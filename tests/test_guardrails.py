"""
Guardrail policy validator (P6).

Candidates are constructed directly so each cap can be violated in isolation. Nothing
here reads data/ or needs a model.
"""

import pytest

from app.config import settings
from app.core.candidates import generate_candidates
from app.core.eligibility import check_eligibility
from app.core.finance_math import MONTHS_PER_YEAR
from app.core.financial import analyze_financials
from app.core.guardrails import (
    check_guardrails,
    liquidation_share,
    loan_to_income_multiple,
)
from app.core.portfolio import analyze_portfolio
from app.schemas import Candidate, PortfolioMetrics
from app.schemas.enums import (
    EligibilityStatus,
    FinancingStrategy,
    GuardrailRule,
    MismatchReasonCode,
    PortfolioRisk,
    RiskAppetite,
)
from tests import fixtures

METRICS = analyze_financials(fixtures.standard_customer())  # income 120,000
PORTFOLIO = analyze_portfolio(fixtures.mixed_portfolio())  # total 2,300,000
NO_PORTFOLIO = analyze_portfolio(fixtures.empty_portfolio())


def _candidate(
    *,
    loan_amount: float = 500_000.0,
    debt_burden: float = 0.20,
    remaining_portfolio: float = 2_300_000.0,
    volatile_liquidated: float = 0.0,
    liquidation_amount: float = 0.0,
) -> Candidate:
    """A candidate that passes every cap unless an argument is set to break one."""
    return Candidate(
        candidate_id="c-test",
        product_id="HL-001",
        lender="Meridian Bank",
        tenure_months=120,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=2_000_000.0,
        loan_amount=loan_amount,
        emi=6_200.0,
        total_interest=244_000.0,
        total_repayment=744_000.0,
        liquidation_amount=liquidation_amount,
        volatile_liquidation_amount=volatile_liquidated,
        remaining_portfolio_value=remaining_portfolio,
        resulting_liquidity_ratio=0.5,
        resulting_debt_burden_ratio=debt_burden,
        affordability_headroom=20_300.0,
    )


def _check(candidate, appetite=RiskAppetite.CONSERVATIVE, portfolio=PORTFOLIO):
    return check_guardrails(appetite, METRICS, portfolio, candidate)


# ------------------------------------------------------------- the happy path


def test_a_compliant_candidate_is_allowed():
    result = _check(_candidate())
    assert result.allowed is True
    assert result.violated_rule is None
    assert result.reason_code is None


def test_an_allowed_result_carries_no_cap_or_observed_value():
    result = _check(_candidate())
    assert result.cap_value is None
    assert result.observed_value is None


# ------------------------------------------------- each cap, violated in isolation


def test_debt_burden_cap_violation():
    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    observed = caps.max_debt_burden_ratio + 0.05
    result = _check(_candidate(debt_burden=observed))
    assert result.allowed is False
    assert result.violated_rule == GuardrailRule.MAX_DEBT_BURDEN_RATIO.value
    assert result.reason_code is MismatchReasonCode.DEBT_BURDEN_CAP_EXCEEDED
    assert result.cap_value == caps.max_debt_burden_ratio
    assert result.observed_value == pytest.approx(observed)


def test_debt_burden_exactly_at_the_cap_is_allowed():
    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    assert _check(_candidate(debt_burden=caps.max_debt_burden_ratio)).allowed is True


def test_loan_to_income_cap_violation():
    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    annual_income = METRICS.monthly_income * MONTHS_PER_YEAR
    loan = annual_income * (caps.max_loan_to_income_multiple + 1.0)
    result = _check(_candidate(loan_amount=loan))
    assert result.allowed is False
    assert result.violated_rule == GuardrailRule.MAX_LOAN_TO_INCOME_MULTIPLE.value
    assert result.reason_code is MismatchReasonCode.LOAN_TO_INCOME_CAP_EXCEEDED
    assert result.cap_value == caps.max_loan_to_income_multiple
    assert result.observed_value == pytest.approx(
        caps.max_loan_to_income_multiple + 1.0
    )


def test_loan_to_income_is_measured_against_annual_income():
    """
    The easiest thing in this module to get backwards. A 500,000 loan against a
    120,000 monthly income is 0.35x ANNUAL, not 4.17x monthly — and the configured
    caps of 8/12/18 are only sensible read the first way.
    """
    candidate = _candidate(loan_amount=500_000.0)
    assert loan_to_income_multiple(METRICS, candidate) == pytest.approx(
        500_000.0 / (120_000.0 * 12)
    )
    assert loan_to_income_multiple(METRICS, candidate) < 1.0


def test_a_realistic_home_loan_is_not_blocked_by_loan_to_income():
    """The regression this cap would cause if it were read as monthly income."""
    candidate = _candidate(loan_amount=2_000_000.0)
    result = _check(candidate, RiskAppetite.CONSERVATIVE)
    assert result.allowed is True


def test_liquidation_share_cap_violation():
    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    # Consume more of the portfolio than the conservative cap permits.
    share = caps.max_liquidation_share + 0.10
    remaining = PORTFOLIO.total_value * (1.0 - share)
    result = _check(
        _candidate(remaining_portfolio=remaining, liquidation_amount=500_000.0)
    )
    assert result.allowed is False
    assert result.violated_rule == GuardrailRule.MAX_LIQUIDATION_SHARE.value
    assert result.reason_code is MismatchReasonCode.LIQUIDATION_SHARE_CAP_EXCEEDED
    assert result.cap_value == caps.max_liquidation_share
    assert result.observed_value == pytest.approx(share)


def test_liquidation_share_is_measured_gross_of_the_haircut():
    """
    The cap asks how much LEAVES the portfolio. The customer loses the haircut too,
    so the net funding contribution would understate it.
    """
    candidate = _candidate(
        remaining_portfolio=PORTFOLIO.total_value - 500_000.0,
        liquidation_amount=480_000.0,
    )
    assert liquidation_share(PORTFOLIO, candidate) == pytest.approx(
        500_000.0 / PORTFOLIO.total_value
    )
    assert liquidation_share(PORTFOLIO, candidate) > (
        candidate.liquidation_amount / PORTFOLIO.total_value
    )


def test_volatile_liquidation_prohibited_for_conservative():
    result = _check(
        _candidate(
            volatile_liquidated=100_000.0,
            remaining_portfolio=PORTFOLIO.total_value - 100_000.0,
            liquidation_amount=95_000.0,
        )
    )
    assert result.allowed is False
    assert result.violated_rule == GuardrailRule.VOLATILE_ASSET_LIQUIDATION.value
    assert (
        result.reason_code
        is MismatchReasonCode.VOLATILE_ASSET_LIQUIDATION_PROHIBITED
    )
    assert result.cap_value == 0.0
    assert result.observed_value == 100_000.0


def test_volatile_liquidation_allowed_for_aggressive():
    result = _check(
        _candidate(
            volatile_liquidated=100_000.0,
            remaining_portfolio=PORTFOLIO.total_value - 100_000.0,
            liquidation_amount=95_000.0,
        ),
        RiskAppetite.AGGRESSIVE,
    )
    assert result.allowed is True


def test_zero_volatile_liquidation_never_triggers_the_prohibition():
    assert _check(_candidate(volatile_liquidated=0.0)).allowed is True


# ------------------------------------------------------- appetite differentiates


def test_conservative_blocks_a_high_leverage_candidate_that_aggressive_permits():
    conservative = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    aggressive = settings.GUARDRAIL_CAPS[RiskAppetite.AGGRESSIVE]
    # Between the two debt-burden caps.
    burden = (conservative.max_debt_burden_ratio + aggressive.max_debt_burden_ratio) / 2
    candidate = _candidate(debt_burden=burden)

    blocked = _check(candidate, RiskAppetite.CONSERVATIVE)
    permitted = _check(candidate, RiskAppetite.AGGRESSIVE)
    assert blocked.allowed is False
    assert blocked.reason_code is MismatchReasonCode.DEBT_BURDEN_CAP_EXCEEDED
    assert permitted.allowed is True


def test_moderate_sits_between_conservative_and_aggressive():
    caps = settings.GUARDRAIL_CAPS
    burden = (
        caps[RiskAppetite.CONSERVATIVE].max_debt_burden_ratio
        + caps[RiskAppetite.MODERATE].max_debt_burden_ratio
    ) / 2
    candidate = _candidate(debt_burden=burden)
    assert _check(candidate, RiskAppetite.CONSERVATIVE).allowed is False
    assert _check(candidate, RiskAppetite.MODERATE).allowed is True


def test_every_risk_appetite_has_a_configured_cap_set():
    assert set(settings.GUARDRAIL_CAPS) == set(RiskAppetite)


def test_caps_are_ordered_by_permissiveness():
    caps = settings.GUARDRAIL_CAPS
    for attribute in (
        "max_debt_burden_ratio",
        "max_liquidation_share",
        "max_loan_to_income_multiple",
    ):
        conservative = getattr(caps[RiskAppetite.CONSERVATIVE], attribute)
        moderate = getattr(caps[RiskAppetite.MODERATE], attribute)
        aggressive = getattr(caps[RiskAppetite.AGGRESSIVE], attribute)
        assert conservative < moderate < aggressive, attribute


# -------------------------------------------------------------- no portfolio


def test_no_portfolio_borrow_only_candidate_is_evaluated_normally():
    candidate = _candidate(remaining_portfolio=0.0)
    result = check_guardrails(
        RiskAppetite.CONSERVATIVE, METRICS, NO_PORTFOLIO, candidate
    )
    assert result.allowed is True


def test_no_portfolio_cannot_trigger_the_liquidation_share_cap():
    """Consuming none of nothing is a share of zero, not a division by zero."""
    candidate = _candidate(remaining_portfolio=0.0)
    assert liquidation_share(NO_PORTFOLIO, candidate) == 0.0
    assert (
        check_guardrails(
            RiskAppetite.CONSERVATIVE, METRICS, NO_PORTFOLIO, candidate
        ).allowed
        is True
    )


def test_no_portfolio_still_enforces_the_income_and_burden_caps():
    """The caps that do not depend on holdings must still fire."""
    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    candidate = _candidate(
        remaining_portfolio=0.0, debt_burden=caps.max_debt_burden_ratio + 0.10
    )
    result = check_guardrails(
        RiskAppetite.CONSERVATIVE, METRICS, NO_PORTFOLIO, candidate
    )
    assert result.allowed is False
    assert result.reason_code is MismatchReasonCode.DEBT_BURDEN_CAP_EXCEEDED


def test_a_zero_value_portfolio_metrics_block_is_safe():
    empty = PortfolioMetrics(
        has_portfolio=False,
        total_value=0.0,
        allocation={},
        liquid_value=0.0,
        liquidity_ratio=0.0,
        equity_exposure=0.0,
        debt_exposure=0.0,
        crypto_exposure=0.0,
        concentration_risk=0.0,
        unrealized_gain_loss=0.0,
        portfolio_risk=PortfolioRisk.CONSERVATIVE,
    )
    assert liquidation_share(empty, _candidate(remaining_portfolio=0.0)) == 0.0


# ------------------------------------------------------ deterministic rule order


def test_the_same_input_names_the_same_rule_twice():
    candidate = _candidate(
        debt_burden=0.90,
        loan_amount=50_000_000.0,
        remaining_portfolio=0.0,
        volatile_liquidated=500_000.0,
        liquidation_amount=1_000_000.0,
    )
    first = _check(candidate)
    second = _check(candidate)
    assert first == second
    assert first.violated_rule == second.violated_rule


def test_the_first_rule_in_configured_order_wins_when_several_are_violated():
    """All four caps broken at once — the configured order decides which is named."""
    candidate = _candidate(
        debt_burden=0.90,
        loan_amount=50_000_000.0,
        remaining_portfolio=0.0,
        volatile_liquidated=500_000.0,
        liquidation_amount=1_000_000.0,
    )
    result = _check(candidate)
    assert result.violated_rule == settings.GUARDRAIL_RULE_ORDER[0].value


def test_rule_order_is_honoured_when_the_first_rule_passes():
    """With the debt-burden cap satisfied, the next configured rule is the one named."""
    candidate = _candidate(
        debt_burden=0.10,
        loan_amount=50_000_000.0,
        remaining_portfolio=0.0,
        volatile_liquidated=500_000.0,
    )
    assert _check(candidate).violated_rule == settings.GUARDRAIL_RULE_ORDER[1].value


def test_every_rule_in_the_configured_order_is_evaluable():
    """A rule with no evaluation would silently never fire."""
    from app.core.guardrails import _evaluate

    caps = settings.GUARDRAIL_CAPS[RiskAppetite.CONSERVATIVE]
    for rule in settings.GUARDRAIL_RULE_ORDER:
        _evaluate(rule, caps, METRICS, PORTFOLIO, _candidate())


def test_configured_order_covers_every_defined_rule():
    assert set(settings.GUARDRAIL_RULE_ORDER) == set(GuardrailRule)


def test_every_rule_maps_to_a_distinct_reason_code():
    from app.core.guardrails import _REASON_FOR_RULE

    assert set(_REASON_FOR_RULE) == set(GuardrailRule)
    assert len(set(_REASON_FOR_RULE.values())) == len(GuardrailRule)


# ---------------------------------------------------- pass/fail, never filtering


def test_the_module_never_filters_a_list():
    """
    Guardrails validate ONE candidate. A function taking or returning a list here
    could delete an option, which is exactly what this layer must not do.
    """
    import inspect

    import app.core.guardrails as guardrails

    signature = inspect.signature(guardrails.check_guardrails)
    for parameter in signature.parameters.values():
        assert "list" not in str(parameter.annotation).lower()
    assert "GuardrailResult" in str(signature.return_annotation)


def test_the_candidate_is_not_modified():
    candidate = _candidate(debt_burden=0.90)
    before = candidate.model_dump()
    _check(candidate)
    assert candidate.model_dump() == before


def test_guardrails_apply_cleanly_to_real_generated_candidates():
    """End to end over P5's output: every candidate gets a verdict, none is dropped."""
    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    catalogue = fixtures.mock_catalogue()
    metrics = analyze_financials(customer)
    outcomes = check_eligibility(customer, metrics, requirement, catalogue)
    eligible_ids = {
        r.product_id for r in outcomes if r.status is EligibilityStatus.ELIGIBLE
    }
    portfolio = analyze_portfolio(fixtures.mixed_portfolio())
    generated = generate_candidates(
        requirement,
        metrics,
        portfolio,
        [p for p in catalogue if p.product_id in eligible_ids],
    )

    verdicts = [
        check_guardrails(requirement.risk_appetite, metrics, portfolio, candidate)
        for candidate in generated.candidates
    ]
    assert len(verdicts) == len(generated.candidates)
    for verdict in verdicts:
        if verdict.allowed:
            assert verdict.violated_rule is None
        else:
            assert verdict.violated_rule is not None
            assert verdict.reason_code is not None


def test_conservative_blocks_more_real_candidates_than_aggressive():
    """The appetite genuinely changes outcomes on the real option space."""
    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    catalogue = fixtures.mock_catalogue()
    metrics = analyze_financials(customer)
    outcomes = check_eligibility(customer, metrics, requirement, catalogue)
    eligible_ids = {
        r.product_id for r in outcomes if r.status is EligibilityStatus.ELIGIBLE
    }
    portfolio = analyze_portfolio(fixtures.mixed_portfolio())
    candidates = generate_candidates(
        requirement,
        metrics,
        portfolio,
        [p for p in catalogue if p.product_id in eligible_ids],
    ).candidates

    def blocked(appetite):
        return sum(
            1
            for c in candidates
            if not check_guardrails(appetite, metrics, portfolio, c).allowed
        )

    assert blocked(RiskAppetite.CONSERVATIVE) > blocked(RiskAppetite.AGGRESSIVE)
