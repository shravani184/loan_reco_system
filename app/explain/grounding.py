"""
Numeric and entity grounding guards (P13).

PORTED FROM PHASE R, NOT REDESIGNED. spikes/grounding validated this rule set against
the 78-case corpus now at tests/data/grounding_corpus.jsonl: 21/21 UNGROUNDED cases
rejected, 0/54 GROUNDED cases falsely rejected. This module productionizes it against
the real payload schema and moves every constant into config.

THE DESIGN (AGENTS.md section 5, CONTEXT.md 17.3):
  * CONTEXT-GATED EXTRACTION — a number is financial only next to a currency symbol,
    a percent sign or a cue word, or above the magnitude floor. Requiring context,
    rather than only filtering by size, is what removes the bulk of false positives.
  * EXPANDED ACCEPTED SET — build every legitimate representation of each PAYLOAD
    figure, rather than trying to parse every possible spelling in the response.
  * THREE OUTCOMES — GROUNDED accepts, UNVERIFIED accepts-and-flags, UNGROUNDED
    rejects. An unparseable token is a limitation of the guard, not evidence of a
    hallucination, and must not cost the user their explanation.

THIS GUARD MAY NOT BE DISABLED OR BYPASSED, AND ITS TOLERANCE MAY NOT BE WIDENED TO
MAKE A DEMO PASS. If it produces a false positive, the normalizer is the bug: fix the
normalizer and add a corpus case. Never widen a tolerance, never edit a corpus label.

Standard library only.
"""

import logging
import re

from app.config import settings
from app.schemas.explanation import GroundingCheck, GroundingFinding
from app.schemas.enums import GroundingOutcome

logger = logging.getLogger(__name__)

# Numbers in these shapes are STRUCTURAL, never financial. Excluded before any
# context test, because "top 3" and "1st" are exactly where naive guards fire.
STRUCTURAL_PATTERNS = [
    re.compile(r"\b\d+(st|nd|rd|th)\b", re.I),  # 1st, 2nd
    re.compile(r"\boption\s+\d+\b", re.I),  # Option 2
    re.compile(r"\bsection\s+\d+\b", re.I),  # Section 7
    re.compile(r"\bstep\s+\d+\b", re.I),  # Step 3
    re.compile(r"\btop\s+\d+\b", re.I),  # top 3
    re.compile(
        r"\b\d+\s+(alternatives?|options?|products?|lenders?|banks?|reasons?|choices?)\b",
        re.I,
    ),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),  # dates
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO dates
]

MULTIPLIERS = {
    "lakh": 100_000.0,
    "lakhs": 100_000.0,
    "lac": 100_000.0,
    "lacs": 100_000.0,
    "l": 100_000.0,
    "crore": 10_000_000.0,
    "crores": 10_000_000.0,
    "cr": 10_000_000.0,
    "k": 1_000.0,
    "million": 1_000_000.0,
    "mn": 1_000_000.0,
}

# A number, optionally preceded by a currency marker, optionally followed by a unit.
#
# THE GROUPED-DIGITS BRANCH IS FIRST AND REQUIRES AT LEAST ONE COMMA GROUP. Without
# that ordering, `\d{1,3}(?:,\d{2,3})*` matches only the first three digits of a plain
# number and "600000" reads as 600 followed by 000 — a defect that made grounded cases
# pass for entirely the wrong reason until the Phase R corpus caught it.
NUMBER_PATTERN = re.compile(
    r"""
    (?:(?<![A-Za-z])(?P<currency>₹|rs\.?|inr)\s*)?
    (?P<number>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    [\s-]*
    (?P<unit>%|percent|lakhs?|lacs?|crores?|cr\b|l\b|k\b|million|mn\b|months?|years?|yrs?|yr\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _walk(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item, prefix)
    else:
        yield prefix, obj


def build_accepted_set(payload: dict) -> set[float]:
    """
    Every legitimate reading of every payload figure.

    DELIBERATELY NO DIVISIONS OR ROUNDING EXPANSIONS. The response side already
    converts "6 lakh" and "6L" into 600000, so the accepted set only needs base units
    plus the genuine duals (percent/decimal, month/year). Phase R's first version added
    value/1000 and round(value, -5) for every figure, and that made a sanctioned limit
    of 15,000,000 accept a fabricated EMI of "Rs 15,000". A writer's rounding is
    covered by the relative tolerance instead.
    """
    accepted: set[float] = set()

    for key, value in _walk(payload):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        accepted.add(float(value))
        lowered = key.lower()
        if "rate" in lowered or "percent" in lowered or lowered.endswith("_pct"):
            accepted.add(value / 100.0)  # 8%   -> 0.08
            accepted.add(value * 100.0)  # 0.08 -> 8
        if "tenure" in lowered or "month" in lowered:
            accepted.add(value / 12.0)  # 48 months -> 4 years
        if "year" in lowered:
            accepted.add(value * 12.0)
        if "score" in lowered or "suitability" in lowered:
            accepted.add(value * 100.0)  # 0.86 -> 86
    return accepted


def _matches(value: float, accepted: set[float]) -> bool:
    for candidate in accepted:
        tolerance = abs(candidate) * settings.GROUNDING_RELATIVE_TOLERANCE
        # The absolute rupee allowance is meaningful for amounts and catastrophic for
        # small derived numbers: applied everywhere it made "5 years" match a 4-year
        # tenure and "9%" match an 8% rate.
        if abs(candidate) >= settings.GROUNDING_ABSOLUTE_TOLERANCE_MIN_MAGNITUDE:
            tolerance = max(tolerance, settings.GROUNDING_ABSOLUTE_TOLERANCE)
        if abs(value - candidate) <= tolerance:
            return True
    return False


def _structural_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in STRUCTURAL_PATTERNS:
        spans.extend(match.span() for match in pattern.finditer(text))
    return spans


def _in_span(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _has_cue(text: str, start: int, end: int, window: int = 28) -> bool:
    left = text[max(0, start - window) : start].lower()
    right = text[end : end + window].lower()
    words = set(re.findall(r"[a-z]+", left + " " + right))
    return bool(words & set(settings.GROUNDING_CUE_WORDS))


def _interpretations(raw: str, unit: str | None, currency: str | None) -> list[float]:
    """Every reading of this token. Matching any one of them grounds it."""
    base = float(raw.replace(",", ""))
    unit = (unit or "").lower().rstrip(".")

    if unit in ("%", "percent"):
        return [base, base / 100.0]
    if unit in MULTIPLIERS:
        # A lakh/crore/k suffix is UNAMBIGUOUS: "8 lakh" is 800000, never 8. Keeping
        # the bare base as a fallback let a fabricated "8 lakh" match an 8% rate.
        return [base * MULTIPLIERS[unit]]
    if unit in ("month", "months"):
        return [base, base / 12.0]
    if unit in ("year", "years", "yr", "yrs"):
        return [base * 12.0, base]
    return [base]


def verify_numeric_grounding(response_text: str, payload: dict) -> GroundingCheck:
    """
    Check every financial figure in the response against the payload.

    Returns UNGROUNDED if ANY token parsed confidently as a financial figure with no
    payload match; otherwise UNVERIFIED if any token could not be confidently parsed;
    otherwise GROUNDED.
    """
    accepted = build_accepted_set(payload)
    spans = _structural_spans(response_text)
    findings: list[GroundingFinding] = []

    for match in NUMBER_PATTERN.finditer(response_text):
        start, end = match.span()
        number_start = match.start("number")

        # A number inside a word ("P1", "HOME-A2") is an identifier, not a figure.
        preceding = response_text[max(0, number_start - 1) : number_start]
        if preceding.isalpha():
            continue
        if _in_span(number_start, spans):
            continue

        currency = match.group("currency")
        unit = match.group("unit")
        raw = match.group("number")
        try:
            base = float(raw.replace(",", ""))
        except ValueError:
            findings.append(
                GroundingFinding(
                    text=match.group(0).strip(),
                    outcome=GroundingOutcome.UNVERIFIED,
                    note="unparseable",
                )
            )
            continue

        explicit = bool(currency) or bool(unit)
        cued = _has_cue(response_text, start, end)
        if not (explicit or cued or base >= settings.GROUNDING_MAGNITUDE_FLOOR):
            continue  # a small structural integer in no financial context

        readings = _interpretations(raw, unit, currency)
        if any(_matches(reading, accepted) for reading in readings):
            findings.append(
                GroundingFinding(
                    text=match.group(0).strip(),
                    outcome=GroundingOutcome.GROUNDED,
                    interpretations=readings,
                )
            )
            continue

        # No match. Is the parse confident enough to call the figure invented?
        # An explicit unit or currency always is. A cued number is, when it is large
        # or a decimal — decimals are almost never structural. A bare small cued
        # integer is NOT: that band is exactly where false positives live, so it
        # degrades to UNVERIFIED rather than costing the user their explanation.
        confident = (
            explicit
            or base >= settings.GROUNDING_MAGNITUDE_FLOOR
            or (cued and (base >= settings.GROUNDING_SMALL_CUED_FLOOR or "." in raw))
        )
        findings.append(
            GroundingFinding(
                text=match.group(0).strip(),
                outcome=GroundingOutcome.UNGROUNDED
                if confident
                else GroundingOutcome.UNVERIFIED,
                interpretations=readings,
                note="no payload match" if confident else "ambiguous, low confidence",
            )
        )

    if any(f.outcome is GroundingOutcome.UNGROUNDED for f in findings):
        result = GroundingCheck(outcome=GroundingOutcome.UNGROUNDED, findings=findings)
        logger.warning(
            "numeric grounding REJECTED an explanation; invented figures: %s",
            result.offending(),
        )
        return result
    if any(f.outcome is GroundingOutcome.UNVERIFIED for f in findings):
        result = GroundingCheck(outcome=GroundingOutcome.UNVERIFIED, findings=findings)
        # Logged so the normalizer improves from real traffic, per CONTEXT.md 17.3.
        logger.info(
            "numeric grounding UNVERIFIED (accepted, flagged); tokens: %s",
            result.unverified(),
        )
        return result
    return GroundingCheck(outcome=GroundingOutcome.GROUNDED, findings=findings)


def verify_entity_grounding(
    response_text: str, payload_entities: list[str], known_entities: list[str]
) -> GroundingCheck:
    """
    A product or lender name in the response that is not in the payload is a
    rejection, on the same path as an invented number (AGENTS.md section 5).

    Checked against a KNOWN VOCABULARY rather than by guessing at capitalised phrases.
    That keeps it precise: unknown capitalised text is never asserted to be a product,
    so ordinary prose cannot trip the guard.
    """
    findings: list[GroundingFinding] = []
    allowed = {entity.lower() for entity in payload_entities}
    lowered = response_text.lower()

    for entity in known_entities:
        if entity.lower() in allowed:
            continue
        if re.search(rf"\b{re.escape(entity.lower())}\b", lowered):
            findings.append(
                GroundingFinding(
                    text=entity,
                    outcome=GroundingOutcome.UNGROUNDED,
                    note="entity not in payload",
                )
            )

    if findings:
        result = GroundingCheck(outcome=GroundingOutcome.UNGROUNDED, findings=findings)
        logger.warning(
            "entity grounding REJECTED an explanation; invented entities: %s",
            result.offending(),
        )
        return result
    return GroundingCheck(outcome=GroundingOutcome.GROUNDED)
