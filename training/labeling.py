"""
THE relevance labeling policy (P7). There is exactly one labeler and this is it.

This file defines what "suitable for this customer" MEANS as a training target. The
primary recommender's entire notion of suitability comes from here, and no downstream
metric can detect a flaw in it, because every downstream metric is measured against
these same labels (CONTEXT.md 17.1). That is why it is decomposed rather than
monolithic, and why tests/test_labeling_invariants.py was written before it.

    Stage A  disqualifier mask       -> forced grade 0. Nothing else assigns grade 0.
    Stage B  independent sub-scores  -> each in [0,1], each owning exactly ONE concern.
                                        No sub-score reads another's inputs.
                                        funding / affordability / cost /
                                        portfolio impact / appetite alignment.
    Stage C  documented combination  -> weighted sum, then GRADES BY RANK WITHIN THE
                                        CUSTOMER'S OWN GROUP, capped by an absolute
                                        quality floor.
    Stage D  stress demotion         -> applied AFTER grading, never folded into a
                                        sub-score.

    Label noise is a FIFTH, separate step applied at dataset build time — see
    apply_label_noise below for why it is not part of grade_group.

EVERY QUANTITY USED IS A RATIO. That is what makes the scale-invariance invariant
hold. Introduce one absolute rupee threshold anywhere here and that invariant fails,
which is precisely why it exists.

LABELS PRODUCED HERE ARE SYNTHETIC. A model trained on them partially reproduces this
policy; reported NDCG measures agreement with it, not with real customer outcomes
(AGENTS.md section 6 rule 9).

OFFLINE ONLY. Lives in training/, never imported by app/.
"""

import random
from dataclasses import dataclass

from app.config import settings
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.schemas import (
    Candidate,
    CustomerProfile,
    FinancialMetrics,
    LoanRequirement,
    Portfolio,
    PortfolioMetrics,
)
from app.schemas.enums import RiskAppetite

LABELING_POLICY_VERSION = settings.LABELING_POLICY_VERSION

# ==========================================================================
# CONSTANTS — every one documented. Starting values validated in Phase R
# (spikes/labeling/FINDINGS.md), re-measured here against the real generator.
# ==========================================================================

# --- Stage A: hard disqualifiers ----------------------------------------
# Policy-level debt-burden ceiling. Deliberately appetite-INDEPENDENT, so
# disqualification stays deterministic and appetite enters only through Stage B.
# It is also deliberately looser than any guardrail cap: guardrails are a serving-time
# policy layer and must NOT be baked into the labels, or the model learns to reproduce
# the policy instead of learning suitability, and the P12 guardrail walk becomes a
# no-op.
HARD_DBR_CAP = 0.55
# Below this share of the requirement a candidate is not an answer to the request at
# all, and is disqualified. BETWEEN this floor and full funding it is a COMPROMISE, not
# an impossibility, and is scored down by subscore_funding rather than gated.
#
# FINDING (P7, against the real generator): treating anything under 95% coverage as a
# Stage A disqualifier made grade 0 eighty-seven percent of the dataset, because P5's
# amount grid deliberately enumerates 0.6x and 0.8x candidates. Worse, without a
# funding term the cost sub-score divides interest by the FULL required amount, so an
# under-funded candidate scores as cheaper — the policy would have ranked partial
# funding highest. Funding adequacy is a concern in its own right.
FUNDING_DISQUALIFY_BELOW = 0.50

# --- Stage B: sub-score shaping ------------------------------------------
# Total financing cost as a share of the required amount at which the cost sub-score
# reaches 0.
MAX_COST_RATIO = 1.20
# Without an opportunity-cost term, liquidating holdings is treated as FREE — no
# interest, no EMI — and 100%-liquidate won ~92% of groups in Phase R. Selling an
# invested asset forgoes its return, and that is a real cost of the financing choice.
# Evaluated over a FIXED horizon so candidates of different tenures stay comparable.
OPPORTUNITY_HORIZON_YEARS = 5.0
LIQUID_ASSET_RETURN = 0.06
VOLATILE_ASSET_RETURN = 0.11
# Extra portfolio-impact penalty per unit of volatile holdings sold.
VOLATILE_IMPACT_MULTIPLIER = 0.50
# Emergency buffer, in months of expenses, that should survive the liquidation.
# Without this term the policy treats spending savings as free.
TARGET_BUFFER_MONTHS = 6.0
BUFFER_SHORTFALL_WEIGHT = 1.20
# Comfort ceiling per appetite — NOT a hard rule, and not the guardrail cap.
DBR_CAP_BY_APPETITE = {
    RiskAppetite.CONSERVATIVE: 0.30,
    RiskAppetite.MODERATE: 0.40,
    RiskAppetite.AGGRESSIVE: 0.50,
}
# Appetite-sensitive dislike of selling volatile assets, per unit of portfolio sold.
VOLATILE_APPETITE_PENALTY = {
    RiskAppetite.CONSERVATIVE: 0.60,
    RiskAppetite.MODERATE: 0.30,
    RiskAppetite.AGGRESSIVE: 0.10,
}

# --- Stage C: combination and grading -------------------------------------
# Weights sum to 1.0. Affordability carries a deliberately modest weight because it is
# ALREADY enforced twice — as a P5 feasibility gate, and inside the appetite
# sub-score's debt-burden term. Weighting it heavily a third time was one cause of the
# 100%-liquidate degeneracy found in Phase R.
W_FUNDING = 0.20
W_AFFORDABILITY = 0.18
W_COST = 0.26
W_PORTFOLIO_IMPACT = 0.20
W_APPETITE = 0.16

# Top 15% of a customer's own candidates -> 3, next 25% -> 2, next 30% -> 1, rest -> 0.
GRADE_QUANTILES = (0.15, 0.40, 0.70)
# Raw score required to be ALLOWED a grade of 3 / 2 / 1. THIS CAP IS WHAT LETS A
# CUSTOMER LEGITIMATELY HAVE NO GOOD OPTION — quantile grading alone always
# manufactures a grade 3, and the product must be able to say NO_SUITABLE_LOAN.
ABSOLUTE_GRADE_FLOORS = (0.60, 0.45, 0.33)

# --- Stage D: stress simulation ------------------------------------------
# One shared scenario draw from a constant seed, reused for every customer and
# candidate. Sharing the draws is what makes the simulation simultaneously
# deterministic, monotone in EMI, and scale-invariant — three properties the invariant
# suite checks.
STRESS_SEED = 20260901
STRESS_SIMS = 200
STRESS_SHOCK_PROBABILITY = 0.35
STRESS_MAGNITUDE_RANGE = (0.20, 0.55)
# Demote one grade when this share of scenarios leaves the household unable to pay.
STRESS_DEMOTION_THRESHOLD = 0.32

# --- Label noise (applied at dataset build, NOT in grade_group) -----------
# Share of labels perturbed by one grade. Real relevance judgements are noisy, and a
# perfectly consistent target invites the ranker to memorise the policy exactly.
LABEL_NOISE_RATE = 0.05
LABEL_NOISE_SEED = 20260903

MIN_GRADE = 0
MAX_GRADE = 3


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


@dataclass(frozen=True)
class CustomerContext:
    """Everything the policy may read about one customer. Assembled once per group."""

    profile: CustomerProfile
    financial: FinancialMetrics
    portfolio: PortfolioMetrics
    requirement: LoanRequirement


def build_context(
    profile: CustomerProfile, portfolio: Portfolio, requirement: LoanRequirement
) -> CustomerContext:
    """
    Derive the context using the SAME analysis modules that run at serving time.
    Re-deriving these metrics inside training would let them drift from production.
    """
    return CustomerContext(
        profile=profile,
        financial=analyze_financials(profile),
        portfolio=analyze_portfolio(portfolio),
        requirement=requirement,
    )


def funding_coverage(candidate: Candidate) -> float:
    """Share of the stated requirement this candidate actually funds."""
    if candidate.required_amount <= 0.0:
        return 1.0
    funded = candidate.loan_amount + candidate.liquidation_amount
    return funded / candidate.required_amount


def _gross_liquidated(context: CustomerContext, candidate: Candidate) -> float:
    """Value that actually LEFT the portfolio, including the haircut loss."""
    return max(0.0, context.portfolio.total_value - candidate.remaining_portfolio_value)


# ==========================================================================
# STAGE A — disqualifiers. Nothing else in this policy assigns grade 0.
# ==========================================================================
def disqualify(context: CustomerContext, candidate: Candidate) -> str | None:
    """
    Reason string when the candidate is a forced grade 0, else None.

    EMI-affordability and liquidation-capacity disqualification are NOT re-implemented
    here. They are exactly P5's feasibility rules, already evaluated and recorded on
    candidate.feasible / candidate.infeasibility_reason. Phase R found that a second
    copy of those rules lets the training set and the serving candidate set drift apart
    about what is even possible, so this reads P5's verdict instead.
    """
    if not candidate.feasible:
        return (
            candidate.infeasibility_reason.value
            if candidate.infeasibility_reason
            else "INFEASIBLE"
        )
    if context.financial.monthly_income <= 0.0:
        return "NO_INCOME"
    if candidate.resulting_debt_burden_ratio > HARD_DBR_CAP:
        return "DEBT_BURDEN_CAP_EXCEEDED"
    if funding_coverage(candidate) < FUNDING_DISQUALIFY_BELOW:
        return "FUNDING_SHORTFALL"
    return None


# ==========================================================================
# STAGE B — independent sub-scores. Each owns ONE concern and reads no other's
# inputs. Each is separately unit-tested in tests/test_labeling.py.
# ==========================================================================
def subscore_funding(context: CustomerContext, candidate: Candidate) -> float:
    """
    Concern: does this actually meet the need the customer stated?

    Full coverage scores 1.0 and falls linearly to 0.0 at the disqualification floor.
    Nothing below the floor reaches here — Stage A has already taken it.
    """
    coverage = funding_coverage(candidate)
    span = 1.0 - FUNDING_DISQUALIFY_BELOW
    return _clamp((coverage - FUNDING_DISQUALIFY_BELOW) / span)


def subscore_affordability(context: CustomerContext, candidate: Candidate) -> float:
    """
    Concern: how much of the customer's sustainable EMI capacity this consumes.

    Measured against P1's emi_affordability_ceiling rather than a labeling-specific
    share of disposable income, so training and serving agree on what "affordable"
    means and there is one fewer constant to drift.
    """
    ceiling = context.financial.emi_affordability_ceiling
    if ceiling <= 0.0:
        return 0.0
    return _clamp(1.0 - candidate.emi / ceiling)


def subscore_cost(context: CustomerContext, candidate: Candidate) -> float:
    """
    Concern: what this financing CHOICE costs — interest paid on what is borrowed,
    plus the return forgone on what is sold.
    """
    required = candidate.required_amount
    if required <= 0.0:
        return 1.0

    volatile_used = candidate.volatile_liquidation_amount
    liquid_used = max(0.0, _gross_liquidated(context, candidate) - volatile_used)
    opportunity_cost = liquid_used * (
        (1.0 + LIQUID_ASSET_RETURN) ** OPPORTUNITY_HORIZON_YEARS - 1.0
    ) + volatile_used * (
        (1.0 + VOLATILE_ASSET_RETURN) ** OPPORTUNITY_HORIZON_YEARS - 1.0
    )
    ratio = (candidate.total_interest + opportunity_cost) / required
    return _clamp(1.0 - ratio / MAX_COST_RATIO)


def subscore_portfolio_impact(context: CustomerContext, candidate: Candidate) -> float:
    """
    Concern: what this does to the customer's holdings and their safety margin.
    """
    total = context.portfolio.total_value
    if total <= 0.0:
        return 1.0  # zero portfolio: nothing to impact

    share = _gross_liquidated(context, candidate) / total
    volatile_share = candidate.volatile_liquidation_amount / total
    penalty = share + VOLATILE_IMPACT_MULTIPLIER * volatile_share

    # Emergency-buffer term, in months of expenses. Ratio-based, so scale invariance
    # holds. Without it the policy treats spending savings as free.
    expenses = context.financial.monthly_expenses
    if expenses > 0.0:
        remaining_liquid = (
            candidate.resulting_liquidity_ratio * candidate.remaining_portfolio_value
        )
        buffer_months = remaining_liquid / expenses
        shortfall = (
            max(0.0, TARGET_BUFFER_MONTHS - buffer_months) / TARGET_BUFFER_MONTHS
        )
        penalty += BUFFER_SHORTFALL_WEIGHT * shortfall

    return _clamp(1.0 - penalty)


def subscore_appetite(context: CustomerContext, candidate: Candidate) -> float:
    """
    Concern: how well the leverage and the asset sale match the declared appetite.
    """
    if context.financial.monthly_income <= 0.0:
        return 0.0
    cap = DBR_CAP_BY_APPETITE[context.requirement.risk_appetite]
    score = 1.0 - candidate.resulting_debt_burden_ratio / cap

    total = context.portfolio.total_value
    if total > 0.0 and candidate.volatile_liquidation_amount > 0.0:
        volatile_share = candidate.volatile_liquidation_amount / total
        score -= (
            VOLATILE_APPETITE_PENALTY[context.requirement.risk_appetite]
            * volatile_share
        )
    return _clamp(score)


# ==========================================================================
# STAGE C — documented combination, then within-group rank grading
# ==========================================================================
def score_candidate(context: CustomerContext, candidate: Candidate) -> float:
    """Combined raw score in [0,1]. Scale-invariant by construction."""
    return (
        W_FUNDING * subscore_funding(context, candidate)
        + W_AFFORDABILITY * subscore_affordability(context, candidate)
        + W_COST * subscore_cost(context, candidate)
        + W_PORTFOLIO_IMPACT * subscore_portfolio_impact(context, candidate)
        + W_APPETITE * subscore_appetite(context, candidate)
    )


def _absolute_cap(raw_score: float) -> int:
    """The highest grade this raw score is ALLOWED, regardless of within-group rank."""
    floor_three, floor_two, floor_one = ABSOLUTE_GRADE_FLOORS
    if raw_score >= floor_three:
        return 3
    if raw_score >= floor_two:
        return 2
    if raw_score >= floor_one:
        return 1
    return 0


# ==========================================================================
# STAGE D — stress demotion
# ==========================================================================
def _stress_scenarios() -> list[tuple[bool, float]]:
    rng = random.Random(STRESS_SEED)
    low, high = STRESS_MAGNITUDE_RANGE
    return [
        (rng.random() < STRESS_SHOCK_PROBABILITY, rng.uniform(low, high))
        for _ in range(STRESS_SIMS)
    ]


_SCENARIOS = _stress_scenarios()


def stress_failure_rate(context: CustomerContext, candidate: Candidate) -> float:
    """
    Share of drawn scenarios in which the household cannot cover the new EMI.

    This is the forward-looking component. It is deliberately NOT directly recoverable
    from the feature vector, so the model has something to learn beyond a formula.
    """
    income = context.financial.monthly_income
    expenses = context.financial.monthly_expenses
    existing = context.financial.existing_emi

    failures = 0
    for shocked, magnitude in _SCENARIOS:
        shocked_income = income * (1.0 - magnitude) if shocked else income
        headroom = shocked_income - expenses - existing
        if headroom < candidate.emi:
            failures += 1
    return failures / len(_SCENARIOS)


# ==========================================================================
# the graded result + the entry point
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
    context: CustomerContext,
    candidates: list[Candidate],
    apply_stress: bool = True,
) -> list[GradedCandidate]:
    """
    Grade one customer's whole candidate set. Order is preserved: result[i]
    corresponds to candidates[i].

    NOISE-FREE by design — see apply_label_noise.
    """
    if not candidates:
        return []

    reasons = [disqualify(context, candidate) for candidate in candidates]
    raw_scores = [
        0.0 if reasons[index] else score_candidate(context, candidate)
        for index, candidate in enumerate(candidates)
    ]

    qualified = [index for index in range(len(candidates)) if reasons[index] is None]
    grades = [0] * len(candidates)

    if qualified:
        # Within-group rank. Ties break by original index so ordering is stable and
        # dominance survives grading.
        ordered = sorted(qualified, key=lambda i: (-raw_scores[i], i))
        quantile_three, quantile_two, quantile_one = GRADE_QUANTILES
        for position, index in enumerate(ordered):
            percentile = position / len(ordered)
            if percentile < quantile_three:
                by_rank = 3
            elif percentile < quantile_two:
                by_rank = 2
            elif percentile < quantile_one:
                by_rank = 1
            else:
                by_rank = 0
            grades[index] = min(by_rank, _absolute_cap(raw_scores[index]))

    results = []
    for index, candidate in enumerate(candidates):
        failure_rate = stress_failure_rate(context, candidate)
        grade = grades[index]
        demoted = False
        if apply_stress and grade > MIN_GRADE and failure_rate > STRESS_DEMOTION_THRESHOLD:
            grade -= 1
            demoted = True
        results.append(
            GradedCandidate(
                candidate=candidate,
                raw_score=raw_scores[index],
                grade=grade,
                disqualified_reason=reasons[index],
                stress_failure_rate=failure_rate,
                demoted=demoted,
            )
        )
    return results


def apply_label_noise(grade: int, rng: random.Random) -> int:
    """
    Perturb a grade by one, LABEL_NOISE_RATE of the time.

    DELIBERATELY NOT PART OF grade_group. Noise is, by definition, not
    invariant-preserving: it would break dominance, monotonicity and scale invariance
    on any run where it fired, and those invariants are how the POLICY is verified.
    So the policy is graded noiselessly and verified, and noise is added as an explicit
    final step when the dataset is written. The rng is passed in so the whole dataset
    build stays reproducible from one recorded seed.
    """
    if rng.random() >= LABEL_NOISE_RATE:
        return grade
    step = rng.choice([-1, 1])
    return max(MIN_GRADE, min(MAX_GRADE, grade + step))
