"""
SPIKE 1 — THE INVARIANT SUITE.

Written BEFORE the labeling policy exists, deliberately. These are properties any
correct labeler must satisfy regardless of its coefficients. Phase 7 ports this file
to tests/test_labeling_invariants.py against the real schemas.

Run:  python -m pytest spikes/labeling/test_invariants.py -q
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from domain import (
    AGGRESSIVE,
    CONSERVATIVE,
    Candidate,
    Customer,
    Product,
    generate_candidates,
    scale,
)
from policy import grade_group, score_candidate

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# --------------------------------------------------------------------------
# generators
# --------------------------------------------------------------------------
@st.composite
def customers(draw, with_portfolio: bool = True):
    income = draw(st.floats(min_value=25_000, max_value=1_500_000))
    expenses = draw(st.floats(min_value=0.15, max_value=0.75)) * income
    existing = draw(st.floats(min_value=0.0, max_value=0.20)) * income
    liquid = draw(st.floats(min_value=0.0, max_value=40.0)) * income if with_portfolio else 0.0
    volatile = draw(st.floats(min_value=0.0, max_value=40.0)) * income if with_portfolio else 0.0
    return Customer(
        monthly_income=income,
        monthly_expenses=expenses,
        existing_emi=existing,
        credit_score=draw(st.integers(min_value=300, max_value=900)),
        age=draw(st.integers(min_value=21, max_value=64)),
        risk_appetite=draw(st.sampled_from([CONSERVATIVE, "MODERATE", AGGRESSIVE])),
        portfolio_value=liquid + volatile,
        liquid_value=liquid,
        volatile_value=volatile,
    )


@st.composite
def candidate_pair_same_product(draw):
    """A candidate and a strictly dominated twin: same product and loan amount."""
    customer = draw(customers())
    amount = draw(st.floats(min_value=100_000, max_value=5_000_000))
    tenure = draw(st.integers(min_value=12, max_value=84))
    good_rate = draw(st.floats(min_value=6.0, max_value=12.0))
    worse_rate = good_rate + draw(st.floats(min_value=0.5, max_value=6.0))

    better = Candidate(
        product_id="P1",
        annual_rate=good_rate,
        required_amount=amount,
        loan_amount=amount,
        liquidation_amount=0.0,
        volatile_liquidated=0.0,
        tenure_months=tenure,
        strategy="BORROW_100",
    )
    worse = replace(better, annual_rate=worse_rate)
    return customer, better, worse


PRODUCTS = [
    Product("P1", 9.5, 50_000, 8_000_000, 12, 84),
    Product("P2", 11.0, 50_000, 3_000_000, 12, 60),
    Product("P3", 8.25, 200_000, 10_000_000, 24, 120),
]
TENURES = [12, 24, 36, 48, 60, 84]


# --------------------------------------------------------------------------
# INVARIANT 1 — dominance
# --------------------------------------------------------------------------
@SETTINGS
@given(candidate_pair_same_product())
def test_dominance_score(pair):
    """A candidate dominated on every axis never scores above its dominator."""
    customer, better, worse = pair
    assert better.emi <= worse.emi + 1e-9
    assert better.total_interest <= worse.total_interest + 1e-9
    assert score_candidate(customer, better) >= score_candidate(customer, worse) - 1e-12


@SETTINGS
@given(candidate_pair_same_product())
def test_dominance_grade(pair):
    """Dominance survives grading, including the stress demotion."""
    customer, better, worse = pair
    graded = grade_group(customer, [better, worse])
    assert graded[0].grade >= graded[1].grade


# --------------------------------------------------------------------------
# INVARIANT 2 — single-axis monotonicity
# --------------------------------------------------------------------------
@SETTINGS
@given(candidate_pair_same_product())
def test_lower_rate_never_lowers_score(pair):
    customer, better, worse = pair
    assert score_candidate(customer, better) >= score_candidate(customer, worse) - 1e-12


@SETTINGS
@given(
    customers(),
    st.floats(min_value=200_000, max_value=4_000_000),
    st.integers(min_value=12, max_value=60),
    st.floats(min_value=7.0, max_value=14.0),
)
def test_smaller_liquidation_share_never_lowers_score(customer, amount, tenure, rate):
    """Holding all else equal, liquidating less of the portfolio never scores worse."""
    if customer.portfolio_value <= 0:
        return
    capacity = min(customer.liquid_value, amount)
    if capacity <= 0:
        return
    heavy = Candidate("P1", rate, amount, amount - capacity, capacity, 0.0, tenure, "HYBRID")
    light = Candidate("P1", rate, amount, amount - capacity / 2, capacity / 2, 0.0, tenure, "HYBRID")
    # `light` liquidates less but borrows more; compare only the portfolio-impact
    # sub-score, which is the axis this invariant is about.
    from policy import subscore_portfolio_impact

    assert subscore_portfolio_impact(customer, light) >= subscore_portfolio_impact(
        customer, heavy
    ) - 1e-12


@SETTINGS
@given(
    customers(),
    st.floats(min_value=200_000, max_value=4_000_000),
    st.integers(min_value=12, max_value=60),
    st.floats(min_value=7.0, max_value=14.0),
)
def test_volatile_liquidation_never_scores_higher_than_liquid(customer, amount, tenure, rate):
    """
    Added after a mutation check: the original liquidation invariant only ever
    exercised volatile_liquidated == 0, so a SIGN ERROR on the volatile penalty
    survived the whole suite. Selling volatile holdings must never score better
    than selling the same rupee amount of liquid ones.
    """
    from policy import subscore_appetite, subscore_portfolio_impact

    if customer.portfolio_value <= 0 or customer.volatile_value <= 0:
        return
    liquidation = min(amount, customer.portfolio_value)
    volatile_used = min(liquidation, customer.volatile_value)
    if volatile_used <= 0:
        return
    from_liquid = Candidate("P1", rate, amount, amount - liquidation, liquidation, 0.0, tenure, "HYBRID")
    from_volatile = Candidate(
        "P1", rate, amount, amount - liquidation, liquidation, volatile_used, tenure, "HYBRID"
    )
    assert subscore_portfolio_impact(customer, from_volatile) <= subscore_portfolio_impact(
        customer, from_liquid
    ) + 1e-12
    assert subscore_appetite(customer, from_volatile) <= subscore_appetite(
        customer, from_liquid
    ) + 1e-12


@SETTINGS
@given(candidate_pair_same_product())
def test_grade_never_decreases_when_candidate_improves(pair):
    """Improving one candidate in a group never lowers that candidate's own grade."""
    customer, better, worse = pair
    others = [
        Candidate("P2", 11.0, worse.required_amount, worse.required_amount, 0.0, 0.0, 24, "BORROW_100"),
        Candidate("P3", 8.25, worse.required_amount, worse.required_amount, 0.0, 0.0, 60, "BORROW_100"),
    ]
    before = grade_group(customer, [worse, *others])[0].grade
    after = grade_group(customer, [better, *others])[0].grade
    assert after >= before


@SETTINGS
@given(customers(), st.floats(min_value=200_000, max_value=4_000_000), st.integers(min_value=12, max_value=60))
def test_liquidation_is_never_free(customer, amount, tenure):
    """
    Added after a mutation check: dropping the opportunity-cost term from the cost
    sub-score survived the suite, and that is the exact flaw that made
    100%-liquidate win 92% of groups. Selling an invested asset forgoes its return,
    so any candidate that liquidates must carry a non-zero cost.
    """
    from policy import subscore_cost

    if customer.portfolio_value < amount:
        return                      # only the fully-funded-from-assets case is the point
    # Liquid holdings are consumed before volatile ones, exactly as the generator does.
    # Getting this wrong is what made the first version of this test fail: it built a
    # candidate that liquidated from a customer who had no liquid assets at all.
    volatile_used = max(0.0, amount - customer.liquid_value)
    cash = Candidate("NO_LOAN", 0.0, amount, 0.0, amount, volatile_used, tenure, "LIQUIDATE_100")
    assert cash.total_interest == 0.0          # nothing borrowed
    assert subscore_cost(customer, cash) < 1.0  # ...but it is still not free


@SETTINGS
@given(customers(), st.floats(min_value=200_000, max_value=4_000_000), st.integers(min_value=12, max_value=84))
def test_stress_can_only_demote(customer, amount, tenure):
    """
    Added after a mutation check: a Stage D that PROMOTED instead of demoting
    survived the suite. Demotion is definitionally one-directional.
    """
    candidates = [
        Candidate("P1", 9.5, amount, amount, 0.0, 0.0, tenure, "BORROW_100"),
        Candidate("P2", 11.0, amount, amount, 0.0, 0.0, tenure, "BORROW_100"),
        Candidate("P3", 8.25, amount, amount * 0.6, 0.0, 0.0, tenure, "BORROW_100"),
    ]
    with_stress = grade_group(customer, candidates, apply_stress=True)
    without = grade_group(customer, candidates, apply_stress=False)
    for a, b in zip(with_stress, without):
        assert a.grade <= b.grade
        if a.demoted:
            assert a.grade == b.grade - 1


# --------------------------------------------------------------------------
# INVARIANT 3 — scale invariance  (the one that catches absolute thresholds)
# --------------------------------------------------------------------------
@SETTINGS
@given(customers(), st.floats(min_value=0.1, max_value=10.0))
def test_scale_invariance(customer, k):
    required = customer.monthly_income * 12
    candidates = generate_candidates(customer, PRODUCTS, required, TENURES)
    if not candidates:
        return
    base = [g.grade for g in grade_group(customer, candidates)]
    sc, scaled_candidates = scale(customer, candidates, k)
    after = [g.grade for g in grade_group(sc, scaled_candidates)]
    assert base == after


@SETTINGS
@given(customers(), st.floats(min_value=0.2, max_value=5.0))
def test_scale_invariance_of_scores(customer, k):
    required = customer.monthly_income * 12
    candidates = generate_candidates(customer, PRODUCTS, required, TENURES)
    if not candidates:
        return
    sc, scaled_candidates = scale(customer, candidates, k)
    for original, scaled_candidate in zip(candidates, scaled_candidates):
        a = score_candidate(customer, original)
        b = score_candidate(sc, scaled_candidate)
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


# --------------------------------------------------------------------------
# INVARIANT 4 — appetite ordering
# --------------------------------------------------------------------------
@SETTINGS
@given(customers(), st.floats(min_value=500_000, max_value=6_000_000), st.integers(min_value=24, max_value=84))
def test_leverage_never_graded_higher_under_conservative(customer, amount, tenure):
    leveraged = Candidate("P1", 10.5, amount, amount, 0.0, 0.0, tenure, "BORROW_100")
    modest = Candidate("P1", 10.5, amount, amount * 0.3, 0.0, 0.0, tenure, "BORROW_100")
    cons = replace(customer, risk_appetite=CONSERVATIVE)
    aggr = replace(customer, risk_appetite=AGGRESSIVE)
    assert score_candidate(cons, leveraged) <= score_candidate(aggr, leveraged) + 1e-12
    g_cons = grade_group(cons, [leveraged, modest])[0].grade
    g_aggr = grade_group(aggr, [leveraged, modest])[0].grade
    assert g_cons <= g_aggr


# --------------------------------------------------------------------------
# INVARIANT 5 — zero-portfolio consistency
# --------------------------------------------------------------------------
@SETTINGS
@given(customers(with_portfolio=False))
def test_no_liquidation_strategies_without_portfolio(customer):
    candidates = generate_candidates(
        customer, PRODUCTS, customer.monthly_income * 12, TENURES
    )
    assert all(c.liquidation_amount == 0.0 for c in candidates)
    assert all(c.strategy == "BORROW_100" for c in candidates)


@SETTINGS
@given(customers(with_portfolio=False))
def test_zero_portfolio_still_grades(customer):
    candidates = generate_candidates(
        customer, PRODUCTS, customer.monthly_income * 12, TENURES
    )
    if not candidates:
        return
    graded = grade_group(customer, candidates)
    assert len(graded) == len(candidates)
    assert all(0 <= g.grade <= 3 for g in graded)


# --------------------------------------------------------------------------
# INVARIANT 6 — non-degeneracy  (population-level, not per-example)
# --------------------------------------------------------------------------
def test_population_non_degeneracy():
    """
    Over a synthetic population: every grade appears, no grade dominates the
    dataset, and no single product / tenure / strategy wins most groups.
    """
    from population import build_population, degeneracy_report

    groups = build_population(n_customers=300, seed=42)
    report = degeneracy_report(groups)

    assert set(report["grade_counts"]) == {0, 1, 2, 3}, report["grade_counts"]
    assert report["max_grade_share"] <= 0.60, report
    assert report["max_product_win_share"] <= 0.60, report
    assert report["max_tenure_win_share"] <= 0.60, report
    assert report["max_strategy_win_share"] <= 0.60, report


def test_population_contains_no_good_option_customers():
    """The dataset MUST contain customers for whom nothing is suitable."""
    from population import build_population, degeneracy_report

    groups = build_population(n_customers=300, seed=42)
    report = degeneracy_report(groups)
    assert report["no_good_option_customers"] > 0, report


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
