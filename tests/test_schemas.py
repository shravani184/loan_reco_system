"""
The typed contract, asserted. Every test here checks a value, an enum or a raised
error — not that something is merely not None (AGENTS.md section 10).
"""

import pytest
from pydantic import ValidationError

from app.schemas import (
    Candidate,
    CandidateGenerationCounts,
    CatalogueCoverage,
    CustomerProfile,
    DecisionTrace,
    EligibilityResult,
    FinancialMetrics,
    GuardrailResult,
    LoanRequirement,
    PersonalizationContext,
    PortfolioMetrics,
    Recommendation,
    RiskPrediction,
    ScoredCandidate,
    ValidationResult,
)
from app.schemas.enums import (
    EligibilityStatus,
    FinancialHealth,
    FinancingStrategy,
    LoanPurpose,
    MismatchReasonCode,
    PortfolioRisk,
    RecommendationSource,
    RecommendationStatus,
    RiskAppetite,
    RiskClass,
)
from tests import fixtures


# --------------------------------------------------------------------- inputs


def test_valid_customer_constructs():
    customer = fixtures.standard_customer()
    assert customer.credit_score == 760
    assert customer.monthly_income == 120_000.0


@pytest.mark.parametrize("score", [299, 901])
def test_credit_score_outside_range_raises(score):
    payload = fixtures.standard_customer().model_dump()
    payload["credit_score"] = score
    with pytest.raises(ValidationError):
        CustomerProfile.model_validate(payload)


def test_negative_income_raises():
    payload = fixtures.standard_customer().model_dump()
    payload["monthly_income"] = -1.0
    with pytest.raises(ValidationError):
        CustomerProfile.model_validate(payload)


def test_unknown_field_is_rejected():
    """extra='forbid' — nothing attaches an undeclared field in passing."""
    payload = fixtures.standard_customer().model_dump()
    payload["annual_bonus"] = 50_000.0
    with pytest.raises(ValidationError):
        CustomerProfile.model_validate(payload)


def test_portfolio_with_zero_holdings_is_valid():
    """The no-portfolio path is first-class, not an error."""
    portfolio = fixtures.empty_portfolio()
    assert portfolio.holdings == []


def test_mixed_portfolio_holds_six_asset_types():
    holdings = fixtures.mixed_portfolio().holdings
    assert len(holdings) == 6
    assert len({h.asset_type for h in holdings}) == 6


def test_zero_required_amount_raises():
    with pytest.raises(ValidationError):
        LoanRequirement(
            purpose=LoanPurpose.HOME,
            required_amount=0.0,
            preferred_tenure_months=120,
            risk_appetite=RiskAppetite.MODERATE,
        )


def test_product_max_amount_below_min_raises():
    payload = fixtures.mock_catalogue()[0].model_dump()
    payload["max_amount"] = 1_000.0
    with pytest.raises(ValidationError):
        type(fixtures.mock_catalogue()[0]).model_validate(payload)


def test_mock_catalogue_spans_lenders_and_purposes():
    catalogue = fixtures.mock_catalogue()
    assert len(catalogue) == 6
    assert len({p.lender for p in catalogue}) == 3
    covered = {purpose for p in catalogue for purpose in p.purposes}
    assert LoanPurpose.HOME in covered and LoanPurpose.BUSINESS in covered


def test_no_match_customer_is_below_every_product_minimum():
    customer = fixtures.no_match_customer()
    for product in fixtures.mock_catalogue():
        assert customer.credit_score < product.min_credit_score
        assert customer.monthly_income < product.min_monthly_income


# ---------------------------------------------------------------- eligibility


def test_ineligible_result_requires_a_reason_code():
    with pytest.raises(ValidationError):
        EligibilityResult(product_id="HL-001", status=EligibilityStatus.INELIGIBLE)


def test_eligible_result_must_not_carry_a_reason_code():
    with pytest.raises(ValidationError):
        EligibilityResult(
            product_id="HL-001",
            status=EligibilityStatus.ELIGIBLE,
            reason_code=MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM,
        )


def test_ineligible_result_carries_observed_and_threshold():
    result = EligibilityResult(
        product_id="HL-001",
        status=EligibilityStatus.INELIGIBLE,
        reason_code=MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM,
        observed_value=545.0,
        threshold_value=720.0,
    )
    assert result.reason_code is MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM
    assert result.observed_value == 545.0


# ------------------------------------------------------------------ candidate


def _borrowing_candidate(**overrides) -> Candidate:
    payload = dict(
        candidate_id="c-1",
        product_id="HL-001",
        lender="Meridian Bank",
        tenure_months=120,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=2_000_000.0,
        loan_amount=2_000_000.0,
        emi=24_797.0,
        total_interest=975_640.0,
        total_repayment=2_975_640.0,
        liquidation_amount=0.0,
        volatile_liquidation_amount=0.0,
        remaining_portfolio_value=2_300_000.0,
        resulting_liquidity_ratio=0.52,
        resulting_debt_burden_ratio=0.31,
        affordability_headroom=8_203.0,
    )
    payload.update(overrides)
    return Candidate(**payload)


def test_borrowing_candidate_constructs_fully_specified():
    candidate = _borrowing_candidate()
    assert candidate.strategy is FinancingStrategy.BORROW_100
    assert candidate.tenure_months == 120
    assert candidate.feasible is True


def test_borrowing_candidate_without_product_raises():
    with pytest.raises(ValidationError):
        _borrowing_candidate(product_id=None)


def test_borrowing_candidate_without_tenure_raises():
    with pytest.raises(ValidationError):
        _borrowing_candidate(tenure_months=None)


def test_no_loan_candidate_carries_no_product_or_tenure():
    """
    LIQUIDATE_100 means "pay from your assets, borrow nothing". Phase R finding:
    it must not be representable as a 1-month loan.
    """
    candidate = Candidate(
        candidate_id="c-noloan",
        strategy=FinancingStrategy.LIQUIDATE_100,
        required_amount=2_000_000.0,
        loan_amount=0.0,
        emi=0.0,
        total_interest=0.0,
        total_repayment=0.0,
        liquidation_amount=2_000_000.0,
        volatile_liquidation_amount=800_000.0,
        remaining_portfolio_value=300_000.0,
        resulting_liquidity_ratio=0.4,
        resulting_debt_burden_ratio=0.1,
        affordability_headroom=53_000.0,
    )
    assert candidate.product_id is None
    assert candidate.tenure_months is None
    assert candidate.emi == 0.0


def test_no_loan_candidate_with_a_tenure_raises():
    with pytest.raises(ValidationError) as excinfo:
        Candidate(
            candidate_id="c-bad",
            tenure_months=1,
            strategy=FinancingStrategy.LIQUIDATE_100,
            required_amount=2_000_000.0,
            loan_amount=0.0,
            emi=0.0,
            total_interest=0.0,
            total_repayment=0.0,
            liquidation_amount=2_000_000.0,
            volatile_liquidation_amount=0.0,
            remaining_portfolio_value=300_000.0,
            resulting_liquidity_ratio=0.4,
            resulting_debt_burden_ratio=0.1,
            affordability_headroom=53_000.0,
        )
    assert "not a 1-month loan" in str(excinfo.value)


def test_no_loan_candidate_that_borrows_raises():
    with pytest.raises(ValidationError):
        Candidate(
            candidate_id="c-bad2",
            strategy=FinancingStrategy.LIQUIDATE_100,
            required_amount=2_000_000.0,
            loan_amount=500_000.0,
            emi=0.0,
            total_interest=0.0,
            total_repayment=0.0,
            liquidation_amount=1_500_000.0,
            volatile_liquidation_amount=0.0,
            remaining_portfolio_value=300_000.0,
            resulting_liquidity_ratio=0.4,
            resulting_debt_burden_ratio=0.1,
            affordability_headroom=53_000.0,
        )


def test_infeasible_candidate_requires_a_reason():
    with pytest.raises(ValidationError):
        _borrowing_candidate(feasible=False)


def test_feasible_candidate_must_not_carry_an_infeasibility_reason():
    with pytest.raises(ValidationError):
        _borrowing_candidate(
            feasible=True,
            infeasibility_reason=MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY,
        )


def test_infeasible_candidate_is_marked_not_deleted():
    candidate = _borrowing_candidate(
        feasible=False,
        infeasibility_reason=MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY,
    )
    assert candidate.feasible is False
    assert candidate.infeasibility_reason is MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY


# ------------------------------------------------------------ scoring / policy


def test_suitability_above_one_raises():
    with pytest.raises(ValidationError):
        ScoredCandidate(candidate=_borrowing_candidate(), suitability=1.4, rank=1)


def test_scored_candidate_allows_null_suitability_for_fallback():
    scored = ScoredCandidate(candidate=_borrowing_candidate(), rank=1)
    assert scored.suitability is None
    assert scored.raw_ranker_margin is None


def test_failed_validation_must_name_the_check():
    with pytest.raises(ValidationError):
        ValidationResult(passed=False)


def test_passed_validation_constructs():
    assert ValidationResult(passed=True).failed_check is None


def test_blocked_guardrail_must_name_rule_and_reason():
    with pytest.raises(ValidationError):
        GuardrailResult(allowed=False, violated_rule="max_debt_burden_ratio")


def test_blocked_guardrail_records_cap_and_observed():
    result = GuardrailResult(
        allowed=False,
        violated_rule="max_debt_burden_ratio",
        reason_code=MismatchReasonCode.DEBT_BURDEN_CAP_EXCEEDED,
        cap_value=0.35,
        observed_value=0.48,
    )
    assert result.cap_value == 0.35
    assert result.observed_value == 0.48


# ------------------------------------------------------------- recommendation


def _minimal_trace(
    status: RecommendationStatus,
    source: RecommendationSource,
    coverage: CatalogueCoverage,
) -> DecisionTrace:
    return DecisionTrace(
        user_id="cust-0001",
        financial_metrics=FinancialMetrics(
            monthly_income=120_000.0,
            monthly_expenses=55_000.0,
            existing_emi=12_000.0,
            disposable_income=53_000.0,
            debt_burden_ratio=0.10,
            expense_ratio=0.46,
            emi_affordability_ceiling=26_500.0,
            income_stability_score=0.8,
            financial_health=FinancialHealth.GOOD,
        ),
        portfolio_metrics=PortfolioMetrics(
            has_portfolio=False,
            total_value=0.0,
            liquid_value=0.0,
            liquidity_ratio=0.0,
            equity_exposure=0.0,
            debt_exposure=0.0,
            crypto_exposure=0.0,
            concentration_risk=0.0,
            unrealized_gain_loss=0.0,
            portfolio_risk=PortfolioRisk.CONSERVATIVE,
        ),
        personalization=PersonalizationContext(is_cold_start=True),
        eligibility=[
            EligibilityResult(product_id="HL-001", status=EligibilityStatus.ELIGIBLE)
        ],
        candidate_counts=CandidateGenerationCounts(
            generated=10, infeasible=2, dominance_pruned=3, capped=0, surviving=5
        ),
        risk=RiskPrediction(
            risk_class=RiskClass.LOW,
            probability_of_default=0.04,
            model_version="risk-2.0.0",
        ),
        ranked_candidates=[],
        validation_walk=[],
        selection_stop_reason="test fixture",
        coverage=coverage,
        recommendation_status=status,
        recommendation_source=source,
        config_version="2.0.0",
        feature_version="2.0.0",
        prompt_version="2.0.0",
        labeling_policy_version="2.0.0",
        risk_model_version="risk-2.0.0",
        recommender_model_version="rec-2.0.0",
    )


def _coverage(above_threshold: int = 0) -> CatalogueCoverage:
    return CatalogueCoverage(
        catalogue_products=6,
        products_passing_eligibility=4,
        products_with_feasible_candidates=4,
        candidates_generated=86,
        candidates_infeasible=12,
        candidates_dominance_pruned=20,
        candidates_scored=86,
        candidates_above_suitability_threshold=above_threshold,
    )


def test_no_suitable_loan_with_no_candidate_is_valid():
    """The mismatch result is a first-class shape, not an error."""
    coverage = _coverage(0)
    recommendation = Recommendation(
        status=RecommendationStatus.NO_SUITABLE_LOAN,
        source=RecommendationSource.ML_RANKER,
        coverage=coverage,
        decision_trace=_minimal_trace(
            RecommendationStatus.NO_SUITABLE_LOAN,
            RecommendationSource.ML_RANKER,
            coverage,
        ),
    )
    assert recommendation.selected_candidate is None
    assert recommendation.status is RecommendationStatus.NO_SUITABLE_LOAN
    assert recommendation.coverage.candidates_above_suitability_threshold == 0


def test_recommended_without_a_candidate_raises():
    coverage = _coverage(4)
    with pytest.raises(ValidationError):
        Recommendation(
            status=RecommendationStatus.RECOMMENDED,
            source=RecommendationSource.ML_RANKER,
            coverage=coverage,
            decision_trace=_minimal_trace(
                RecommendationStatus.RECOMMENDED,
                RecommendationSource.ML_RANKER,
                coverage,
            ),
        )


def test_non_recommended_status_with_a_candidate_raises():
    """Never manufacture a recommendation to avoid saying NO_SUITABLE_LOAN."""
    coverage = _coverage(0)
    with pytest.raises(ValidationError):
        Recommendation(
            status=RecommendationStatus.NO_SUITABLE_LOAN,
            source=RecommendationSource.ML_RANKER,
            selected_candidate=_borrowing_candidate(),
            coverage=coverage,
            decision_trace=_minimal_trace(
                RecommendationStatus.NO_SUITABLE_LOAN,
                RecommendationSource.ML_RANKER,
                coverage,
            ),
        )


def test_recommended_with_a_candidate_constructs():
    coverage = _coverage(4)
    recommendation = Recommendation(
        status=RecommendationStatus.RECOMMENDED,
        source=RecommendationSource.ML_RANKER,
        selected_candidate=_borrowing_candidate(),
        ml_suitability=0.87,
        coverage=coverage,
        decision_trace=_minimal_trace(
            RecommendationStatus.RECOMMENDED,
            RecommendationSource.ML_RANKER,
            coverage,
        ),
    )
    assert recommendation.ml_suitability == 0.87
    assert recommendation.selected_candidate.product_id == "HL-001"


def test_fallback_source_forbids_an_ml_suitability_value():
    """In fallback mode the ML suitability field is null, never a rescaled score."""
    coverage = _coverage(4)
    with pytest.raises(ValidationError):
        Recommendation(
            status=RecommendationStatus.RECOMMENDED,
            source=RecommendationSource.DETERMINISTIC_FALLBACK,
            selected_candidate=_borrowing_candidate(),
            ml_suitability=0.72,
            coverage=coverage,
            decision_trace=_minimal_trace(
                RecommendationStatus.RECOMMENDED,
                RecommendationSource.DETERMINISTIC_FALLBACK,
                coverage,
            ),
        )


def test_fallback_can_still_be_recommended():
    """Status and source are independent axes."""
    coverage = _coverage(4)
    recommendation = Recommendation(
        status=RecommendationStatus.RECOMMENDED,
        source=RecommendationSource.DETERMINISTIC_FALLBACK,
        selected_candidate=_borrowing_candidate(),
        coverage=coverage,
        decision_trace=_minimal_trace(
            RecommendationStatus.RECOMMENDED,
            RecommendationSource.DETERMINISTIC_FALLBACK,
            coverage,
        ),
    )
    assert recommendation.source is RecommendationSource.DETERMINISTIC_FALLBACK
    assert recommendation.ml_suitability is None


# ------------------------------------------------------------------ contracts


def test_status_enum_has_no_fallback_member():
    """A fallback is a source, never a status (CONTEXT.md 5.2/5.3)."""
    assert "DETERMINISTIC_FALLBACK" not in {m.name for m in RecommendationStatus}
    assert len(list(RecommendationStatus)) == 5


def test_source_enum_has_exactly_two_members():
    assert {m.name for m in RecommendationSource} == {
        "ML_RANKER",
        "DETERMINISTIC_FALLBACK",
    }


def test_every_context_mismatch_reason_code_exists():
    expected = {
        "CREDIT_SCORE_BELOW_MINIMUM",
        "INCOME_BELOW_MINIMUM",
        "AMOUNT_ABOVE_PRODUCT_MAX",
        "AMOUNT_BELOW_PRODUCT_MIN",
        "TENURE_OUT_OF_RANGE",
        "PURPOSE_NOT_SUPPORTED",
        "EMI_EXCEEDS_AFFORDABILITY",
        "DEBT_BURDEN_CAP_EXCEEDED",
        "LOAN_TO_INCOME_CAP_EXCEEDED",
        "LIQUIDATION_EXCEEDS_PORTFOLIO",
        "LIQUIDATION_SHARE_CAP_EXCEEDED",
        "VOLATILE_ASSET_LIQUIDATION_PROHIBITED",
        "SUITABILITY_BELOW_THRESHOLD",
        "REQUIRED_AMOUNT_UNREACHABLE",
    }
    assert {m.name for m in MismatchReasonCode} == expected


def test_six_financing_strategies_exist():
    assert len(list(FinancingStrategy)) == 6
