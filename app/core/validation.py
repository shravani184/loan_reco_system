"""
Deterministic re-verification of the ML's chosen candidate (P12).

It independently re-derives what the candidate CLAIMS and compares. It answers
pass/fail and nothing else: it never re-ranks, never adjusts a value, and NEVER
SILENTLY CORRECTS A CANDIDATE (CONTEXT.md section 4).

A failure here is a DEFECT SIGNAL, not a routine outcome. Candidate generation
computed these figures; if validation disagrees, either the arithmetic drifted or a
candidate was mutated in flight. It is logged at error level, recorded in the trace,
and the walk moves to the next ML-ranked candidate.

EMI IS RECOMPUTED FROM app/core/finance_math.py — the single implementation. The
comparison uses EMI_VALIDATION_TOLERANCE_RUPEES rather than float equality, because
money is float rupees and "matches to the rupee" cannot be expressed as `==`.
"""

import logging

from app.config import settings
from app.core.finance_math import emi as compute_emi
from app.core.finance_math import total_interest, total_repayment
from app.schemas import (
    Candidate,
    FinancialMetrics,
    LoanProduct,
    PortfolioMetrics,
    ValidationResult,
)
from app.schemas.enums import FinancingStrategy

logger = logging.getLogger(__name__)


def _failure(check: str, expected: float, observed: float) -> ValidationResult:
    return ValidationResult(
        passed=False,
        failed_check=check,
        expected_value=expected,
        observed_value=observed,
    )


def validate_candidate(
    candidate: Candidate,
    product: LoanProduct | None,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
) -> ValidationResult:
    """
    Re-verify one candidate. Pure: nothing is mutated, nothing is corrected.

    Checks run in a fixed order and the FIRST failure is returned, so the same input
    always names the same check:

      1. EMI matches a fresh computation from the canonical formula
      2. total interest and total repayment match that EMI
      3. the loan sits inside the product's amount limits
      4. the tenure sits inside the product's tenure limits
      5. the EMI is within the affordability ceiling
      6. the liquidation does not exceed what the portfolio holds

    The no-loan candidate (LIQUIDATE_100) borrows nothing, so checks 1-5 are trivially
    satisfied by zero and the product checks do not apply — it has no product.
    """
    tolerance = settings.EMI_VALIDATION_TOLERANCE_RUPEES
    borrows = candidate.strategy is not FinancingStrategy.LIQUIDATE_100

    if borrows:
        if product is None:
            return ValidationResult(
                passed=False,
                failed_check="product_present",
                expected_value=1.0,
                observed_value=0.0,
            )

        # 1. THE EMI, recomputed from the one canonical formula.
        expected_emi = compute_emi(
            candidate.loan_amount, product.annual_rate, candidate.tenure_months
        )
        if abs(expected_emi - candidate.emi) > tolerance:
            logger.error(
                "validation defect: candidate %s claims EMI %.2f, recomputation gives "
                "%.2f (tolerance %.2f)",
                candidate.candidate_id,
                candidate.emi,
                expected_emi,
                tolerance,
            )
            return _failure("emi_matches_recomputation", expected_emi, candidate.emi)

        # 2. The derived cost figures must follow from that same EMI.
        expected_interest = total_interest(
            candidate.loan_amount, product.annual_rate, candidate.tenure_months
        )
        if abs(expected_interest - candidate.total_interest) > tolerance:
            logger.error(
                "validation defect: candidate %s claims total interest %.2f, "
                "recomputation gives %.2f",
                candidate.candidate_id,
                candidate.total_interest,
                expected_interest,
            )
            return _failure(
                "total_interest_matches_recomputation",
                expected_interest,
                candidate.total_interest,
            )

        expected_repayment = total_repayment(
            candidate.loan_amount, product.annual_rate, candidate.tenure_months
        )
        if abs(expected_repayment - candidate.total_repayment) > tolerance:
            return _failure(
                "total_repayment_matches_recomputation",
                expected_repayment,
                candidate.total_repayment,
            )

        # 3. Product amount limits.
        if candidate.loan_amount < product.min_amount:
            return _failure(
                "loan_amount_within_product_minimum",
                product.min_amount,
                candidate.loan_amount,
            )
        if candidate.loan_amount > product.max_amount:
            return _failure(
                "loan_amount_within_product_maximum",
                product.max_amount,
                candidate.loan_amount,
            )

        # 4. Product tenure limits.
        if candidate.tenure_months < product.min_tenure_months:
            return _failure(
                "tenure_within_product_minimum",
                float(product.min_tenure_months),
                float(candidate.tenure_months),
            )
        if candidate.tenure_months > product.max_tenure_months:
            return _failure(
                "tenure_within_product_maximum",
                float(product.max_tenure_months),
                float(candidate.tenure_months),
            )

    # 5. Affordability. Re-checked here even though P5 marked feasibility, because the
    #    point of this module is to trust nothing upstream computed.
    if candidate.emi > financial_metrics.emi_affordability_ceiling + tolerance:
        return _failure(
            "emi_within_affordability_ceiling",
            financial_metrics.emi_affordability_ceiling,
            candidate.emi,
        )

    # 6. The liquidation must not exceed what the customer actually holds. Compared on
    #    the GROSS value leaving the portfolio, which is what P5 computed and what the
    #    guardrail also measures.
    gross_liquidated = portfolio_metrics.total_value - candidate.remaining_portfolio_value
    if gross_liquidated > portfolio_metrics.total_value + tolerance:
        return _failure(
            "liquidation_within_portfolio",
            portfolio_metrics.total_value,
            gross_liquidated,
        )
    if candidate.liquidation_amount > portfolio_metrics.total_value + tolerance:
        return _failure(
            "liquidation_within_portfolio",
            portfolio_metrics.total_value,
            candidate.liquidation_amount,
        )

    return ValidationResult(passed=True)
