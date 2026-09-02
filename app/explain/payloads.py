"""
Prompt payload construction (P13).

EVERY FIGURE ENTERS A PROMPT TWICE: as a number, and as a pre-formatted DISPLAY
STRING that the prompt instructs the model to reproduce verbatim. That is the primary
defence against invented numbers — the guard is only the safety net (CONTEXT.md 17.3
decision 1). Comparing against strings the system itself wrote is a far easier problem
than parsing arbitrary prose.

NO PII EVER ENTERS A PAYLOAD. Not a name, not contact details, not an identity number.
The pseudonymous user_id is deliberately excluded too — the LLM has no use for it and
a payload is the easiest place for an identifier to leak into a third-party service.

The numeric values are included alongside the display strings because the grounding
guard builds its accepted set from them.
"""

from app.config import settings
from app.schemas import Recommendation
from app.schemas.enums import RecommendationSource, RecommendationStatus

# Indian digit grouping: the last three digits, then pairs. 600000 -> "6,00,000".
def format_rupees(amount: float) -> str:
    rounded = int(round(amount))
    sign = "-" if rounded < 0 else ""
    digits = str(abs(rounded))
    if len(digits) <= 3:
        return f"{sign}Rs {digits}"
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}Rs {','.join(groups)},{tail}"


def format_months(months: int | None) -> str:
    if months is None:
        return "not applicable"
    return f"{months} months"


def format_percent(value: float) -> str:
    return f"{value:.1f}%"


def format_score(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:.2f}"


STATUS_DESCRIPTIONS = {
    RecommendationStatus.RECOMMENDED: "a suitable option was found",
    RecommendationStatus.NO_ELIGIBLE_PRODUCTS: (
        "no product in the catalogue could be considered, because none of them accept "
        "this combination of purpose, amount, tenure, credit score and income"
    ),
    RecommendationStatus.NO_FEASIBLE_CANDIDATES: (
        "products could be considered, but no combination of amount, tenure and "
        "funding method produced a repayment this customer could sustain"
    ),
    RecommendationStatus.ALL_CANDIDATES_BLOCKED: (
        "workable options existed, but every one of them exceeded a limit set by the "
        "risk appetite the customer declared"
    ),
    RecommendationStatus.NO_SUITABLE_LOAN: (
        "options were available and were scored, but none was a good enough match for "
        "this customer to be worth recommending"
    ),
}

REASON_DESCRIPTIONS = {
    "CREDIT_SCORE_BELOW_MINIMUM": "the product needs a higher credit score",
    "INCOME_BELOW_MINIMUM": "the product needs a higher monthly income",
    "AMOUNT_ABOVE_PRODUCT_MAX": "the amount requested is above the product's maximum",
    "AMOUNT_BELOW_PRODUCT_MIN": "the amount requested is below the product's minimum",
    "TENURE_OUT_OF_RANGE": "the preferred tenure is outside the product's range",
    "PURPOSE_NOT_SUPPORTED": "the product is not offered for this purpose",
    "EMI_EXCEEDS_AFFORDABILITY": (
        "the monthly repayment would be more than this customer can sustain"
    ),
    "LIQUIDATION_EXCEEDS_PORTFOLIO": (
        "funding it this way would need more holdings than the customer has"
    ),
    "REQUIRED_AMOUNT_UNREACHABLE": (
        "no available combination could raise the full amount requested"
    ),
    "DEBT_BURDEN_CAP_EXCEEDED": (
        "the total monthly commitment would exceed the limit for the declared risk "
        "appetite"
    ),
    "LOAN_TO_INCOME_CAP_EXCEEDED": (
        "the loan would be a larger multiple of income than the declared risk appetite "
        "allows"
    ),
    "LIQUIDATION_SHARE_CAP_EXCEEDED": (
        "it would require selling more of the portfolio than the declared risk "
        "appetite allows"
    ),
    "VOLATILE_ASSET_LIQUIDATION_PROHIBITED": (
        "it would require selling shares or crypto, which the declared risk appetite "
        "does not permit"
    ),
    "SUITABILITY_BELOW_THRESHOLD": (
        "the best available option still was not a good enough personal match"
    ),
}


def _candidate_payload(candidate) -> dict:
    """
    THE NO-LOAN CANDIDATE has no product, lender or tenure. It is described as "pay
    from your holdings and borrow nothing" rather than as a zero-month loan, because
    rendering it as a loan would be simply wrong (Phase R finding).
    """
    borrows = candidate.loan_amount > 0
    return {
        "borrows": borrows,
        "product_name": candidate.product_id,
        "lender": candidate.lender,
        "loan_amount": candidate.loan_amount,
        "tenure_months": candidate.tenure_months,
        "emi": candidate.emi,
        "total_interest": candidate.total_interest,
        "total_repayment": candidate.total_repayment,
        "liquidation_amount": candidate.liquidation_amount,
        "remaining_portfolio_value": candidate.remaining_portfolio_value,
        "display": {
            "summary": (
                f"borrow {format_rupees(candidate.loan_amount)} over "
                f"{format_months(candidate.tenure_months)}"
                if borrows
                else "pay from your holdings and borrow nothing"
            ),
            "loan_amount": format_rupees(candidate.loan_amount),
            "tenure": format_months(candidate.tenure_months),
            "emi": format_rupees(candidate.emi),
            "total_interest": format_rupees(candidate.total_interest),
            "total_repayment": format_rupees(candidate.total_repayment),
            "liquidation_amount": format_rupees(candidate.liquidation_amount),
            "remaining_portfolio_value": format_rupees(
                candidate.remaining_portfolio_value
            ),
        },
    }


def _why_this_option(recommendation: Recommendation) -> list[str]:
    """
    Reasons drawn ONLY from computed facts. Never a claim the pipeline did not make.
    """
    items: list[str] = []
    candidate = recommendation.selected_candidate
    if candidate is None:
        return items
    if candidate.loan_amount == 0:
        items.append("it avoids borrowing entirely")
    if candidate.affordability_headroom > 0:
        items.append(
            "the monthly repayment leaves room inside what this customer can sustain"
        )
    if candidate.liquidation_amount == 0 and candidate.loan_amount > 0:
        items.append("it leaves the customer's investments untouched")
    if recommendation.risk is not None and not recommendation.risk.imputed:
        items.append(
            f"the assessed risk band for this customer is "
            f"{recommendation.risk.risk_class.value.lower()}"
        )
    return items


def entity_vocabulary(recommendation: Recommendation) -> tuple[list[str], list[str]]:
    """
    (entities allowed in the response, the full known vocabulary).

    The guard checks a KNOWN vocabulary rather than guessing at capitalised phrases,
    so it needs both: what this payload legitimately mentions, and what else exists
    and would therefore be an invention.
    """
    allowed: set[str] = set()
    known: set[str] = set()
    for scored in recommendation.decision_trace.ranked_candidates:
        if scored.candidate.lender:
            known.add(scored.candidate.lender)
        if scored.candidate.product_id:
            known.add(scored.candidate.product_id)
    for source in (recommendation.selected_candidate,):
        if source is not None:
            if source.lender:
                allowed.add(source.lender)
            if source.product_id:
                allowed.add(source.product_id)
    for alternative in recommendation.alternatives:
        if alternative.candidate.lender:
            allowed.add(alternative.candidate.lender)
        if alternative.candidate.product_id:
            allowed.add(alternative.candidate.product_id)
    if recommendation.ml_top_choice_blocked is not None:
        blocked = recommendation.ml_top_choice_blocked.candidate
        if blocked.lender:
            allowed.add(blocked.lender)
        if blocked.product_id:
            allowed.add(blocked.product_id)
    return sorted(allowed), sorted(known | allowed)


def build_recommendation_payload(recommendation: Recommendation) -> dict:
    """
    The payload for a successful recommendation.

    Carries the FALLBACK FACT when the ordering came from the deterministic backup, so
    the prompt can require the explanation to say so. A fallback described as an ML
    recommendation is a correctness defect, not a cosmetic one (AGENTS.md section 7.4).
    """
    is_fallback = recommendation.source is RecommendationSource.DETERMINISTIC_FALLBACK
    coverage = recommendation.coverage

    payload: dict = {
        "status": recommendation.status.value,
        "status_description": STATUS_DESCRIPTIONS[recommendation.status],
        "source": recommendation.source.value,
        "is_deterministic_fallback": is_fallback,
        "fallback_notice": (
            "The personalised model was unavailable. This recommendation came from the "
            "system's deterministic backup rules. It is not a model-based personalised "
            "recommendation and there is no suitability score."
            if is_fallback
            else None
        ),
        "coverage": {
            "catalogue_products": coverage.catalogue_products,
            "products_passing_eligibility": coverage.products_passing_eligibility,
            "candidates_considered": coverage.candidates_scored,
            "display": {
                "summary": (
                    f"{coverage.products_passing_eligibility} of "
                    f"{coverage.catalogue_products} products could be considered, and "
                    f"{coverage.candidates_scored} specific options were assessed"
                )
            },
        },
        "alternatives_count": len(recommendation.alternatives),
    }

    if recommendation.selected_candidate is not None:
        payload["recommendation"] = _candidate_payload(recommendation.selected_candidate)
        payload["why_this_option"] = _why_this_option(recommendation)

    # Suitability appears ONLY when the model produced one. Under fallback it is None
    # and is omitted entirely, so the model cannot mention a score that does not exist.
    if recommendation.ml_suitability is not None:
        payload["suitability"] = recommendation.ml_suitability
        payload["display_suitability"] = format_score(recommendation.ml_suitability)

    if recommendation.risk is not None:
        payload["risk"] = {
            "band": recommendation.risk.risk_class.value,
            "imputed": recommendation.risk.imputed,
            "display": {
                "band": recommendation.risk.risk_class.value.lower(),
            },
        }

    if recommendation.ml_top_choice_blocked is not None:
        blocked = recommendation.ml_top_choice_blocked
        payload["blocked_choice"] = {
            **_candidate_payload(blocked.candidate),
            "rule": blocked.blocking_rule,
            "reason_code": blocked.reason_code.value,
            "rule_description": REASON_DESCRIPTIONS.get(
                blocked.reason_code.value, blocked.reason_code.value
            ),
        }

    return payload


def build_mismatch_payload(recommendation: Recommendation) -> dict:
    """
    The payload for a no-recommendation outcome.

    Reasons are rendered from the SYSTEM'S OWN description table, not left to the
    model. The LLM renders these reasons; it does not author them
    (CONTEXT.md non-negotiable 14).
    """
    coverage = recommendation.coverage
    reasons = []
    for reason in recommendation.mismatch_reasons:
        reasons.append(
            {
                "code": reason.code.value,
                "text": REASON_DESCRIPTIONS.get(reason.code.value, reason.code.value),
                "product_id": reason.product_id,
                "observed_value": reason.observed_value,
                "threshold_value": reason.threshold_value,
            }
        )

    return {
        "status": recommendation.status.value,
        "status_description": STATUS_DESCRIPTIONS[recommendation.status],
        "source": recommendation.source.value,
        "is_deterministic_fallback": (
            recommendation.source is RecommendationSource.DETERMINISTIC_FALLBACK
        ),
        "coverage": {
            "catalogue_products": coverage.catalogue_products,
            "products_passing_eligibility": coverage.products_passing_eligibility,
            "products_with_feasible_candidates": (
                coverage.products_with_feasible_candidates
            ),
            "candidates_considered": coverage.candidates_scored,
            "candidates_above_threshold": (
                coverage.candidates_above_suitability_threshold
            ),
            "display": {
                "funnel": (
                    f"{coverage.catalogue_products} products were checked, "
                    f"{coverage.products_passing_eligibility} could be considered, and "
                    f"{coverage.candidates_scored} specific options were assessed"
                )
            },
        },
        "reasons": reasons,
    }
