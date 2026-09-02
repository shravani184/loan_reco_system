"""
Eligibility Engine — rule-based hard constraints, no ML.

Answers ONE question: can this catalogue product be considered at all? It runs BEFORE
candidate generation and BEFORE the recommender (CONTEXT.md section 3).

It is NOT the "is this right for you" question. That is the recommender's, in P10.
This module does not score, does not rank, does not compute an EMI, and does not
check affordability — affordability is feasibility and belongs to P5.

EVERY CATALOGUE PRODUCT APPEARS IN THE OUTPUT, always, with an outcome. A silently
dropped product becomes an unexplainable gap in the coverage funnel and the decision
trace, so the returned list is the same length as the catalogue by construction.

Every threshold is a property of the LoanProduct being checked. There are no numbers
in this file.
"""

from app.schemas import (
    CustomerProfile,
    EligibilityResult,
    FinancialMetrics,
    LoanProduct,
    LoanRequirement,
)
from app.schemas.enums import EligibilityStatus, MismatchReasonCode


def _first_failure(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    requirement: LoanRequirement,
    product: LoanProduct,
) -> tuple[MismatchReasonCode, float | None, float | None] | None:
    """
    The first hard rule this product fails, as (reason code, observed, threshold).

    RULE ORDER IS DEFINED AND DELIBERATE, because EligibilityResult carries exactly
    one reason code and the first failure is the one the user is shown:

      1. purpose        a product for a different purpose is not a near miss, it is
                        the wrong product entirely
      2. credit score   the constraint the customer can least quickly change
      3. income         likewise, and both are about the person
      4. amount         about the request, and adjustable by the customer
      5. tenure         likewise, and the most easily adjusted of all

    Reporting the least-adjustable failure first means the reason shown is the one
    that actually blocks them, not a formality they could fix in a second.
    """
    if requirement.purpose not in product.purposes:
        # Purpose is categorical, so there is no meaningful observed/threshold pair.
        # The schema allows both to be None; the code and the product id carry the
        # whole explanation here.
        return (MismatchReasonCode.PURPOSE_NOT_SUPPORTED, None, None)

    if customer.credit_score < product.min_credit_score:
        return (
            MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM,
            float(customer.credit_score),
            float(product.min_credit_score),
        )

    # Income comes from FinancialMetrics, which owns it, rather than being re-read
    # from the raw profile (AGENTS.md section 2).
    if financial_metrics.monthly_income < product.min_monthly_income:
        return (
            MismatchReasonCode.INCOME_BELOW_MINIMUM,
            financial_metrics.monthly_income,
            product.min_monthly_income,
        )

    if requirement.required_amount < product.min_amount:
        return (
            MismatchReasonCode.AMOUNT_BELOW_PRODUCT_MIN,
            requirement.required_amount,
            product.min_amount,
        )

    if requirement.required_amount > product.max_amount:
        return (
            MismatchReasonCode.AMOUNT_ABOVE_PRODUCT_MAX,
            requirement.required_amount,
            product.max_amount,
        )

    tenure = requirement.preferred_tenure_months
    if tenure < product.min_tenure_months:
        return (
            MismatchReasonCode.TENURE_OUT_OF_RANGE,
            float(tenure),
            float(product.min_tenure_months),
        )
    if tenure > product.max_tenure_months:
        return (
            MismatchReasonCode.TENURE_OUT_OF_RANGE,
            float(tenure),
            float(product.max_tenure_months),
        )

    return None


def check_eligibility(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    requirement: LoanRequirement,
    catalogue: list[LoanProduct],
) -> list[EligibilityResult]:
    """
    One EligibilityResult per catalogue product, in catalogue order.

    Pure: no I/O, no global state, no model calls, inputs not mutated.
    """
    results: list[EligibilityResult] = []

    for product in catalogue:
        failure = _first_failure(customer, financial_metrics, requirement, product)

        if failure is None:
            results.append(
                EligibilityResult(
                    product_id=product.product_id,
                    status=EligibilityStatus.ELIGIBLE,
                )
            )
            continue

        reason_code, observed, threshold = failure
        results.append(
            EligibilityResult(
                product_id=product.product_id,
                status=EligibilityStatus.INELIGIBLE,
                reason_code=reason_code,
                observed_value=observed,
                threshold_value=threshold,
            )
        )

    return results
