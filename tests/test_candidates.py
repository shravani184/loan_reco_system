"""
Finance math and candidate generation (P5).

Nothing here reads data/ or needs a model. The EMI reference values are the standard
published figures for the loans named in each test.
"""

import pytest

from app.config import settings
from app.core.candidates import (
    NO_LOAN_CANDIDATE_ID,
    _prune_dominated,
    generate_candidates,
)
from app.core.eligibility import check_eligibility
from app.core.finance_math import emi, total_interest, total_repayment
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.schemas import Candidate
from app.schemas.enums import (
    EligibilityStatus,
    FinancingStrategy,
    MismatchReasonCode,
)
from tests import fixtures


def _eligible_products(customer, requirement, catalogue):
    outcomes = check_eligibility(
        customer, analyze_financials(customer), requirement, catalogue
    )
    eligible_ids = {
        r.product_id for r in outcomes if r.status is EligibilityStatus.ELIGIBLE
    }
    return [p for p in catalogue if p.product_id in eligible_ids]


def _generate(customer=None, requirement=None, portfolio=None, catalogue=None):
    customer = customer or fixtures.standard_customer()
    requirement = requirement or fixtures.standard_requirement()
    catalogue = catalogue if catalogue is not None else fixtures.mock_catalogue()
    portfolio = fixtures.mixed_portfolio() if portfolio is None else portfolio
    return generate_candidates(
        requirement,
        analyze_financials(customer),
        analyze_portfolio(portfolio),
        _eligible_products(customer, requirement, catalogue),
    )


# ============================================================== finance math


def test_emi_matches_a_hand_computed_value():
    """1,000,000 at 10% over 12 months is the standard 87,915.89."""
    assert emi(1_000_000.0, 10.0, 12) == pytest.approx(87_915.89, abs=0.01)


def test_emi_matches_a_second_hand_computed_value():
    """500,000 at 12% over 24 months is 23,536.74."""
    assert emi(500_000.0, 12.0, 24) == pytest.approx(23_536.74, abs=0.01)


def test_emi_with_zero_interest_rate_is_principal_over_tenure():
    assert emi(120_000.0, 0.0, 12) == pytest.approx(10_000.0)
    assert emi(1_000_000.0, 0.0, 100) == pytest.approx(10_000.0)


def test_zero_interest_loan_costs_no_interest():
    assert total_interest(120_000.0, 0.0, 12) == pytest.approx(0.0)
    assert total_repayment(120_000.0, 0.0, 12) == pytest.approx(120_000.0)


def test_zero_principal_borrows_and_repays_nothing():
    """The no-loan candidate, not a degenerate loan."""
    assert emi(0.0, 8.5, 120) == 0.0
    assert total_interest(0.0, 8.5, 120) == 0.0
    assert total_repayment(0.0, 8.5, 120) == 0.0


def test_total_repayment_is_emi_times_tenure():
    assert total_repayment(1_000_000.0, 10.0, 12) == pytest.approx(
        emi(1_000_000.0, 10.0, 12) * 12
    )


def test_total_interest_is_repayment_less_principal():
    assert total_interest(1_000_000.0, 10.0, 12) == pytest.approx(
        total_repayment(1_000_000.0, 10.0, 12) - 1_000_000.0
    )


def test_total_interest_is_never_negative():
    assert total_interest(1_000_000.0, 0.0, 360) >= 0.0


@pytest.mark.parametrize("tenure", [0, -12])
def test_non_positive_tenure_raises(tenure):
    with pytest.raises(ValueError):
        emi(100_000.0, 10.0, tenure)


def test_negative_principal_raises():
    with pytest.raises(ValueError):
        emi(-1.0, 10.0, 12)


def test_longer_tenure_lowers_emi_and_raises_total_interest():
    """Monotonicity in both directions, over the whole configured tenure grid."""
    emis = [emi(2_000_000.0, 9.0, t) for t in settings.CANDIDATE_TENURE_OPTIONS_MONTHS]
    interests = [
        total_interest(2_000_000.0, 9.0, t)
        for t in settings.CANDIDATE_TENURE_OPTIONS_MONTHS
    ]
    assert emis == sorted(emis, reverse=True)
    assert interests == sorted(interests)


def test_higher_rate_raises_emi():
    assert emi(1_000_000.0, 12.0, 60) > emi(1_000_000.0, 8.0, 60)


def test_larger_principal_raises_emi_proportionally():
    """EMI is linear in principal, which is what makes scale invariance hold."""
    assert emi(2_000_000.0, 9.0, 60) == pytest.approx(2.0 * emi(1_000_000.0, 9.0, 60))


def test_exactly_one_emi_implementation_under_app():
    """
    Two implementations of EMI is a defect even if they agree. Only finance_math.py
    may contain the formula; everything else imports it.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in (root / "app").rglob("*.py"):
        if path.name == "finance_math.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "def emi(" in text or "/ 12 / 100" in text or "/ 12.0 / 100" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"a second EMI implementation exists in {offenders}"


# ======================================================== candidate generation


def test_generation_produces_candidates_for_the_standard_customer():
    result = _generate()
    assert result.counts.generated > 0
    assert result.counts.surviving > 0
    assert any(c.feasible for c in result.candidates)


def test_every_candidate_is_fully_specified():
    for candidate in _generate().candidates:
        if candidate.strategy is FinancingStrategy.LIQUIDATE_100:
            assert candidate.product_id is None and candidate.tenure_months is None
        else:
            assert candidate.product_id is not None
            assert candidate.lender is not None
            assert candidate.tenure_months is not None


def test_candidate_ids_are_unique():
    ids = [c.candidate_id for c in _generate().candidates]
    assert len(ids) == len(set(ids))


def test_emi_on_a_candidate_matches_the_canonical_formula():
    """P12 re-verifies against this same function, so they must already agree."""
    for candidate in _generate().candidates:
        if candidate.tenure_months is None:
            assert candidate.emi == 0.0
            continue
        product = next(
            p
            for p in fixtures.mock_catalogue()
            if p.product_id == candidate.product_id
        )
        assert candidate.emi == pytest.approx(
            emi(candidate.loan_amount, product.annual_rate, candidate.tenure_months)
        )


def test_candidates_stay_within_product_amount_and_tenure_limits():
    for candidate in _generate().candidates:
        if candidate.product_id is None:
            continue
        product = next(
            p
            for p in fixtures.mock_catalogue()
            if p.product_id == candidate.product_id
        )
        assert product.min_amount <= candidate.loan_amount <= product.max_amount
        assert (
            product.min_tenure_months
            <= candidate.tenure_months
            <= product.max_tenure_months
        )


def test_the_customers_preferred_tenure_is_in_the_option_space():
    preferred = fixtures.standard_requirement().preferred_tenure_months
    tenures = {c.tenure_months for c in _generate().candidates}
    assert preferred in tenures


def test_higher_liquidation_lowers_loan_amount_and_emi():
    """Same product, same tenure, same funded amount — only the split differs."""
    result = _generate()
    by_strategy = {}
    for candidate in result.candidates:
        if (
            candidate.product_id == "HL-002"
            and candidate.tenure_months == 120
            and candidate.loan_amount + candidate.liquidation_amount
            == pytest.approx(2_000_000.0)
        ):
            by_strategy[candidate.strategy] = candidate

    borrow_share = settings.CANDIDATE_STRATEGY_BORROW_SHARE
    ordered = sorted(by_strategy, key=lambda s: borrow_share[s], reverse=True)
    assert len(ordered) >= 3, "need several splits to compare"

    loans = [by_strategy[s].loan_amount for s in ordered]
    emis = [by_strategy[s].emi for s in ordered]
    liquidations = [by_strategy[s].liquidation_amount for s in ordered]
    assert loans == sorted(loans, reverse=True)
    assert emis == sorted(emis, reverse=True)
    assert liquidations == sorted(liquidations)


def test_resulting_debt_burden_includes_the_new_emi():
    metrics = analyze_financials(fixtures.standard_customer())
    for candidate in _generate().candidates:
        expected = (metrics.existing_emi + candidate.emi) / metrics.monthly_income
        assert candidate.resulting_debt_burden_ratio == pytest.approx(expected)


def test_affordability_headroom_is_ceiling_less_emi():
    metrics = analyze_financials(fixtures.standard_customer())
    for candidate in _generate().candidates:
        assert candidate.affordability_headroom == pytest.approx(
            metrics.emi_affordability_ceiling - candidate.emi
        )


# ------------------------------------------------------------ the haircut


def test_liquidation_applies_the_haircut_so_more_is_sold_than_is_raised():
    """
    P2 left liquid_value gross precisely so the haircut is applied HERE. If it were
    not, gross sold would equal the funding contribution.
    """
    result = _generate()
    liquidating = [
        c
        for c in result.candidates
        if c.liquidation_amount > 0.0 and c.remaining_portfolio_value > 0.0
    ]
    assert liquidating, "expected liquidating candidates"
    portfolio_total = analyze_portfolio(fixtures.mixed_portfolio()).total_value
    for candidate in liquidating:
        gross_sold = portfolio_total - candidate.remaining_portfolio_value
        assert gross_sold > candidate.liquidation_amount


def test_cheapest_holdings_are_sold_first():
    """
    A small liquidation is funded entirely from cash (haircut 0.00), so no volatile
    holding is touched.
    """
    requirement = fixtures.standard_requirement().model_copy(
        update={"required_amount": 600_000.0}
    )
    result = _generate(requirement=requirement)
    small = [
        c
        for c in result.candidates
        if 0.0 < c.liquidation_amount <= 120_000.0
    ]
    assert small, "expected a small liquidation"
    assert all(c.volatile_liquidation_amount == 0.0 for c in small)


def test_a_large_liquidation_reaches_volatile_holdings():
    result = _generate()
    large = [c for c in result.candidates if c.liquidation_amount >= 1_500_000.0]
    assert large, "expected a large liquidation"
    assert any(c.volatile_liquidation_amount > 0.0 for c in large)


def test_volatile_liquidation_is_reported_not_refused():
    """
    Whether volatile assets MAY be sold is P6's policy question. P5 reports the
    amount so the guardrail has something to check.
    """
    result = _generate()
    assert any(c.volatile_liquidation_amount > 0.0 for c in result.candidates)


# ------------------------------------------------------------- feasibility


def test_infeasible_candidates_are_returned_marked_not_dropped():
    """A customer who can afford almost nothing still gets a full option space."""
    poor = fixtures.standard_customer().model_copy(
        update={"monthly_expenses": 118_000.0, "existing_emi": 0.0}
    )
    result = _generate(customer=poor)
    infeasible = [c for c in result.candidates if not c.feasible]
    assert infeasible, "expected infeasible candidates to be returned"
    assert result.counts.infeasible == len(infeasible)
    assert all(c.infeasibility_reason is not None for c in infeasible)


def test_emi_above_the_ceiling_is_marked_emi_exceeds_affordability():
    poor = fixtures.standard_customer().model_copy(
        update={"monthly_expenses": 118_000.0, "existing_emi": 0.0}
    )
    metrics = analyze_financials(poor)
    result = _generate(customer=poor)
    for candidate in result.candidates:
        if candidate.emi > metrics.emi_affordability_ceiling:
            assert candidate.feasible is False
            assert (
                candidate.infeasibility_reason
                is MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY
            )


def test_liquidation_beyond_the_portfolio_is_marked_not_dropped():
    """A tiny portfolio cannot fund the liquidating strategies."""
    tiny = fixtures.mixed_portfolio().model_copy(
        update={"holdings": fixtures.mixed_portfolio().holdings[:1]}
    )
    requirement = fixtures.standard_requirement()
    result = _generate(portfolio=tiny, requirement=requirement)
    blocked = [
        c
        for c in result.candidates
        if c.infeasibility_reason is MismatchReasonCode.LIQUIDATION_EXCEEDS_PORTFOLIO
    ]
    assert blocked, "expected liquidation-limited candidates"


def test_feasible_candidates_never_carry_an_infeasibility_reason():
    for candidate in _generate().candidates:
        assert candidate.feasible == (candidate.infeasibility_reason is None)


def test_counts_reconcile_with_the_returned_list():
    result = _generate()
    counts = result.counts
    assert counts.generated == (
        counts.infeasible + counts.dominance_pruned + counts.capped + counts.surviving
    )
    assert len(result.candidates) == counts.surviving + counts.infeasible


# ---------------------------------------------------------- the no portfolio


def test_no_portfolio_generates_only_full_borrow_candidates():
    result = _generate(portfolio=fixtures.empty_portfolio())
    assert result.candidates
    assert all(
        c.strategy is FinancingStrategy.BORROW_100 for c in result.candidates
    )


def test_no_portfolio_generates_no_no_loan_candidate():
    """There is nothing to liquidate, so paying from assets is not an option."""
    result = _generate(portfolio=fixtures.empty_portfolio())
    assert all(c.candidate_id != NO_LOAN_CANDIDATE_ID for c in result.candidates)


def test_no_portfolio_candidates_liquidate_nothing():
    for candidate in _generate(portfolio=fixtures.empty_portfolio()).candidates:
        assert candidate.liquidation_amount == 0.0
        assert candidate.volatile_liquidation_amount == 0.0
        assert candidate.remaining_portfolio_value == 0.0
        assert candidate.resulting_liquidity_ratio == 0.0


def test_no_portfolio_still_produces_feasible_candidates():
    result = _generate(portfolio=fixtures.empty_portfolio())
    assert any(c.feasible for c in result.candidates)


# ------------------------------------------------------------ the no-loan option


def test_the_no_loan_candidate_is_generated_exactly_once():
    """Phase R finding: once per CUSTOMER, not once per product x tenure."""
    result = _generate()
    no_loan = [
        c for c in result.candidates if c.strategy is FinancingStrategy.LIQUIDATE_100
    ]
    assert len(no_loan) == 1


def test_the_no_loan_candidate_borrows_nothing_and_is_not_a_one_month_loan():
    result = _generate()
    no_loan = next(
        c for c in result.candidates if c.strategy is FinancingStrategy.LIQUIDATE_100
    )
    assert no_loan.loan_amount == 0.0
    assert no_loan.emi == 0.0
    assert no_loan.total_interest == 0.0
    assert no_loan.product_id is None
    assert no_loan.lender is None
    assert no_loan.tenure_months is None


def test_the_no_loan_candidate_liquidates_the_full_requirement():
    result = _generate()
    no_loan = next(
        c for c in result.candidates if c.strategy is FinancingStrategy.LIQUIDATE_100
    )
    assert no_loan.liquidation_amount == pytest.approx(
        fixtures.standard_requirement().required_amount
    )


# -------------------------------------------------------- dominance pruning


def _candidate(
    candidate_id: str,
    emi_value: float,
    interest: float,
    remaining_portfolio: float,
    loan_amount: float = 1_000_000.0,
    product_id: str = "HL-001",
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        product_id=product_id,
        lender="Meridian Bank",
        tenure_months=120,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=2_000_000.0,
        loan_amount=loan_amount,
        emi=emi_value,
        total_interest=interest,
        total_repayment=loan_amount + interest,
        liquidation_amount=0.0,
        volatile_liquidation_amount=0.0,
        remaining_portfolio_value=remaining_portfolio,
        resulting_liquidity_ratio=0.5,
        resulting_debt_burden_ratio=0.3,
        affordability_headroom=1_000.0,
    )


PORTFOLIO_VALUE = 1_000_000.0


def test_pruning_removes_a_strictly_dominated_candidate():
    """B is worse on every axis, so it is objectively worse and is dropped."""
    dominator = _candidate("A", 10_000.0, 200_000.0, 1_000_000.0)
    dominated = _candidate("B", 12_000.0, 250_000.0, 900_000.0)
    kept = _prune_dominated([dominator, dominated], PORTFOLIO_VALUE)
    assert [c.candidate_id for c in kept] == ["A"]


def test_pruning_removes_a_candidate_worse_on_one_axis_and_equal_elsewhere():
    dominator = _candidate("A", 10_000.0, 200_000.0, 1_000_000.0)
    dominated = _candidate("B", 10_000.0, 200_001.0, 1_000_000.0)
    kept = _prune_dominated([dominator, dominated], PORTFOLIO_VALUE)
    assert [c.candidate_id for c in kept] == ["A"]


def test_pruning_keeps_a_candidate_that_trades_one_axis_for_another():
    """
    THIS IS THE TEST THAT PROVES PRUNING IS NOT RANKING. A has a lower EMI, B has
    lower total interest. Nothing here is entitled to decide which the customer
    cares about — that is the recommender's job — so both survive.
    """
    a = _candidate("A", 10_000.0, 300_000.0, 1_000_000.0)
    b = _candidate("B", 15_000.0, 200_000.0, 1_000_000.0)
    kept = _prune_dominated([a, b], PORTFOLIO_VALUE)
    assert {c.candidate_id for c in kept} == {"A", "B"}


def test_pruning_keeps_a_candidate_that_trades_cost_for_portfolio_impact():
    a = _candidate("A", 10_000.0, 200_000.0, 500_000.0)
    b = _candidate("B", 12_000.0, 260_000.0, 1_000_000.0)
    kept = _prune_dominated([a, b], PORTFOLIO_VALUE)
    assert {c.candidate_id for c in kept} == {"A", "B"}


def test_identical_candidates_are_both_kept():
    """A tie is not dominance, so pruning never deletes arbitrarily."""
    a = _candidate("A", 10_000.0, 200_000.0, 1_000_000.0)
    b = _candidate("B", 10_000.0, 200_000.0, 1_000_000.0)
    assert len(_prune_dominated([a, b], PORTFOLIO_VALUE)) == 2


def test_pruning_does_not_compare_across_products():
    """Different products are different offers, not competing configurations."""
    a = _candidate("A", 10_000.0, 200_000.0, 1_000_000.0, product_id="HL-001")
    b = _candidate("B", 12_000.0, 250_000.0, 900_000.0, product_id="HL-002")
    assert len(_prune_dominated([a, b], PORTFOLIO_VALUE)) == 2


def test_pruning_does_not_compare_across_loan_amounts():
    """A smaller loan is a different offer, not a worse version of a bigger one."""
    a = _candidate("A", 10_000.0, 200_000.0, 1_000_000.0, loan_amount=1_000_000.0)
    b = _candidate("B", 12_000.0, 250_000.0, 900_000.0, loan_amount=1_500_000.0)
    assert len(_prune_dominated([a, b], PORTFOLIO_VALUE)) == 2


def test_pruning_reduces_the_real_candidate_set():
    result = _generate()
    assert result.counts.dominance_pruned > 0


def test_pruned_candidates_are_absent_from_the_returned_feasible_set():
    result = _generate()
    feasible_returned = [c for c in result.candidates if c.feasible]
    assert len(feasible_returned) == result.counts.surviving


# -------------------------------------------------------------------- caps


def test_candidate_count_is_bounded_by_the_configured_caps():
    result = _generate()
    feasible = [c for c in result.candidates if c.feasible]
    assert len(feasible) <= settings.MAX_CANDIDATES_TOTAL
    per_product: dict[str | None, int] = {}
    for candidate in feasible:
        per_product[candidate.product_id] = (
            per_product.get(candidate.product_id, 0) + 1
        )
    for count in per_product.values():
        assert count <= settings.MAX_CANDIDATES_PER_PRODUCT


def test_generated_count_is_bounded_by_the_grid():
    """The enumeration is bounded brute force, not an open search."""
    catalogue = fixtures.mock_catalogue()
    requirement = fixtures.standard_requirement()
    products = _eligible_products(fixtures.standard_customer(), requirement, catalogue)
    max_tenures = len(settings.CANDIDATE_TENURE_OPTIONS_MONTHS) + 1
    ceiling = (
        len(products)
        * len(settings.CANDIDATE_AMOUNT_STEPS)
        * max_tenures
        * len(settings.CANDIDATE_STRATEGY_BORROW_SHARE)
    ) + 1  # +1 for the single no-loan candidate
    assert _generate().counts.generated <= ceiling


def test_generation_is_deterministic():
    first = _generate()
    second = _generate()
    assert [c.candidate_id for c in first.candidates] == [
        c.candidate_id for c in second.candidates
    ]
    assert first.counts == second.counts


def test_no_eligible_products_yields_only_the_no_loan_option():
    """With a portfolio but nothing to borrow from, paying from assets remains."""
    result = generate_candidates(
        fixtures.standard_requirement(),
        analyze_financials(fixtures.standard_customer()),
        analyze_portfolio(fixtures.mixed_portfolio()),
        [],
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].candidate_id == NO_LOAN_CANDIDATE_ID


def test_no_eligible_products_and_no_portfolio_yields_nothing():
    result = generate_candidates(
        fixtures.standard_requirement(),
        analyze_financials(fixtures.standard_customer()),
        analyze_portfolio(fixtures.empty_portfolio()),
        [],
    )
    assert result.candidates == []
    assert result.counts.generated == 0


# ------------------------------------------------------- no preference ordering


def test_module_defines_no_scoring_identifier():
    """
    The exit criterion: no preference ordering in this module. Checked against the
    AST — identifiers only, so the module's own prose about NOT having a utility
    function cannot satisfy or break it.
    """
    import ast
    import pathlib

    tree = ast.parse(
        (
            pathlib.Path(__file__).resolve().parent.parent
            / "app"
            / "core"
            / "candidates.py"
        ).read_text(encoding="utf-8")
    )
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)

    for banned in ("utility", "score", "rank", "preference", "priority"):
        offenders = [name for name in identifiers if banned in name.lower()]
        assert offenders == [], (
            f"candidates.py defines {offenders} — this module generates the option "
            "space and must not express a preference within it"
        )


def test_returned_order_is_enumeration_order_not_quality_order():
    """
    Behavioural proof that no preference ordering happened: the surviving feasible
    candidates come back in generation order, which is NOT monotone in EMI, interest
    or portfolio impact. A module that had ranked them would produce a sorted axis.
    """
    feasible = [c for c in _generate().candidates if c.feasible]
    assert len(feasible) > 5

    emis = [c.emi for c in feasible]
    interests = [c.total_interest for c in feasible]
    impacts = [c.remaining_portfolio_value for c in feasible]
    for axis in (emis, interests, impacts):
        assert axis != sorted(axis), "candidates came back ordered by a quality axis"
        assert axis != sorted(axis, reverse=True)
