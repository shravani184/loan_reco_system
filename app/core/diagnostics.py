"""
The diagnostic utility score — DETERMINISTIC, ADVISORY ONLY.

This is the v1.0 weighted utility function, surviving under a name that cannot be
mistaken for the primary recommender. Its only permitted uses (CONTEXT.md section 4):

  1. DETERMINISTIC FALLBACK ranking, when the ML recommender is unavailable — and only
     with recommendation_source = DETERMINISTIC_FALLBACK stamped on the output.
  2. DIAGNOSTICS AND AUDIT — recorded in the trace beside the ML score so the two can
     be compared offline, and used as a mandatory evaluation baseline at P10.

IT MAY NEVER REORDER, VETO OR ADJUST AN ML RECOMMENDATION DURING NORMAL OPERATION
(CONTEXT.md non-negotiable 1). If you find this being called from the orchestrator on
a path where the recommender succeeded, that is the architectural regression this
redesign exists to prevent.

Scope note: built at P10 only as far as the mandatory baseline comparison needs. P12
wires it into the fallback path and the trace; it does not re-implement it.

Every weight comes from settings.DIAGNOSTIC_WEIGHTS and is version-stamped.
"""

from app.config import settings
from app.schemas import Candidate, FinancialMetrics, PortfolioMetrics


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0.0 else 0.0


def affordability_component(
    financial: FinancialMetrics, candidate: Candidate
) -> float:
    """Share of the customer's EMI capacity left unused. Higher is better."""
    return _clamp(
        _ratio(candidate.affordability_headroom, financial.emi_affordability_ceiling)
    )


def cost_component(candidate: Candidate) -> float:
    """Cost of credit against the amount required. Higher is cheaper."""
    return _clamp(1.0 - _ratio(candidate.total_interest, candidate.required_amount))


def portfolio_impact_component(
    portfolio: PortfolioMetrics, candidate: Candidate
) -> float:
    """
    Share of the portfolio consumed, GROSS of the haircut — the same measure the
    guardrail uses, so the two cannot disagree about what "impact" means.
    """
    if portfolio.total_value <= 0.0:
        return 0.0
    consumed = portfolio.total_value - candidate.remaining_portfolio_value
    return _clamp(_ratio(consumed, portfolio.total_value))


def soft_constraint_component(candidate: Candidate) -> float:
    """
    Soft misses: funding less than the customer asked for. Not a hard rule — a
    partially funded option is a compromise, not an impossibility — so it is a penalty
    rather than an exclusion.
    """
    funded = candidate.loan_amount + candidate.liquidation_amount
    shortfall = candidate.required_amount - funded
    return _clamp(_ratio(shortfall, candidate.required_amount))


def diagnostic_utility_score(
    financial: FinancialMetrics,
    portfolio: PortfolioMetrics,
    candidate: Candidate,
    risk_pd: float,
) -> float:
    """
    ADVISORY. A deterministic quality score for one candidate.

        w1 * affordability_headroom
      + w2 * (1 - risk_pd)
      + w3 * cost_efficiency
      - w4 * portfolio_impact_penalty
      - w5 * soft_constraint_violations

    Unbounded below by construction (the penalties can exceed the rewards), which is
    fine: only its ORDER is ever used, never its absolute value.
    """
    weights = settings.DIAGNOSTIC_WEIGHTS
    return (
        weights.w1_affordability_headroom * affordability_component(financial, candidate)
        + weights.w2_inverse_risk * (1.0 - _clamp(risk_pd))
        + weights.w3_cost_efficiency * cost_component(candidate)
        - weights.w4_portfolio_impact_penalty
        * portfolio_impact_component(portfolio, candidate)
        - weights.w5_soft_constraint_penalty * soft_constraint_component(candidate)
    )
