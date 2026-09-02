"""
Risk-Tolerance Guardrails — rule-based policy, pass/fail only.

ARCHITECTURAL POSITION (this is the v2.0 change): guardrails no longer pre-filter the
option space before ML. They VALIDATE candidates the recommender has ALREADY RANKED,
one at a time, in rank order, during P12's validation walk.

That is why this is a pure function over a SINGLE candidate. It takes no list, returns
no list, and cannot filter one. It never deletes an option, never chooses one, and
never reorders anything. A blocked candidate is returned flagged with its reason so
P12 can surface "the model's best match for you was X, but rule R blocked it, so we
recommend Y" (CONTEXT.md section 4).

Every cap comes from settings.GUARDRAIL_CAPS[risk_appetite]. Caps are never widened to
make a demo produce a recommendation (AGENTS.md section 10).
"""

from app.config import GuardrailCaps, settings
from app.core.finance_math import MONTHS_PER_YEAR
from app.core.financial import income_ratio
from app.schemas import Candidate, FinancialMetrics, GuardrailResult, PortfolioMetrics
from app.schemas.enums import GuardrailRule, MismatchReasonCode, RiskAppetite

# One reason code per rule. A rule with no code could not be explained to the user,
# and a code with no rule would be a reason nobody can trace to an evaluation.
_REASON_FOR_RULE: dict[GuardrailRule, MismatchReasonCode] = {
    GuardrailRule.MAX_DEBT_BURDEN_RATIO: MismatchReasonCode.DEBT_BURDEN_CAP_EXCEEDED,
    GuardrailRule.MAX_LOAN_TO_INCOME_MULTIPLE: (
        MismatchReasonCode.LOAN_TO_INCOME_CAP_EXCEEDED
    ),
    GuardrailRule.MAX_LIQUIDATION_SHARE: (
        MismatchReasonCode.LIQUIDATION_SHARE_CAP_EXCEEDED
    ),
    GuardrailRule.VOLATILE_ASSET_LIQUIDATION: (
        MismatchReasonCode.VOLATILE_ASSET_LIQUIDATION_PROHIBITED
    ),
}


def liquidation_share(
    portfolio_metrics: PortfolioMetrics, candidate: Candidate
) -> float:
    """
    Fraction of the portfolio consumed, measured GROSS of the haircut.

    NOT candidate.liquidation_amount, which is the net funding contribution: the
    customer loses the haircut too, and a cap on "how much of your portfolio may be
    liquidated" has to mean how much actually leaves the portfolio.

    A customer with no portfolio consumes none of it, so the share is zero rather
    than a division by zero.
    """
    if portfolio_metrics.total_value <= 0.0:
        return 0.0
    consumed = portfolio_metrics.total_value - candidate.remaining_portfolio_value
    return consumed / portfolio_metrics.total_value


def loan_to_income_multiple(
    financial_metrics: FinancialMetrics, candidate: Candidate
) -> float:
    """
    Loan size as a multiple of ANNUAL income.

    Annual, not monthly. The configured caps (8 / 12 / 18) are ordinary
    loan-to-income multiples, which are conventionally annual; read against monthly
    income they would reject almost every genuine home loan. Stated explicitly
    because it is the single easiest thing in this module to get backwards.

    Uses P1's zero-income convention rather than a second copy of it.
    """
    annual_income = financial_metrics.monthly_income * MONTHS_PER_YEAR
    return income_ratio(candidate.loan_amount, annual_income)


def _evaluate(
    rule: GuardrailRule,
    caps: GuardrailCaps,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    candidate: Candidate,
) -> tuple[float, float] | None:
    """
    Evaluate one rule. Returns (observed, cap) on a VIOLATION, None when it passes.
    """
    if rule is GuardrailRule.MAX_DEBT_BURDEN_RATIO:
        # Already includes the new EMI — computed by P5, not recomputed here.
        observed = candidate.resulting_debt_burden_ratio
        cap = caps.max_debt_burden_ratio
        return (observed, cap) if observed > cap else None

    if rule is GuardrailRule.MAX_LOAN_TO_INCOME_MULTIPLE:
        observed = loan_to_income_multiple(financial_metrics, candidate)
        cap = caps.max_loan_to_income_multiple
        return (observed, cap) if observed > cap else None

    if rule is GuardrailRule.MAX_LIQUIDATION_SHARE:
        observed = liquidation_share(portfolio_metrics, candidate)
        cap = caps.max_liquidation_share
        return (observed, cap) if observed > cap else None

    if rule is GuardrailRule.VOLATILE_ASSET_LIQUIDATION:
        # Categorical, not a magnitude: under a prohibition the permitted amount is
        # zero, so the cap reported to the user is 0.0 and the observed value is what
        # the candidate would have sold.
        if caps.allow_volatile_liquidation:
            return None
        observed = candidate.volatile_liquidation_amount
        return (observed, 0.0) if observed > 0.0 else None

    raise ValueError(f"no evaluation defined for guardrail rule {rule}")


def check_guardrails(
    risk_appetite: RiskAppetite,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    candidate: Candidate,
) -> GuardrailResult:
    """
    Pass/fail one candidate against the caps for this declared risk appetite.

    Rules are evaluated in settings.GUARDRAIL_RULE_ORDER and the FIRST violation is
    returned, so the same input always names the same rule. Pure: no I/O, no global
    state, no model call, and the candidate is not modified.
    """
    caps = settings.GUARDRAIL_CAPS[risk_appetite]

    for rule in settings.GUARDRAIL_RULE_ORDER:
        violation = _evaluate(
            rule, caps, financial_metrics, portfolio_metrics, candidate
        )
        if violation is None:
            continue
        observed, cap = violation
        return GuardrailResult(
            allowed=False,
            violated_rule=rule.value,
            reason_code=_REASON_FOR_RULE[rule],
            cap_value=cap,
            observed_value=observed,
        )

    return GuardrailResult(allowed=True)
