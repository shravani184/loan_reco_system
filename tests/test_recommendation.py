"""
The Recommendation Orchestrator (P12).

The most important test here is ORDERING INTEGRITY: with a stubbed recommender
returning a deliberately scrambled ordering, the selected candidate must be the
highest-SCORING one that survives validation and guardrails — not the cheapest, not
the first, not the one a deterministic score would have preferred. That is what proves
nothing downstream re-sorts.

Model behaviour is injected with a stub through the module's own seam rather than by
requiring a trained artifact, per the test-data rule in AGENTS.md section 2.
"""

import pytest

from app.config import settings
from app.core import recommendation as orchestrator
from app.core.recommendation import recommend
from app.ml import recommender as ml_recommender
from app.ml import risk as ml_risk
from app.schemas import (
    CustomerProfile,
    LoanRequirement,
    Recommendation,
    ScoredCandidate,
    ScoringResult,
)
from app.schemas.enums import (
    CandidateOutcome,
    EligibilityStatus,
    FinancingStrategy,
    GuardrailRule,
    MismatchReasonCode,
    RecommendationSource,
    RecommendationStatus,
    RiskAppetite,
)
from tests import fixtures

CATALOGUE = fixtures.mock_catalogue()


@pytest.fixture(autouse=True)
def clean_model_state():
    """No test may inherit or leak a loaded model."""
    ml_risk.reset_state()
    ml_recommender.reset_state()
    yield
    ml_risk.reset_state()
    ml_recommender.reset_state()


def _run(customer=None, portfolio=None, requirement=None, catalogue=None, **kwargs):
    return recommend(
        customer or fixtures.standard_customer(),
        fixtures.mixed_portfolio() if portfolio is None else portfolio,
        requirement or fixtures.standard_requirement(),
        catalogue if catalogue is not None else CATALOGUE,
        **kwargs,
    )


def _stub_scorer(monkeypatch, score_for, source=RecommendationSource.ML_RANKER):
    """
    Replace the recommender with a known ordering.

    `score_for(candidate) -> float | None` decides the suitability. The stub sorts
    descending and assigns ranks, exactly as the real one does, so the orchestrator
    cannot tell the difference — which is the point.
    """

    def stub(
        customer,
        financial_metrics,
        portfolio_metrics,
        personalization_context,
        requirement,
        products_by_id,
        candidates,
        risk_pd,
    ):
        scores = [score_for(candidate) for candidate in candidates]
        order = sorted(
            range(len(candidates)),
            key=lambda i: (-(scores[i] if scores[i] is not None else 0.0), i),
        )
        return ScoringResult(
            scored_candidates=[
                ScoredCandidate(
                    candidate=candidates[index],
                    raw_ranker_margin=None if scores[index] is None else scores[index],
                    suitability=scores[index],
                    rank=rank,
                )
                for rank, index in enumerate(order, start=1)
            ],
            source=source,
        )

    monkeypatch.setattr(orchestrator, "score_candidates", stub)


# ================================================== the end-to-end paths


def test_a_normal_customer_gets_a_complete_recommendation(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run()
    assert isinstance(result, Recommendation)
    assert result.status is RecommendationStatus.RECOMMENDED
    assert result.source is RecommendationSource.ML_RANKER
    assert result.selected_candidate is not None
    assert result.ml_suitability == pytest.approx(0.9)
    assert result.risk is not None
    assert result.decision_trace is not None


def test_a_customer_with_no_portfolio_gets_a_borrow_only_recommendation(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run(portfolio=fixtures.empty_portfolio())
    assert result.status is RecommendationStatus.RECOMMENDED
    assert result.selected_candidate.strategy is FinancingStrategy.BORROW_100
    assert result.selected_candidate.liquidation_amount == 0.0
    assert result.decision_trace.portfolio_metrics.has_portfolio is False


def test_a_cold_start_customer_gets_a_valid_recommendation(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run(user_id=None)
    assert result.status is RecommendationStatus.RECOMMENDED
    assert result.decision_trace.personalization.is_cold_start is True
    assert result.decision_trace.user_id is None


def test_the_result_is_deterministic(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    first = _run()
    second = _run()
    assert first.model_dump() == second.model_dump()


# ====================================================== ORDERING INTEGRITY


def _scrambled_scores(candidates):
    """
    A deliberately perverse ordering: the MOST expensive candidate scores highest.

    If anything downstream re-sorted by cost, EMI or a deterministic utility, the
    selected candidate would not be the one this ordering puts first.
    """
    ranked = sorted(candidates, key=lambda c: -c.emi)
    return {
        candidate.candidate_id: 0.99 - index * 0.001
        for index, candidate in enumerate(ranked)
    }


def test_the_selected_candidate_is_the_highest_scoring_survivor(monkeypatch):
    """
    ORDERING INTEGRITY. Nothing downstream may re-sort the model's ranking.
    """
    from app.core.candidates import generate_candidates
    from app.core.eligibility import check_eligibility
    from app.core.financial import analyze_financials
    from app.core.guardrails import check_guardrails
    from app.core.portfolio import analyze_portfolio
    from app.core.validation import validate_candidate

    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    financial = analyze_financials(customer)
    portfolio_metrics = analyze_portfolio(fixtures.mixed_portfolio())
    eligible = {
        r.product_id
        for r in check_eligibility(customer, financial, requirement, CATALOGUE)
        if r.status is EligibilityStatus.ELIGIBLE
    }
    candidates = [
        c
        for c in generate_candidates(
            requirement,
            financial,
            portfolio_metrics,
            [p for p in CATALOGUE if p.product_id in eligible],
        ).candidates
        if c.feasible
    ]
    scores = _scrambled_scores(candidates)
    _stub_scorer(monkeypatch, lambda candidate: scores[candidate.candidate_id])

    result = _run()

    # Independently compute what the walk SHOULD have selected.
    products_by_id = {p.product_id: p for p in CATALOGUE}
    expected = None
    for candidate in sorted(candidates, key=lambda c: -scores[c.candidate_id]):
        if scores[candidate.candidate_id] < settings.SUITABILITY_ACCEPTANCE_THRESHOLD:
            break
        product = products_by_id.get(candidate.product_id)
        if not validate_candidate(candidate, product, financial, portfolio_metrics).passed:
            continue
        if not check_guardrails(
            requirement.risk_appetite, financial, portfolio_metrics, candidate
        ).allowed:
            continue
        expected = candidate
        break

    assert expected is not None
    assert result.selected_candidate.candidate_id == expected.candidate_id


def test_alternatives_follow_ml_order_exactly(monkeypatch):
    """Alternatives are the NEXT candidates in the model's own ranking."""
    from app.core.candidates import generate_candidates
    from app.core.eligibility import check_eligibility
    from app.core.financial import analyze_financials
    from app.core.portfolio import analyze_portfolio

    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    financial = analyze_financials(customer)
    portfolio_metrics = analyze_portfolio(fixtures.mixed_portfolio())
    eligible = {
        r.product_id
        for r in check_eligibility(customer, financial, requirement, CATALOGUE)
        if r.status is EligibilityStatus.ELIGIBLE
    }
    candidates = [
        c
        for c in generate_candidates(
            requirement,
            financial,
            portfolio_metrics,
            [p for p in CATALOGUE if p.product_id in eligible],
        ).candidates
        if c.feasible
    ]
    scores = _scrambled_scores(candidates)
    _stub_scorer(monkeypatch, lambda candidate: scores[candidate.candidate_id])

    result = _run()
    ranks = [item.rank for item in result.alternatives]
    assert ranks == sorted(ranks), "alternatives were re-sorted out of ML order"
    assert all(rank > result.decision_trace.validation_walk[-1].rank for rank in ranks)
    suitabilities = [item.suitability for item in result.alternatives]
    assert suitabilities == sorted(suitabilities, reverse=True)


def test_alternatives_are_capped_by_config(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run()
    assert len(result.alternatives) <= settings.MAX_ALTERNATIVES_RETURNED


def test_the_orchestrator_contains_no_scoring_formula():
    """
    The v1.0 regression this redesign removed. Checked against the AST so the module's
    own prose about NOT scoring cannot satisfy or break it.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(orchestrator))
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for banned in ("score", "utility", "rank_", "weight"):
        offenders = [name for name in defined if banned in name.lower()]
        assert offenders == [], (banned, offenders)


def test_the_diagnostic_score_is_recorded_but_never_used_to_order():
    """
    It may appear exactly once, assigned to the trace field. Any use of it in a sort
    key would be the deterministic score reordering an ML result.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(orchestrator))
    callers = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "diagnostic_utility_score"
            ):
                callers.add(node.name)
    assert callers == {"recommend"}

    # And it must not appear anywhere inside an ordering expression. Collect every
    # identifier used within a sorted/max/min call and assert none of them is the
    # diagnostic score or the variable holding it.
    ordering_names = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in {"sorted", "max", "min"}:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name):
                ordering_names.add(inner.id)
            elif isinstance(inner, ast.Attribute):
                ordering_names.add(inner.attr)
    offenders = [name for name in ordering_names if "diagnostic" in name.lower()]
    assert offenders == [], (
        f"{offenders} appear inside an ordering expression — the diagnostic score "
        "may never reorder an ML result."
    )


# ================================================ the blocked top choice


def test_a_blocked_ml_top_choice_is_surfaced_with_its_rule_and_cap(monkeypatch):
    """
    "The model's best match for you was X, but it exceeds your conservative profile,
    so we recommend Y" — a signature behaviour, not a detail.
    """
    conservative = fixtures.standard_requirement().model_copy(
        update={"risk_appetite": RiskAppetite.CONSERVATIVE}
    )

    # Score the heaviest liquidation highest, so the conservative liquidation-share cap
    # blocks the model's own first pick.
    def score(candidate):
        return 0.99 if candidate.liquidation_amount > 0 else 0.80

    _stub_scorer(monkeypatch, score)
    result = _run(requirement=conservative)

    assert result.ml_top_choice_blocked is not None
    blocked = result.ml_top_choice_blocked
    assert blocked.blocking_rule == GuardrailRule.MAX_LIQUIDATION_SHARE.value
    assert blocked.reason_code is MismatchReasonCode.LIQUIDATION_SHARE_CAP_EXCEEDED
    assert blocked.cap_value == (
        settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE].max_liquidation_share
    )
    assert blocked.observed_value > blocked.cap_value
    # And the customer still gets a recommendation — the safer option.
    assert result.status is RecommendationStatus.RECOMMENDED
    assert result.selected_candidate.candidate_id != blocked.candidate.candidate_id


def test_the_blocked_top_choice_is_also_in_the_trace(monkeypatch):
    conservative = fixtures.standard_requirement().model_copy(
        update={"risk_appetite": RiskAppetite.CONSERVATIVE}
    )
    _stub_scorer(
        monkeypatch, lambda c: 0.99 if c.liquidation_amount > 0 else 0.80
    )
    result = _run(requirement=conservative)
    assert result.decision_trace.ml_top_choice_blocked is not None
    assert result.decision_trace.validation_walk[0].outcome is (
        CandidateOutcome.GUARDRAIL_BLOCKED
    )


def test_no_blocked_top_choice_when_the_model_pick_is_accepted(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run(portfolio=fixtures.empty_portfolio())
    if result.decision_trace.validation_walk[0].outcome is CandidateOutcome.RECOMMENDED:
        assert result.ml_top_choice_blocked is None


# ==================================================== the five statuses


def test_status_recommended(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    assert _run().status is RecommendationStatus.RECOMMENDED


def test_status_no_eligible_products():
    """The fixtures' deliberately unmatched customer."""
    result = _run(
        customer=fixtures.no_match_customer(), portfolio=fixtures.empty_portfolio()
    )
    assert result.status is RecommendationStatus.NO_ELIGIBLE_PRODUCTS
    assert result.selected_candidate is None
    assert result.coverage.products_passing_eligibility == 0


def test_status_no_feasible_candidates():
    """
    Eligible on paper, but nothing is affordable and there is no portfolio to pay
    from — so the option space is empty for arithmetic reasons, not rule reasons.
    """
    stretched = fixtures.standard_customer().model_copy(
        update={"monthly_expenses": 119_000.0, "existing_emi": 0.0}
    )
    result = _run(customer=stretched, portfolio=fixtures.empty_portfolio())
    assert result.status is RecommendationStatus.NO_FEASIBLE_CANDIDATES
    assert result.selected_candidate is None
    assert result.coverage.products_passing_eligibility > 0
    assert result.coverage.candidates_generated > 0


def test_status_all_candidates_blocked(monkeypatch):
    """
    Feasible candidates exist and score well, but every one the walk reaches violates
    a policy cap. That is a POLICY outcome, not an unsuitability one.
    """
    _stub_scorer(monkeypatch, lambda candidate: 0.99)
    customer = fixtures.standard_customer().model_copy(
        update={
            "monthly_income": 100_000.0,
            "monthly_expenses": 30_000.0,
            "existing_emi": 30_000.0,
        }
    )
    requirement = fixtures.standard_requirement().model_copy(
        update={"risk_appetite": RiskAppetite.CONSERVATIVE}
    )
    result = _run(
        customer=customer, portfolio=fixtures.empty_portfolio(), requirement=requirement
    )
    assert result.status is RecommendationStatus.ALL_CANDIDATES_BLOCKED
    assert result.selected_candidate is None
    assert result.decision_trace.validation_walk
    assert all(
        step.outcome is CandidateOutcome.GUARDRAIL_BLOCKED
        for step in result.decision_trace.validation_walk
    )


def test_status_no_suitable_loan(monkeypatch):
    """
    Candidates reached the recommender and none scored high enough. The system says so
    rather than manufacturing a recommendation.
    """
    _stub_scorer(monkeypatch, lambda candidate: 0.10)
    result = _run()
    assert result.status is RecommendationStatus.NO_SUITABLE_LOAN
    assert result.selected_candidate is None
    assert result.ml_suitability is None
    assert result.mismatch_reasons


def test_the_four_stop_points_are_distinguishable(monkeypatch):
    """Collapsing them into one status is a defect (CONTEXT.md 7.1)."""
    _stub_scorer(monkeypatch, lambda candidate: 0.10)
    unsuitable = _run().status

    _stub_scorer(monkeypatch, lambda candidate: 0.99)
    blocked = _run(
        customer=fixtures.standard_customer().model_copy(
            update={
                "monthly_income": 100_000.0,
                "monthly_expenses": 30_000.0,
                "existing_emi": 30_000.0,
            }
        ),
        portfolio=fixtures.empty_portfolio(),
        requirement=fixtures.standard_requirement().model_copy(
            update={"risk_appetite": RiskAppetite.CONSERVATIVE}
        ),
    ).status
    ineligible = _run(
        customer=fixtures.no_match_customer(), portfolio=fixtures.empty_portfolio()
    ).status
    infeasible = _run(
        customer=fixtures.standard_customer().model_copy(
            update={"monthly_expenses": 119_000.0, "existing_emi": 0.0}
        ),
        portfolio=fixtures.empty_portfolio(),
    ).status

    assert len({unsuitable, blocked, ineligible, infeasible}) == 4


def test_a_non_recommended_status_never_carries_a_candidate(monkeypatch):
    """Never manufacture a recommendation to avoid saying NO_SUITABLE_LOAN."""
    _stub_scorer(monkeypatch, lambda candidate: 0.10)
    result = _run()
    assert result.status is not RecommendationStatus.RECOMMENDED
    assert result.selected_candidate is None
    assert result.alternatives == []


# ================================================== mismatch and funnel


def test_the_coverage_funnel_is_monotone(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    coverage = _run().coverage
    assert coverage.products_passing_eligibility <= coverage.catalogue_products
    assert (
        coverage.products_with_feasible_candidates
        <= coverage.products_passing_eligibility
    )
    assert coverage.candidates_infeasible <= coverage.candidates_generated
    assert coverage.candidates_scored <= coverage.candidates_generated
    assert (
        coverage.candidates_above_suitability_threshold <= coverage.candidates_scored
    )
    assert coverage.candidates_passing_guardrails <= (
        coverage.candidates_passing_validation
    )


def test_the_funnel_is_emitted_on_success_and_on_failure(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    assert _run().coverage.catalogue_products == len(CATALOGUE)
    _stub_scorer(monkeypatch, lambda candidate: 0.10)
    assert _run().coverage.catalogue_products == len(CATALOGUE)


def test_the_funnel_records_dominance_pruning(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run()
    assert result.coverage.candidates_dominance_pruned == (
        result.decision_trace.candidate_counts.dominance_pruned
    )


def test_every_mismatch_reason_traces_to_a_rule_that_fired():
    """
    No reason may be generated that does not correspond to a rule evaluation that
    actually fired (CONTEXT.md 7.2). Checked against the eligibility results.
    """
    result = _run(
        customer=fixtures.no_match_customer(), portfolio=fixtures.empty_portfolio()
    )
    fired = {
        (r.product_id, r.reason_code)
        for r in result.decision_trace.eligibility
        if r.status is EligibilityStatus.INELIGIBLE
    }
    eligibility_codes = {
        MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM,
        MismatchReasonCode.INCOME_BELOW_MINIMUM,
        MismatchReasonCode.AMOUNT_ABOVE_PRODUCT_MAX,
        MismatchReasonCode.AMOUNT_BELOW_PRODUCT_MIN,
        MismatchReasonCode.TENURE_OUT_OF_RANGE,
        MismatchReasonCode.PURPOSE_NOT_SUPPORTED,
    }
    for reason in result.mismatch_reasons:
        if reason.code in eligibility_codes:
            assert (reason.product_id, reason.code) in fired


def test_an_eligibility_reasons_observed_value_matches_the_rule_that_fired():
    result = _run(
        customer=fixtures.no_match_customer(), portfolio=fixtures.empty_portfolio()
    )
    by_product = {
        r.product_id: r
        for r in result.decision_trace.eligibility
        if r.status is EligibilityStatus.INELIGIBLE
    }
    checked = 0
    for reason in result.mismatch_reasons:
        source = by_product.get(reason.product_id)
        if source is None or source.observed_value is None:
            continue
        assert reason.observed_value == source.observed_value
        assert reason.threshold_value == source.threshold_value
        checked += 1
    assert checked > 0


def test_no_suitability_reason_is_invented_in_fallback_mode(monkeypatch):
    """
    With no calibrated score there is nothing to be below a threshold. Emitting
    SUITABILITY_BELOW_THRESHOLD would be inventing a reason.
    """
    _stub_scorer(
        monkeypatch,
        lambda candidate: None,
        source=RecommendationSource.DETERMINISTIC_FALLBACK,
    )
    result = _run()
    assert all(
        reason.code is not MismatchReasonCode.SUITABILITY_BELOW_THRESHOLD
        for reason in result.mismatch_reasons
    )


def _under_funded_candidate(coverage: float):
    """A feasible candidate that funds only `coverage` of the requirement."""
    from app.core.finance_math import emi, total_interest, total_repayment
    from app.schemas import Candidate

    required = 2_000_000.0
    loan = required * coverage
    monthly = emi(loan, 9.0, 120)
    return Candidate(
        candidate_id=f"partial-{coverage}",
        product_id="HL-002",
        lender="Kestrel Housing Finance",
        tenure_months=120,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=required,
        loan_amount=loan,
        emi=monthly,
        total_interest=total_interest(loan, 9.0, 120),
        total_repayment=total_repayment(loan, 9.0, 120),
        liquidation_amount=0.0,
        volatile_liquidation_amount=0.0,
        remaining_portfolio_value=0.0,
        resulting_liquidity_ratio=0.0,
        resulting_debt_burden_ratio=0.2,
        affordability_headroom=1_000.0,
    )


def test_required_amount_unreachable_is_emitted_when_nothing_funds_the_request():
    """
    The reason code P5 deliberately left to the orchestrator: it is a conclusion about
    the whole option space, not about any single candidate.
    """
    from app.core.mismatch import analyze_mismatch

    candidates = [_under_funded_candidate(0.6), _under_funded_candidate(0.8)]
    reasons, _ = analyze_mismatch([], candidates, [], [])
    unreachable = [
        reason
        for reason in reasons
        if reason.code is MismatchReasonCode.REQUIRED_AMOUNT_UNREACHABLE
    ]
    assert len(unreachable) == 1
    # It reports the BEST coverage achieved against what was asked for.
    assert unreachable[0].observed_value == pytest.approx(2_000_000.0 * 0.8)
    assert unreachable[0].threshold_value == pytest.approx(2_000_000.0)


def test_required_amount_unreachable_is_not_emitted_when_the_request_is_met():
    """It must fire only when the option space genuinely cannot reach the amount."""
    from app.core.mismatch import analyze_mismatch

    reasons, _ = analyze_mismatch(
        [], [_under_funded_candidate(0.6), _under_funded_candidate(1.0)], [], []
    )
    assert all(
        reason.code is not MismatchReasonCode.REQUIRED_AMOUNT_UNREACHABLE
        for reason in reasons
    )


# ========================================================== the fallback


def test_a_missing_recommender_yields_a_valid_fallback_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "RECOMMENDER_MODEL_PATH", str(tmp_path / "absent.json")
    )
    monkeypatch.setattr(
        settings, "CALIBRATION_KNOTS_PATH", str(tmp_path / "absent_calibration.json")
    )
    result = _run()
    assert result.source is RecommendationSource.DETERMINISTIC_FALLBACK
    assert result.ml_suitability is None
    assert result.decision_trace.recommendation_source is (
        RecommendationSource.DETERMINISTIC_FALLBACK
    )
    assert all(item.suitability is None for item in result.decision_trace.ranked_candidates)


def test_the_fallback_still_selects_and_still_applies_guardrails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "RECOMMENDER_MODEL_PATH", str(tmp_path / "absent.json")
    )
    monkeypatch.setattr(
        settings, "CALIBRATION_KNOTS_PATH", str(tmp_path / "absent_calibration.json")
    )
    result = _run()
    assert result.status in {
        RecommendationStatus.RECOMMENDED,
        RecommendationStatus.ALL_CANDIDATES_BLOCKED,
    }
    if result.selected_candidate is not None:
        assert result.decision_trace.validation_walk[-1].guardrail.allowed is True


def test_status_and_source_are_independent_axes(monkeypatch, tmp_path):
    """A DETERMINISTIC_FALLBACK run can still be RECOMMENDED (CONTEXT.md 5.3)."""
    monkeypatch.setattr(
        settings, "RECOMMENDER_MODEL_PATH", str(tmp_path / "absent.json")
    )
    monkeypatch.setattr(
        settings, "CALIBRATION_KNOTS_PATH", str(tmp_path / "absent_calibration.json")
    )
    result = _run(portfolio=fixtures.empty_portfolio())
    assert result.source is RecommendationSource.DETERMINISTIC_FALLBACK
    assert result.status is RecommendationStatus.RECOMMENDED
    assert result.ml_suitability is None


def test_a_missing_risk_model_flags_imputation_and_continues(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RISK_MODEL_PATH", str(tmp_path / "absent.json"))
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    result = _run()
    assert result.risk.imputed is True
    assert result.status is RecommendationStatus.RECOMMENDED


# =============================================================== the trace


def test_the_trace_is_fully_populated(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run().decision_trace
    assert trace.financial_metrics is not None
    assert trace.portfolio_metrics is not None
    assert trace.personalization is not None
    assert trace.eligibility
    assert trace.candidate_counts.generated > 0
    assert trace.risk is not None
    assert trace.ranked_candidates
    assert trace.validation_walk
    assert trace.selection_stop_reason
    assert trace.coverage is not None


def test_the_trace_carries_every_version_stamp(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run().decision_trace
    assert trace.config_version == settings.CONFIG_VERSION
    assert trace.feature_version == settings.FEATURE_VERSION
    assert trace.prompt_version == settings.PROMPT_VERSION
    assert trace.labeling_policy_version == settings.LABELING_POLICY_VERSION
    assert trace.risk_model_version
    assert trace.recommender_model_version


def test_the_trace_lists_every_catalogue_product_with_an_outcome(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run().decision_trace
    assert len(trace.eligibility) == len(CATALOGUE)
    assert {r.product_id for r in trace.eligibility} == {
        p.product_id for p in CATALOGUE
    }


def test_the_trace_includes_at_least_one_elimination_reason(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run().decision_trace
    eliminated = [
        r for r in trace.eligibility if r.status is EligibilityStatus.INELIGIBLE
    ]
    assert eliminated
    assert all(r.reason_code is not None for r in eliminated)


def test_the_walk_log_records_every_candidate_attempted(monkeypatch):
    """Not only the winner — the ones that failed before it are the interesting part."""
    conservative = fixtures.standard_requirement().model_copy(
        update={"risk_appetite": RiskAppetite.CONSERVATIVE}
    )
    _stub_scorer(monkeypatch, lambda c: 0.99 if c.liquidation_amount > 0 else 0.80)
    walk = _run(requirement=conservative).decision_trace.validation_walk
    assert len(walk) > 1
    assert [step.rank for step in walk] == sorted(step.rank for step in walk)
    assert walk[-1].outcome is CandidateOutcome.RECOMMENDED


def test_the_trace_records_the_advisory_diagnostic_score(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run().decision_trace
    assert trace.winner_diagnostic_utility_score is not None


def test_the_trace_holds_no_raw_pii(monkeypatch):
    """Identify a customer by pseudonymous id only (AGENTS.md section 9)."""
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    trace = _run(user_id="cust-0001").decision_trace
    dumped = trace.model_dump_json()
    for banned in ("name", "email", "phone", "address", "aadhaar", "passport"):
        assert banned not in dumped.lower()


# ------------------------------------------------------------- boundaries


def test_no_emi_is_recomputed_outside_finance_math():
    """One EMI implementation. The orchestrator and validator both import it."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in (root / "app").rglob("*.py"):
        if path.name == "finance_math.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "def emi(" in text or "/ 12 / 100" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_the_orchestrator_never_mutates_its_inputs(monkeypatch):
    _stub_scorer(monkeypatch, lambda candidate: 0.9)
    customer = fixtures.standard_customer()
    portfolio = fixtures.mixed_portfolio()
    requirement = fixtures.standard_requirement()
    before = (
        customer.model_dump(),
        portfolio.model_dump(),
        requirement.model_dump(),
    )
    recommend(customer, portfolio, requirement, CATALOGUE)
    assert (
        customer.model_dump(),
        portfolio.model_dump(),
        requirement.model_dump(),
    ) == before


def test_an_empty_catalogue_is_no_eligible_products():
    result = _run(catalogue=[], portfolio=fixtures.empty_portfolio())
    assert result.status is RecommendationStatus.NO_ELIGIBLE_PRODUCTS
    assert result.coverage.catalogue_products == 0
