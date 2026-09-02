"""
SPIKE 1 — prototype relevance labeling policy, in the decomposed four-stage shape.

    Stage A  disqualifier mask            -> forced grade 0
    Stage B  independent sub-scores       -> each in [0,1], each owning ONE concern
    Stage C  documented combination       -> within-group rank + absolute quality cap
    Stage D  stress demotion              -> applied AFTER grading, never folded in

Every quantity used is a RATIO, which is what makes the scale-invariance invariant
hold. If you introduce an absolute rupee threshold anywhere in this file, that
invariant will fail — which is the point of having it.

SPIKE ONLY. Phase 7 re-implements this against the real schemas.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from domain import AGGRESSIVE, CONSERVATIVE, MODERATE, Candidate, Customer

# ==========================================================================
# CONSTANTS — every one documented. Phase 7 moves these into config.
# ==========================================================================

# --- Stage A: hard disqualifiers -----------------------------------------
MAX_EMI_SHARE_OF_DISPOSABLE = 0.60   # EMI above this share of disposable income is
                                     # not a real option at any grade.
HARD_DBR_CAP = 0.55                  # (existing EMI + new EMI) / income. Policy-level
                                     # ceiling, deliberately appetite-INDEPENDENT so
                                     # disqualification stays deterministic; appetite
                                     # enters through Stage B instead.
MIN_FUNDING_COVERAGE = 0.95          # a candidate that funds less than this share of
                                     # the requirement does not meet the need.

# --- Stage B: sub-score shaping ------------------------------------------
MAX_COST_RATIO = 1.20                # total financing cost / required amount at
                                     # which the cost sub-score reaches 0.
# FINDING (spike): without an opportunity-cost term, liquidating holdings is treated
# as FREE — no interest, no EMI — so 100%-liquidate won ~92% of groups. Selling an
# invested asset forgoes its return, and that is a real cost of the financing choice.
# Evaluated over a fixed horizon so candidates with different tenures stay comparable.
OPPORTUNITY_HORIZON_YEARS = 5.0
LIQUID_ASSET_RETURN = 0.06           # cash / FD / liquid funds
VOLATILE_ASSET_RETURN = 0.11         # equity / crypto
VOLATILE_IMPACT_MULTIPLIER = 0.50    # extra portfolio-impact penalty per unit of
                                     # volatile holdings liquidated.
TARGET_BUFFER_MONTHS = 6.0           # emergency buffer, in months of expenses, that
                                     # should survive the liquidation. Without this
                                     # term the policy treats spending savings as
                                     # free and 100%-liquidate wins ~92% of groups.
BUFFER_SHORTFALL_WEIGHT = 1.20       # how hard a depleted buffer is penalised.
DBR_CAP_BY_APPETITE = {              # comfort ceiling (not a hard rule) per appetite
    CONSERVATIVE: 0.30,
    MODERATE: 0.40,
    AGGRESSIVE: 0.50,
}
VOLATILE_APPETITE_PENALTY = {        # appetite-sensitive dislike of selling volatile
    CONSERVATIVE: 0.60,              # assets, as a fraction of the portfolio sold
    MODERATE: 0.30,
    AGGRESSIVE: 0.10,
}

# --- Stage C: combination and grading ------------------------------------
W_AFFORDABILITY = 0.22
W_COST = 0.33
W_PORTFOLIO_IMPACT = 0.25
W_APPETITE = 0.20                    # weights sum to 1.0
# Affordability carries a modest weight because it is ALREADY enforced twice:
# as a Stage A hard disqualifier, and inside the appetite sub-score's debt
# burden term. Weighting it higher a third time made 100%-liquidate win
# almost every group.

GRADE_QUANTILES = (0.15, 0.40, 0.70) # top 15% -> 3, next 25% -> 2, next 30% -> 1
ABSOLUTE_GRADE_FLOORS = (0.60, 0.45, 0.33)  # raw score needed to be *allowed* a
                                     # grade of 3 / 2 / 1. This cap is what lets a
                                     # whole customer legitimately have no good
                                     # option — quantile grading alone would always
                                     # manufacture a grade 3.

# --- Stage D: stress simulation ------------------------------------------
# Tuned in this spike so the label-flip rate lands inside the 2%-30% band.
STRESS_SEED = 20260901
STRESS_SIMS = 200
STRESS_SHOCK_PROBABILITY = 0.35      # chance a given scenario contains an income shock
STRESS_MAGNITUDE_RANGE = (0.20, 0.55)  # fractional income drop during the shock
STRESS_DEMOTION_THRESHOLD = 0.32     # demote one grade when this share of scenarios
                                     # leaves the household unable to pay the EMI


def _clamp(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


# ==========================================================================
# STAGE A — disqualifiers
# ==========================================================================
def disqualify(customer: Customer, candidate: Candidate) -> str | None:
    """Return a reason string when the candidate is a forced grade 0, else None."""
    ceiling = customer.affordability_ceiling(MAX_EMI_SHARE_OF_DISPOSABLE)
    if ceiling <= 0 or candidate.emi > ceiling:
        return "EMI_EXCEEDS_AFFORDABILITY"
    if customer.monthly_income <= 0:
        return "NO_INCOME"
    post_dbr = (customer.existing_emi + candidate.emi) / customer.monthly_income
    if post_dbr > HARD_DBR_CAP:
        return "DEBT_BURDEN_CAP_EXCEEDED"
    funded = candidate.loan_amount + candidate.liquidation_amount
    if funded < candidate.required_amount * MIN_FUNDING_COVERAGE:
        return "FUNDING_SHORTFALL"
    if candidate.liquidation_amount > customer.liquid_value + customer.volatile_value + 1e-6:
        return "LIQUIDATION_EXCEEDS_PORTFOLIO"
    return None


# ==========================================================================
# STAGE B — independent sub-scores, each owning exactly one concern
# ==========================================================================
def subscore_affordability(customer: Customer, candidate: Candidate) -> float:
    ceiling = customer.affordability_ceiling(MAX_EMI_SHARE_OF_DISPOSABLE)
    if ceiling <= 0:
        return 0.0
    return _clamp(1.0 - candidate.emi / ceiling)


def subscore_cost(customer: Customer, candidate: Candidate) -> float:
    """
    Total cost of the financing CHOICE: interest paid on what is borrowed, plus the
    return forgone on what is sold. One concern: what this option costs.
    """
    if candidate.required_amount <= 0:
        return 1.0
    liquid_used = min(candidate.liquidation_amount, customer.liquid_value)
    volatile_used = candidate.volatile_liquidated
    opportunity_cost = liquid_used * (
        (1.0 + LIQUID_ASSET_RETURN) ** OPPORTUNITY_HORIZON_YEARS - 1.0
    ) + volatile_used * (
        (1.0 + VOLATILE_ASSET_RETURN) ** OPPORTUNITY_HORIZON_YEARS - 1.0
    )
    ratio = (candidate.total_interest + opportunity_cost) / candidate.required_amount
    return _clamp(1.0 - ratio / MAX_COST_RATIO)


def subscore_portfolio_impact(customer: Customer, candidate: Candidate) -> float:
    if customer.portfolio_value <= 0:
        return 1.0                                   # zero-portfolio: no impact
    share = candidate.liquidation_amount / customer.portfolio_value
    volatile_share = candidate.volatile_liquidated / customer.portfolio_value
    penalty = share + VOLATILE_IMPACT_MULTIPLIER * volatile_share

    # Emergency-buffer term: what liquid cover survives, in months of expenses.
    # Ratio-based, so scale invariance holds.
    if customer.monthly_expenses > 0:
        remaining_liquid = max(
            0.0, customer.liquid_value - min(candidate.liquidation_amount, customer.liquid_value)
        )
        buffer_months = remaining_liquid / customer.monthly_expenses
        shortfall = max(0.0, TARGET_BUFFER_MONTHS - buffer_months) / TARGET_BUFFER_MONTHS
        penalty += BUFFER_SHORTFALL_WEIGHT * shortfall

    return _clamp(1.0 - penalty)


def subscore_appetite(customer: Customer, candidate: Candidate) -> float:
    cap = DBR_CAP_BY_APPETITE[customer.risk_appetite]
    if customer.monthly_income <= 0:
        return 0.0
    post_dbr = (customer.existing_emi + candidate.emi) / customer.monthly_income
    score = 1.0 - post_dbr / cap
    if customer.portfolio_value > 0 and candidate.volatile_liquidated > 0:
        volatile_share = candidate.volatile_liquidated / customer.portfolio_value
        score -= VOLATILE_APPETITE_PENALTY[customer.risk_appetite] * volatile_share
    return _clamp(score)


# ==========================================================================
# STAGE C — combination
# ==========================================================================
def score_candidate(customer: Customer, candidate: Candidate) -> float:
    """Combined raw score in [0,1]. Scale-invariant by construction."""
    return (
        W_AFFORDABILITY * subscore_affordability(customer, candidate)
        + W_COST * subscore_cost(customer, candidate)
        + W_PORTFOLIO_IMPACT * subscore_portfolio_impact(customer, candidate)
        + W_APPETITE * subscore_appetite(customer, candidate)
    )


def _absolute_cap(raw: float) -> int:
    hi, mid, lo = ABSOLUTE_GRADE_FLOORS
    if raw >= hi:
        return 3
    if raw >= mid:
        return 2
    if raw >= lo:
        return 1
    return 0


# ==========================================================================
# STAGE D — stress demotion
# ==========================================================================
def _stress_scenarios() -> list[tuple[bool, float]]:
    """
    Drawn once, from a constant seed, and shared by every customer and candidate.

    Sharing the draws is what keeps the simulation deterministic, monotone in EMI,
    and scale-invariant — three properties the invariant suite checks.
    """
    rng = random.Random(STRESS_SEED)
    lo, hi = STRESS_MAGNITUDE_RANGE
    return [
        (rng.random() < STRESS_SHOCK_PROBABILITY, rng.uniform(lo, hi))
        for _ in range(STRESS_SIMS)
    ]


_SCENARIOS = _stress_scenarios()


def stress_failure_rate(customer: Customer, candidate: Candidate) -> float:
    """Share of scenarios in which the household cannot cover the new EMI."""
    fails = 0
    for shocked, magnitude in _SCENARIOS:
        income = customer.monthly_income * (1.0 - magnitude) if shocked else customer.monthly_income
        headroom = income - customer.monthly_expenses - customer.existing_emi
        if headroom < candidate.emi:
            fails += 1
    return fails / len(_SCENARIOS)


# ==========================================================================
# public result type + the grading entry point
# ==========================================================================
@dataclass(frozen=True)
class GradedCandidate:
    candidate: Candidate
    raw_score: float
    grade: int
    disqualified_reason: str | None
    stress_failure_rate: float
    demoted: bool


def grade_group(
    customer: Customer,
    candidates: list[Candidate],
    apply_stress: bool = True,
) -> list[GradedCandidate]:
    """
    Grade one customer's whole candidate set.

    Order is preserved: result[i] corresponds to candidates[i].
    """
    if not candidates:
        return []

    reasons = [disqualify(customer, c) for c in candidates]
    raws = [
        0.0 if reasons[i] else score_candidate(customer, c)
        for i, c in enumerate(candidates)
    ]

    eligible_idx = [i for i in range(len(candidates)) if reasons[i] is None]
    grades = [0] * len(candidates)

    if eligible_idx:
        # Within-group rank, ties broken by original index so the ordering is stable
        # and dominance survives grading.
        ordered = sorted(eligible_idx, key=lambda i: (-raws[i], i))
        n = len(ordered)
        q3, q2, q1 = GRADE_QUANTILES
        for position, i in enumerate(ordered):
            pct = position / n
            if pct < q3:
                quantile_grade = 3
            elif pct < q2:
                quantile_grade = 2
            elif pct < q1:
                quantile_grade = 1
            else:
                quantile_grade = 0
            # The absolute cap is what allows a customer to have no good option.
            grades[i] = min(quantile_grade, _absolute_cap(raws[i]))

    out: list[GradedCandidate] = []
    for i, candidate in enumerate(candidates):
        rate = stress_failure_rate(customer, candidate)
        demoted = False
        grade = grades[i]
        if apply_stress and grade > 0 and rate > STRESS_DEMOTION_THRESHOLD:
            grade -= 1
            demoted = True
        out.append(
            GradedCandidate(
                candidate=candidate,
                raw_score=raws[i],
                grade=grade,
                disqualified_reason=reasons[i],
                stress_failure_rate=rate,
                demoted=demoted,
            )
        )
    return out
