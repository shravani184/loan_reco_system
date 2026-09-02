"""
The grounding guards (P13). THE CORPUS IS THE TEST.

tests/data/grounding_corpus.jsonl is FROZEN. When a false positive appears in
practice, the fix is a normalizer improvement plus a NEW corpus case — never a widened
tolerance, never an edited label, never a deleted case (AGENTS.md section 5).

The required result is asymmetric and deliberately so:
  100% of UNGROUNDED cases must be rejected — a missed invented figure is the failure
                                              that actually matters
  ZERO   GROUNDED cases may be falsely rejected — a guard that rejects valid
                                              explanations gets switched off, and then
                                              nothing protects the user at all
"""

import json
from pathlib import Path

import pytest

from app.config import settings
from app.explain.grounding import (
    build_accepted_set,
    verify_entity_grounding,
    verify_numeric_grounding,
)
from app.schemas.enums import GroundingOutcome

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "grounding_corpus.jsonl"
ENTITY_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "entity_corpus.jsonl"


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


CORPUS = _load(CORPUS_PATH)
ENTITY_CORPUS = _load(ENTITY_CORPUS_PATH)


def _outcome(case: dict) -> GroundingOutcome:
    return verify_numeric_grounding(case["response"], case["payload"]).outcome


# =========================================== the corpus, as a whole


def test_the_corpus_is_large_enough_to_mean_something():
    assert len(CORPUS) >= 60


def test_the_corpus_covers_all_three_outcomes():
    labels = {case["expected"] for case in CORPUS}
    assert labels == {"GROUNDED", "UNGROUNDED", "UNVERIFIED"}


def test_every_ungrounded_case_is_rejected():
    """
    100% REQUIRED. A missed invented figure is the failure that matters, because the
    user is shown a number the system never computed.
    """
    ungrounded = [case for case in CORPUS if case["expected"] == "UNGROUNDED"]
    assert ungrounded
    missed = [
        (case["id"], case["response"])
        for case in ungrounded
        if _outcome(case) is not GroundingOutcome.UNGROUNDED
    ]
    assert missed == [], f"invented figures got through: {missed}"


def test_zero_grounded_cases_are_falsely_rejected():
    """
    ZERO REQUIRED. A single false rejection fails the phase: a guard that rejects valid
    explanations gets switched off, and then nothing protects the user.
    """
    grounded = [case for case in CORPUS if case["expected"] == "GROUNDED"]
    assert grounded
    false_positives = [
        (case["id"], case["response"], case.get("note", ""))
        for case in grounded
        if _outcome(case) is GroundingOutcome.UNGROUNDED
    ]
    assert false_positives == [], (
        "the normalizer is the bug — fix it and add a corpus case. Never widen a "
        f"tolerance and never edit a label. False positives: {false_positives}"
    )


@pytest.mark.parametrize("case", CORPUS, ids=[case["id"] for case in CORPUS])
def test_every_corpus_case_gets_its_labelled_outcome(case):
    assert _outcome(case) is GroundingOutcome(case["expected"]), case.get("note", "")


# ================================= the false-positive suite, called out by name


FALSE_POSITIVE_PAYLOAD = {
    "loan_amount": 600_000,
    "emi": 12_133,
    "tenure_months": 48,
    "interest_rate_pct": 8.0,
    "total_interest": 182_384,
}


@pytest.mark.parametrize(
    "response,why",
    [
        ("Your loan amount is Rs 6,00,000.", "Indian digit grouping"),
        ("Your loan amount is 6 lakh.", "lakh form"),
        ("Your loan amount is Rs 6L.", "abbreviated lakh with currency"),
        ("Your loan amount is 600000.", "plain digits"),
        ("The interest rate is 8%.", "percent form of a 0.08 rate"),
        ("The rate works out to 8.0% p.a.", "decimal percent with p.a."),
        ("The tenure is 48 months.", "months as stored"),
        ("The tenure is 4 years.", "years form of a 48-month tenure"),
        ("Here are your 3 alternatives.", "a count, not a figure"),
        ("Option 2 may also suit you.", "a list marker"),
        ("This is our 1st recommendation.", "an ordinal"),
        ("See the top 3 options below.", "a top-N count"),
    ],
)
def test_the_named_false_positive_cases_are_not_rejected(response, why):
    """
    Every one of these is a legitimate phrasing. If any rejects, the NORMALIZER is
    wrong — never the corpus label, never the tolerance.
    """
    outcome = verify_numeric_grounding(response, FALSE_POSITIVE_PAYLOAD).outcome
    assert outcome is not GroundingOutcome.UNGROUNDED, why


# ================================================== the three outcomes


def test_an_invented_figure_is_ungrounded():
    result = verify_numeric_grounding(
        "Your EMI is Rs 45,000.", FALSE_POSITIVE_PAYLOAD
    )
    assert result.outcome is GroundingOutcome.UNGROUNDED
    assert result.rejected is True
    assert result.offending()


def test_an_ambiguous_token_is_unverified_and_the_response_is_accepted():
    """
    An unparseable token is a limitation of the GUARD, not evidence of a
    hallucination, and must not cost the user their explanation.
    """
    unverified_cases = [case for case in CORPUS if case["expected"] == "UNVERIFIED"]
    assert unverified_cases
    for case in unverified_cases:
        result = verify_numeric_grounding(case["response"], case["payload"])
        assert result.outcome is GroundingOutcome.UNVERIFIED
        assert result.rejected is False, "UNVERIFIED must ACCEPT the response"
        assert result.unverified(), "the offending token must be logged"


def test_the_outcome_is_not_a_boolean():
    """Collapsing three outcomes into two is what makes a guard untrustworthy."""
    assert len(list(GroundingOutcome)) == 3
    assert GroundingOutcome.UNVERIFIED is not GroundingOutcome.UNGROUNDED
    assert GroundingOutcome.UNVERIFIED is not GroundingOutcome.GROUNDED


def test_ungrounded_wins_over_unverified_in_the_same_response():
    """One invented figure rejects the whole response, whatever else is in it."""
    result = verify_numeric_grounding(
        "Your loan amount is Rs 6,00,000 and your EMI is Rs 45,000.",
        FALSE_POSITIVE_PAYLOAD,
    )
    assert result.outcome is GroundingOutcome.UNGROUNDED


# ============================================== the accepted set


def test_the_accepted_set_expands_rate_duals():
    accepted = build_accepted_set({"interest_rate_pct": 8.0})
    assert 8.0 in accepted
    assert 0.08 in accepted


def test_the_accepted_set_expands_tenure_duals():
    accepted = build_accepted_set({"tenure_months": 48})
    assert 48.0 in accepted
    assert 4.0 in accepted


def test_the_accepted_set_does_not_expand_by_division_or_rounding():
    """
    Phase R's first version added value/1000 and rounded forms for every figure, which
    made a sanctioned limit of 15,000,000 accept a fabricated EMI of "Rs 15,000".
    """
    accepted = build_accepted_set({"sanctioned_limit": 15_000_000})
    assert 15_000.0 not in accepted
    assert 15_000_000.0 in accepted


def test_a_lakh_suffix_is_unambiguous():
    """
    "8 lakh" is 800000, never 8. Keeping the bare base as a fallback let a fabricated
    "8 lakh" match an 8% interest rate.
    """
    result = verify_numeric_grounding("The amount is 8 lakh.", {"interest_rate_pct": 8.0})
    assert result.outcome is GroundingOutcome.UNGROUNDED


def test_grouped_digits_parse_whole():
    """
    Without the grouped-digits branch first, "600000" reads as 600 then 000 — a defect
    that made grounded cases pass for entirely the wrong reason.
    """
    result = verify_numeric_grounding(
        "The loan is Rs 600000.", {"loan_amount": 600_000}
    )
    assert result.outcome is GroundingOutcome.GROUNDED


def test_a_near_miss_rate_is_not_tolerated():
    """The absolute rupee allowance must not let 9% match an 8% rate."""
    result = verify_numeric_grounding(
        "The rate is 9%.", {"interest_rate_pct": 8.0}
    )
    assert result.outcome is GroundingOutcome.UNGROUNDED


def test_a_near_miss_tenure_is_not_tolerated():
    result = verify_numeric_grounding(
        "The tenure is 5 years.", {"tenure_months": 48}
    )
    assert result.outcome is GroundingOutcome.UNGROUNDED


def test_a_number_inside_an_identifier_is_not_a_figure():
    result = verify_numeric_grounding(
        "The product code is HL-001.", {"loan_amount": 600_000}
    )
    assert result.outcome is not GroundingOutcome.UNGROUNDED


# ================================================== entity grounding


def test_an_invented_lender_is_ungrounded():
    result = verify_entity_grounding(
        "We recommend a loan from Northwind Bank.",
        payload_entities=["Meridian Bank"],
        known_entities=["Meridian Bank", "Northwind Bank"],
    )
    assert result.outcome is GroundingOutcome.UNGROUNDED
    assert "Northwind Bank" in result.offending()


def test_a_payload_lender_is_grounded():
    result = verify_entity_grounding(
        "We recommend a loan from Meridian Bank.",
        payload_entities=["Meridian Bank"],
        known_entities=["Meridian Bank", "Northwind Bank"],
    )
    assert result.outcome is GroundingOutcome.GROUNDED


def test_unknown_capitalised_prose_is_not_treated_as_an_entity():
    """
    The guard checks a KNOWN vocabulary rather than guessing at capitalised phrases,
    so ordinary prose cannot trip it.
    """
    result = verify_entity_grounding(
        "Your Monthly Repayment Is Comfortable.",
        payload_entities=["Meridian Bank"],
        known_entities=["Meridian Bank", "Northwind Bank"],
    )
    assert result.outcome is GroundingOutcome.GROUNDED


@pytest.mark.parametrize(
    "case", ENTITY_CORPUS, ids=[case["id"] for case in ENTITY_CORPUS]
)
def test_every_entity_corpus_case_gets_its_labelled_outcome(case):
    result = verify_entity_grounding(
        case["response"], case["payload_entities"], case["known_entities"]
    )
    assert result.outcome is GroundingOutcome(case["expected"]), case.get("note", "")


# ======================================= the guard cannot be quietly weakened


def test_the_validated_constants_are_unchanged():
    """
    These are the Phase R values the corpus was validated against. Changing one to
    make something pass is the forbidden move (AGENTS.md section 5).
    """
    assert settings.GROUNDING_MAGNITUDE_FLOOR == 1000.0
    assert settings.GROUNDING_SMALL_CUED_FLOOR == 100.0
    assert settings.GROUNDING_RELATIVE_TOLERANCE == 0.01
    assert settings.GROUNDING_ABSOLUTE_TOLERANCE == 1.0
    assert settings.GROUNDING_ABSOLUTE_TOLERANCE_MIN_MAGNITUDE == 100.0


def test_the_guard_uses_only_the_standard_library_and_config():
    import inspect

    import app.explain.grounding as grounding

    source = inspect.getsource(grounding)
    for banned in ("import numpy", "import pandas", "import shap", "import xgboost"):
        assert banned not in source
