"""
The deterministic template explainer (P13).

THE SYSTEM MUST PRODUCE A SENSIBLE EXPLANATION WITH THE LLM UNAVAILABLE. This module
is that guarantee, and it is also where a grounding rejection lands: an LLM response
that invents a figure is discarded and replaced by this.

It writes from the payload only, so by construction it cannot invent a number or a
product name — every figure it prints is a display string the payload already carries.

Covers all five recommendation statuses.
"""

from app.schemas import Recommendation
from app.schemas.enums import RecommendationSource, RecommendationStatus

from app.explain.payloads import (
    REASON_DESCRIPTIONS,
    STATUS_DESCRIPTIONS,
    build_mismatch_payload,
    build_recommendation_payload,
)

FALLBACK_NOTICE = (
    "Please note: our personalised model was unavailable, so this came from the "
    "system's backup rules rather than a personalised match."
)


def _recommended_text(payload: dict) -> str:
    recommendation = payload["recommendation"]
    display = recommendation["display"]
    parts: list[str] = []

    if payload.get("is_deterministic_fallback"):
        parts.append(FALLBACK_NOTICE)

    if recommendation["borrows"]:
        parts.append(
            f"We recommend borrowing {display['loan_amount']} from "
            f"{recommendation['lender']} ({recommendation['product_name']}) over "
            f"{display['tenure']}, at {display['emi']} a month."
        )
        parts.append(
            f"Over the full term that adds up to {display['total_repayment']}, of "
            f"which {display['total_interest']} is interest."
        )
    else:
        parts.append(
            f"We recommend paying {display['liquidation_amount']} from your existing "
            "holdings and not taking a loan at all."
        )
        parts.append(
            f"That would leave {display['remaining_portfolio_value']} of your "
            "portfolio invested."
        )

    if recommendation["borrows"] and recommendation["liquidation_amount"] > 0:
        parts.append(
            f"This also involves selling {display['liquidation_amount']} of your "
            "holdings."
        )

    reasons = payload.get("why_this_option") or []
    if reasons:
        parts.append("We suggest this because " + ", and ".join(reasons) + ".")

    blocked = payload.get("blocked_choice")
    if blocked:
        parts.append(
            "One thing worth knowing: our model's closest match for you was "
            f"{blocked['display']['summary']}, but we are not offering it because "
            f"{blocked['rule_description']}."
        )

    if payload.get("alternatives_count"):
        parts.append(
            f"There are {payload['alternatives_count']} other options available if "
            "you would like to compare."
        )

    return "\n\n".join(parts)


def _mismatch_text(payload: dict) -> str:
    parts: list[str] = []

    if payload.get("is_deterministic_fallback"):
        parts.append(FALLBACK_NOTICE)

    parts.append(
        "We could not find a loan in our current catalogue that would be a good fit "
        "for what you asked for. This is about the products available, not about you."
    )
    parts.append(payload["coverage"]["display"]["funnel"] + ".")

    # Deduplicate reason TEXT, so a dozen products failing the same rule reads as one
    # sentence rather than twelve.
    seen: list[str] = []
    for reason in payload["reasons"]:
        if reason["text"] not in seen:
            seen.append(reason["text"])
    if seen:
        parts.append(
            "The main reasons were: " + "; ".join(seen[:4]) + "."
        )

    parts.append(
        "If your requirement changes — a different amount, a longer tenure, or a "
        "different purpose — it is worth checking again."
    )
    return "\n\n".join(parts)


def template_explanation(recommendation: Recommendation) -> str:
    """
    A complete explanation for any of the five statuses, with no LLM involved.
    """
    if recommendation.status is RecommendationStatus.RECOMMENDED:
        return _recommended_text(build_recommendation_payload(recommendation))
    return _mismatch_text(build_mismatch_payload(recommendation))


def status_sentence(recommendation: Recommendation) -> str:
    """One line describing the outcome. Used by the UI and by the mismatch screen."""
    base = STATUS_DESCRIPTIONS[recommendation.status]
    if recommendation.source is RecommendationSource.DETERMINISTIC_FALLBACK:
        return f"{base} (from the deterministic backup, not the personalised model)"
    return base


def reason_sentence(code: str) -> str:
    """Render one reason code. The system's words, never the model's."""
    return REASON_DESCRIPTIONS.get(code, code)
