"""
THE INVARIANT SUITE for the relevance labeling policy (P7).

Ported from spikes/labeling/test_invariants.py, rewritten against the real schemas.

These are properties ANY correct labeler must satisfy regardless of its coefficients.
They were written before the policy existed — deliberately — because invariants
written afterwards get shaped to fit the policy's bugs, which is the exact failure
this ordering prevents (CONTEXT.md 17.1).

Phase R planted seven realistic defects against the spike version of this suite and
three initially SURVIVED. The three tests marked "added after mutation testing" are
the ones that closed those gaps. Do not delete them and do not weaken them: a passing
invariant suite is not evidence until you have watched it fail.

If an invariant cannot be satisfied, that is a DESIGN FINDING. Report it and set the
phase BLOCKED. Never weaken the invariant to match the policy.
"""

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.candidates import generate_candidates
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.schemas import (
    Candidate,
    CustomerProfile,
    Holding,
    LoanProduct,
    LoanRequirement,
    Portfolio,
)
from app.schemas.enums import (
    AssetType,
    EmploymentType,
    FinancingStrategy,
    LoanPurpose,
    RiskAppetite,
)
from training.labeling import (
    build_context,
    grade_group,
    score_candidate,
    subscore_appetite,
    subscore_cost,
    subscore_portfolio_impact,
)

SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

PRODUCTS = [
    LoanProduct(
        product_id="P1",
        lender="Alpha",
        product_name="Alpha Flexi",
        purposes=[LoanPurpose.PERSONAL],
        annual_rate=9.5,
        min_amount=50_000.0,
        max_amount=80_000_000.0,
        min_tenure_months=12,
        max_tenure_months=84,
        min_credit_score=300,
        min_monthly_income=0.0,
        processing_fee_pct=1.0,
    ),
    LoanProduct(
        product_id="P2",
        lender="Beta",
        product_name="Beta Standard",
        purposes=[LoanPurpose.PERSONAL],
        annual_rate=11.0,
        min_amount=50_000.0,
        max_amount=80_000_000.0,
        min_tenure_months=12,
        max_tenure_months=60,
        min_credit_score=300,
        min_monthly_income=0.0,
        processing_fee_pct=1.0,
    ),
    LoanProduct(
        product_id="P3",
        lender="Gamma",
        product_name="Gamma Long",
        purposes=[LoanPurpose.PERSONAL],
        annual_rate=8.25,
        min_amount=50_000.0,
        max_amount=80_000_000.0,
        min_tenure_months=24,
        max_tenure_months=120,
        min_credit_score=300,
        min_monthly_income=0.0,
        processing_fee_pct=1.0,
    ),
]

EPS = 1e-9


# ============================================================== generators


@st.composite
def profiles(draw, with_portfolio: bool = True):
    income = draw(st.floats(min_value=25_000, max_value=1_500_000))
    expenses = draw(st.floats(min_value=0.15, max_value=0.75)) * income
    existing = draw(st.floats(min_value=0.0, max_value=0.20)) * income

    profile = CustomerProfile(
        user_id="inv-1",
        monthly_income=income,
        monthly_expenses=expenses,
        existing_emi=existing,
        credit_score=draw(st.integers(min_value=300, max_value=900)),
        employment_type=draw(st.sampled_from(list(EmploymentType))),
        employment_years=draw(st.floats(min_value=0.0, max_value=30.0)),
        age=draw(st.integers(min_value=21, max_value=64)),
        dependents=draw(st.integers(min_value=0, max_value=4)),
    )

    if with_portfolio:
        liquid = draw(st.floats(min_value=0.0, max_value=40.0)) * income
        volatile = draw(st.floats(min_value=0.0, max_value=40.0)) * income
        holdings = []
        if liquid > 0:
            holdings.append(
                Holding(
                    asset_type=AssetType.CASH,
                    current_value=liquid,
                    invested_value=liquid,
                )
            )
        if volatile > 0:
            holdings.append(
                Holding(
                    asset_type=AssetType.STOCKS,
                    current_value=volatile,
                    invested_value=volatile,
                )
            )
        portfolio = Portfolio(holdings=holdings)
    else:
        portfolio = Portfolio(holdings=[])

    requirement = LoanRequirement(
        purpose=LoanPurpose.PERSONAL,
        required_amount=income * draw(st.floats(min_value=2.0, max_value=40.0)),
        preferred_tenure_months=draw(st.sampled_from([12, 24, 36, 48, 60, 84])),
        risk_appetite=draw(st.sampled_from(list(RiskAppetite))),
    )
    return profile, portfolio, requirement


def _context(profile, portfolio, requirement):
    return build_context(profile, portfolio, requirement)


def _candidates(context):
    return [
        c
        for c in generate_candidates(
            context.requirement, context.financial, context.portfolio, PRODUCTS
        ).candidates
        if c.feasible
    ]


def _candidate(
    *,
    context,
    product_id: str = "P1",
    annual_rate: float = 9.5,
    loan_amount: float,
    liquidation_amount: float = 0.0,
    volatile_liquidated: float = 0.0,
    tenure_months: int = 36,
) -> Candidate:
    """
    Build one candidate directly, so an invariant can vary exactly one axis.

    The derived fields are computed the same way P5 computes them, using the same
    finance_math functions, so these are not a second arithmetic.
    """
    from app.core.finance_math import emi, total_interest, total_repayment

    monthly_emi = emi(loan_amount, annual_rate, tenure_months)
    total = context.portfolio.total_value
    gross_sold = min(liquidation_amount, total)
    remaining = max(0.0, total - gross_sold)
    remaining_liquid = max(0.0, context.portfolio.liquid_value - gross_sold)
    return Candidate(
        candidate_id=f"{product_id}-{round(loan_amount)}-{tenure_months}",
        product_id=product_id,
        lender="Alpha",
        tenure_months=tenure_months,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=context.requirement.required_amount,
        loan_amount=loan_amount,
        emi=monthly_emi,
        total_interest=total_interest(loan_amount, annual_rate, tenure_months),
        total_repayment=total_repayment(loan_amount, annual_rate, tenure_months),
        liquidation_amount=liquidation_amount,
        volatile_liquidation_amount=volatile_liquidated,
        remaining_portfolio_value=remaining,
        resulting_liquidity_ratio=(
            min(remaining_liquid / remaining, 1.0) if remaining > 0 else 0.0
        ),
        resulting_debt_burden_ratio=(
            (context.financial.existing_emi + monthly_emi)
            / context.financial.monthly_income
            if context.financial.monthly_income > 0
            else 0.0
        ),
        affordability_headroom=context.financial.emi_affordability_ceiling - monthly_emi,
    )


def _scale(context, candidates, k: float):
    """
    Multiply every rupee quantity by k, leaving every ratio untouched.

    This is the transformation the scale-invariance invariant applies. Ratios are
    deliberately NOT scaled: that is the whole point — a correct policy reads only
    ratios, so scaling can change nothing.
    """
    profile = context.profile.model_copy(
        update={
            "monthly_income": context.profile.monthly_income * k,
            "monthly_expenses": context.profile.monthly_expenses * k,
            "existing_emi": context.profile.existing_emi * k,
        }
    )
    financial = context.financial.model_copy(
        update={
            "monthly_income": context.financial.monthly_income * k,
            "monthly_expenses": context.financial.monthly_expenses * k,
            "existing_emi": context.financial.existing_emi * k,
            "disposable_income": context.financial.disposable_income * k,
            "emi_affordability_ceiling": context.financial.emi_affordability_ceiling * k,
        }
    )
    portfolio = context.portfolio.model_copy(
        update={
            "total_value": context.portfolio.total_value * k,
            "liquid_value": context.portfolio.liquid_value * k,
            "unrealized_gain_loss": context.portfolio.unrealized_gain_loss * k,
        }
    )
    requirement = context.requirement.model_copy(
        update={"required_amount": context.requirement.required_amount * k}
    )
    scaled_context = type(context)(
        profile=profile,
        financial=financial,
        portfolio=portfolio,
        requirement=requirement,
    )
    scaled_candidates = [
        candidate.model_copy(
            update={
                "required_amount": candidate.required_amount * k,
                "loan_amount": candidate.loan_amount * k,
                "emi": candidate.emi * k,
                "total_interest": candidate.total_interest * k,
                "total_repayment": candidate.total_repayment * k,
                "liquidation_amount": candidate.liquidation_amount * k,
                "volatile_liquidation_amount": candidate.volatile_liquidation_amount * k,
                "remaining_portfolio_value": candidate.remaining_portfolio_value * k,
                "affordability_headroom": candidate.affordability_headroom * k,
            }
        )
        for candidate in candidates
    ]
    return scaled_context, scaled_candidates


# ================================================== INVARIANT 1 — dominance


@SETTINGS
@given(profiles(), st.floats(min_value=0.5, max_value=6.0))
def test_dominance_score(inputs, rate_gap):
    """A candidate dominated on every axis never scores above its dominator."""
    context = _context(*inputs)
    loan = context.requirement.required_amount
    better = _candidate(context=context, annual_rate=9.5, loan_amount=loan)
    worse = _candidate(context=context, annual_rate=9.5 + rate_gap, loan_amount=loan)

    assert better.emi <= worse.emi + EPS
    assert better.total_interest <= worse.total_interest + EPS
    assert score_candidate(context, better) >= score_candidate(context, worse) - 1e-12


@SETTINGS
@given(profiles(), st.floats(min_value=0.5, max_value=6.0))
def test_dominance_grade(inputs, rate_gap):
    """Dominance survives grading, including the stress demotion."""
    context = _context(*inputs)
    loan = context.requirement.required_amount
    better = _candidate(context=context, annual_rate=9.5, loan_amount=loan)
    worse = _candidate(context=context, annual_rate=9.5 + rate_gap, loan_amount=loan)
    graded = grade_group(context, [better, worse])
    assert graded[0].grade >= graded[1].grade


# ==================================== INVARIANT 2 — single-axis monotonicity


@SETTINGS
@given(profiles(), st.floats(min_value=0.5, max_value=6.0))
def test_lower_rate_never_lowers_score(inputs, rate_gap):
    context = _context(*inputs)
    loan = context.requirement.required_amount
    cheap = _candidate(context=context, annual_rate=9.5, loan_amount=loan)
    dear = _candidate(context=context, annual_rate=9.5 + rate_gap, loan_amount=loan)
    assert score_candidate(context, cheap) >= score_candidate(context, dear) - 1e-12


@SETTINGS
@given(profiles())
def test_smaller_liquidation_share_never_lowers_score(inputs):
    """Liquidating less of the portfolio never scores worse on the impact axis."""
    context = _context(*inputs)
    if context.portfolio.total_value <= 0:
        return
    capacity = min(context.portfolio.liquid_value, context.requirement.required_amount)
    if capacity <= 0:
        return
    heavy = _candidate(
        context=context,
        loan_amount=max(context.requirement.required_amount - capacity, 50_000.0),
        liquidation_amount=capacity,
    )
    light = _candidate(
        context=context,
        loan_amount=max(context.requirement.required_amount - capacity / 2, 50_000.0),
        liquidation_amount=capacity / 2,
    )
    assert subscore_portfolio_impact(context, light) >= (
        subscore_portfolio_impact(context, heavy) - 1e-12
    )


@SETTINGS
@given(profiles(), st.floats(min_value=0.55, max_value=0.95))
def test_more_funding_coverage_never_lowers_the_score(coverage_inputs, coverage):
    """
    Funding the customer's stated need more fully never scores worse.

    Added in P7 after the mutation check: the cost sub-score divides interest by the
    FULL required amount, so an under-funded candidate borrows less, pays less
    interest and looks CHEAPER. Without a funding term the policy ranks partial
    funding above meeting the need, and no other invariant notices.
    """
    context = _context(*coverage_inputs)
    required = context.requirement.required_amount
    partial = _candidate(context=context, loan_amount=required * coverage)
    full = _candidate(context=context, loan_amount=required)
    if not (full.emi <= context.financial.emi_affordability_ceiling):
        return  # only compare candidates the customer could actually take
    assert score_candidate(context, full) >= score_candidate(context, partial) - 1e-12


@SETTINGS
@given(profiles())
def test_volatile_liquidation_never_scores_higher_than_liquid(inputs):
    """
    ADDED AFTER MUTATION TESTING. The original liquidation invariant only ever
    exercised volatile_liquidated == 0, so a SIGN ERROR on the volatile penalty
    survived the entire suite. Selling volatile holdings must never score better
    than selling the same rupee amount of liquid ones.
    """
    context = _context(*inputs)
    volatile_value = context.portfolio.total_value - context.portfolio.liquid_value
    if context.portfolio.total_value <= 0 or volatile_value <= 0:
        return
    liquidation = min(context.requirement.required_amount, context.portfolio.total_value)
    volatile_used = min(liquidation, volatile_value)
    if volatile_used <= 0:
        return

    loan = max(context.requirement.required_amount - liquidation, 50_000.0)
    from_liquid = _candidate(
        context=context, loan_amount=loan, liquidation_amount=liquidation
    )
    from_volatile = _candidate(
        context=context,
        loan_amount=loan,
        liquidation_amount=liquidation,
        volatile_liquidated=volatile_used,
    )
    assert subscore_portfolio_impact(context, from_volatile) <= (
        subscore_portfolio_impact(context, from_liquid) + 1e-12
    )
    assert subscore_appetite(context, from_volatile) <= (
        subscore_appetite(context, from_liquid) + 1e-12
    )


@SETTINGS
@given(profiles())
def test_grades_are_monotone_in_raw_score_within_a_group(inputs):
    """
    ADDED AFTER MUTATION TESTING (P7). Within a customer's own group, a candidate
    with a higher raw score never receives a LOWER grade.

    The dominance invariant compares two candidates, which is too small a group for
    the quantile bands to bite — inverting GRADE_QUANTILES entirely survived the suite
    because both candidates landed in the same band. This checks the real group.

    Stress is disabled: Stage D demotes on a scenario failure rate, which is not a
    function of the raw score, so it may legitimately reorder grades. This invariant
    is about Stage C.
    """
    context = _context(*inputs)
    candidates = _candidates(context)
    if len(candidates) < 3:
        return
    graded = [
        g
        for g in grade_group(context, candidates, apply_stress=False)
        if g.disqualified_reason is None
    ]
    if len(graded) < 3:
        return
    ordered = sorted(graded, key=lambda g: -g.raw_score)
    for higher, lower in zip(ordered, ordered[1:]):
        assert higher.grade >= lower.grade, (
            f"raw {higher.raw_score:.4f} graded {higher.grade} but "
            f"raw {lower.raw_score:.4f} graded {lower.grade}"
        )


@SETTINGS
@given(profiles())
def test_selling_volatile_assets_is_strictly_penalised(inputs):
    """
    ADDED AFTER MUTATION TESTING (P7). Zeroing VOLATILE_APPETITE_PENALTY survived the
    suite, because the ordering invariant permits EQUALITY: "never scores higher" is
    satisfied by scoring identically. But a policy that scores selling stocks exactly
    like selling cash does not represent the concern at all.

    Asserted only in the unclamped region, since two candidates both pinned at 0.0 are
    legitimately equal.
    """
    context = _context(*inputs)
    volatile_value = context.portfolio.total_value - context.portfolio.liquid_value
    if context.portfolio.total_value <= 0 or volatile_value <= 0:
        return
    liquidation = min(context.requirement.required_amount, context.portfolio.total_value)
    volatile_used = min(liquidation, volatile_value)
    if volatile_used <= 0:
        return
    # HYPOTHESIS EDGE CASE: volatile_value can be nonzero but below double-precision
    # significance relative to the portfolio (e.g. 5.55e-12 of a 25000 portfolio). The
    # penalty VOLATILE_APPETITE_PENALTY * (volatile_used / total) then rounds to zero,
    # so the two candidates are literally identical in floating point and the strict
    # "<" cannot hold — not because the penalty is zero, but because the difference is
    # unrepresentable. Skip the strict assertion when the volatile fraction cannot move
    # the score within floating-point resolution.
    if volatile_used / context.portfolio.total_value < 1e-12:
        return

    loan = max(context.requirement.required_amount - liquidation, 50_000.0)
    from_liquid = _candidate(
        context=context, loan_amount=loan, liquidation_amount=liquidation
    )
    from_volatile = _candidate(
        context=context,
        loan_amount=loan,
        liquidation_amount=liquidation,
        volatile_liquidated=volatile_used,
    )

    liquid_appetite = subscore_appetite(context, from_liquid)
    if 0.0 < liquid_appetite < 1.0:
        assert subscore_appetite(context, from_volatile) < liquid_appetite

    liquid_impact = subscore_portfolio_impact(context, from_liquid)
    if 0.0 < liquid_impact < 1.0:
        assert subscore_portfolio_impact(context, from_volatile) < liquid_impact


@SETTINGS
@given(profiles())
def test_liquidation_is_never_free(inputs):
    """
    ADDED AFTER MUTATION TESTING. Dropping the opportunity-cost term from the cost
    sub-score survived the suite, and that is the exact flaw that made
    100%-liquidate win 92% of groups. Selling an invested asset forgoes its return,
    so any candidate funded entirely from holdings must still carry a non-zero cost.
    """
    context = _context(*inputs)
    required = context.requirement.required_amount
    if context.portfolio.total_value < required:
        return
    volatile_used = max(0.0, required - context.portfolio.liquid_value)
    cash = Candidate(
        candidate_id="NO-LOAN",
        strategy=FinancingStrategy.LIQUIDATE_100,
        required_amount=required,
        loan_amount=0.0,
        emi=0.0,
        total_interest=0.0,
        total_repayment=0.0,
        liquidation_amount=required,
        volatile_liquidation_amount=volatile_used,
        remaining_portfolio_value=context.portfolio.total_value - required,
        resulting_liquidity_ratio=0.0,
        resulting_debt_burden_ratio=context.financial.debt_burden_ratio,
        affordability_headroom=context.financial.emi_affordability_ceiling,
    )
    assert cash.total_interest == 0.0
    assert subscore_cost(context, cash) < 1.0


@SETTINGS
@given(profiles())
def test_stress_can_only_demote(inputs):
    """
    ADDED AFTER MUTATION TESTING. A Stage D that PROMOTED instead of demoting
    survived the suite. Demotion is definitionally one-directional.
    """
    context = _context(*inputs)
    candidates = _candidates(context)
    if not candidates:
        return
    with_stress = grade_group(context, candidates, apply_stress=True)
    without = grade_group(context, candidates, apply_stress=False)
    for stressed, plain in zip(with_stress, without):
        assert stressed.grade <= plain.grade
        if stressed.demoted:
            assert stressed.grade == plain.grade - 1


# ========================================== INVARIANT 3 — scale invariance
# The invariant that catches absolute rupee thresholds, which are the most common
# and most invisible labeling bug.


@SETTINGS
@given(profiles(), st.floats(min_value=0.1, max_value=10.0))
def test_scale_invariance_of_grades(inputs, k):
    context = _context(*inputs)
    candidates = _candidates(context)
    if not candidates:
        return
    before = [g.grade for g in grade_group(context, candidates)]
    scaled_context, scaled_candidates = _scale(context, candidates, k)
    after = [g.grade for g in grade_group(scaled_context, scaled_candidates)]
    assert before == after


@SETTINGS
@given(profiles(), st.floats(min_value=0.2, max_value=5.0))
def test_scale_invariance_of_scores(inputs, k):
    context = _context(*inputs)
    candidates = _candidates(context)
    if not candidates:
        return
    scaled_context, scaled_candidates = _scale(context, candidates, k)
    for original, scaled in zip(candidates, scaled_candidates):
        assert math.isclose(
            score_candidate(context, original),
            score_candidate(scaled_context, scaled),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )


# ========================================== INVARIANT 4 — appetite ordering


@SETTINGS
@given(profiles())
def test_leverage_never_graded_higher_under_conservative(inputs):
    profile, portfolio, requirement = inputs
    conservative = build_context(
        profile,
        portfolio,
        requirement.model_copy(update={"risk_appetite": RiskAppetite.CONSERVATIVE}),
    )
    aggressive = build_context(
        profile,
        portfolio,
        requirement.model_copy(update={"risk_appetite": RiskAppetite.AGGRESSIVE}),
    )
    loan = requirement.required_amount
    leveraged = _candidate(context=conservative, loan_amount=loan, tenure_months=60)
    modest = _candidate(context=conservative, loan_amount=loan * 0.3, tenure_months=60)

    assert score_candidate(conservative, leveraged) <= (
        score_candidate(aggressive, leveraged) + 1e-12
    )
    assert grade_group(conservative, [leveraged, modest])[0].grade <= (
        grade_group(aggressive, [leveraged, modest])[0].grade
    )


# =================================== INVARIANT 5 — zero-portfolio consistency


@SETTINGS
@given(profiles(with_portfolio=False))
def test_no_liquidation_strategies_without_a_portfolio(inputs):
    context = _context(*inputs)
    for candidate in _candidates(context):
        assert candidate.liquidation_amount == 0.0
        assert candidate.volatile_liquidation_amount == 0.0
        assert candidate.strategy is FinancingStrategy.BORROW_100


@SETTINGS
@given(profiles(with_portfolio=False))
def test_zero_portfolio_still_grades(inputs):
    context = _context(*inputs)
    candidates = _candidates(context)
    if not candidates:
        return
    graded = grade_group(context, candidates)
    assert len(graded) == len(candidates)
    assert all(0 <= g.grade <= 3 for g in graded)


# ======================================== INVARIANT 6 — non-degeneracy
# Population-level, not per-example. Run against the REAL generated dataset, because
# Phase R's numbers came from a population built inside the spike and the real
# candidate mix shifts them.


@pytest.fixture(scope="module")
def population_report():
    from training.population import build_population, degeneracy_report

    return degeneracy_report(build_population())


def test_every_grade_appears(population_report):
    assert set(population_report["grade_counts"]) == {0, 1, 2, 3}, population_report[
        "grade_counts"
    ]


def test_no_grade_dominates_the_dataset(population_report):
    assert population_report["max_grade_share"] <= 0.60, population_report


def test_grades_form_a_pyramid_at_the_top(population_report):
    """
    ADDED AFTER MUTATION TESTING (P7). The top grade must be SCARCER than the grade
    below it.

    Inverting GRADE_QUANTILES survived every other invariant: the grading stays
    perfectly monotone in raw score, so no per-example invariant can see it, and grade
    3 rose from 12% to 40% of labels — inflated more than threefold but still under
    the 60% dominance limit. A relevance scale where "excellent" is the most common
    label has no discriminative power at the top, which is exactly where NDCG@1 and
    the acceptance threshold operate.
    """
    shares = population_report["grade_shares"]
    assert shares[3] < shares[2], shares


def test_no_single_product_wins_most_groups(population_report):
    assert population_report["max_product_win_share"] <= 0.60, population_report


def test_no_single_tenure_wins_most_groups(population_report):
    assert population_report["max_tenure_win_share"] <= 0.60, population_report


def test_no_single_strategy_wins_most_groups(population_report):
    assert population_report["max_strategy_win_share"] <= 0.60, population_report


def test_population_contains_no_good_option_customers(population_report):
    """
    The dataset MUST contain customers for whom nothing is suitable. Without them the
    model cannot learn that some profiles have no good option, and NO_SUITABLE_LOAN
    becomes unreachable (CONTEXT.md section 7).
    """
    assert population_report["no_good_option_customers"] > 0, population_report
