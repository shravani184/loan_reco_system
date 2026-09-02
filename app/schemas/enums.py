"""
Every string constant in the system.

Nothing anywhere else compares against a raw string. If a new categorical value is
needed, it is added here first (AGENTS.md section 3).

All members inherit from `str` so they serialize as their value over the API and are
usable as dict keys in config without extra conversion.
"""

from enum import Enum


class RiskAppetite(str, Enum):
    """Declared by the customer. Selects the guardrail cap set (config)."""

    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class FinancialHealth(str, Enum):
    """Band emitted by Financial Intelligence (P1). Ordered best to worst."""

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class PortfolioRisk(str, Enum):
    """Band emitted by Portfolio Intelligence (P2). Ordered lowest to highest risk."""

    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    GROWTH = "GROWTH"
    AGGRESSIVE = "AGGRESSIVE"


class RiskClass(str, Enum):
    """Output class of the SECONDARY risk classifier (P9). A feature, not a decision."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FinancingStrategy(str, Enum):
    """
    How the required amount is funded: borrow share / liquidate share.

    LIQUIDATE_100 is the "no loan" candidate — nothing is borrowed, so it carries no
    product and no tenure (see Candidate). Phase R finding: it is generated exactly
    once per customer, not once per product x tenure.
    """

    BORROW_100 = "BORROW_100"
    BORROW_80_LIQUIDATE_20 = "BORROW_80_LIQUIDATE_20"
    BORROW_60_LIQUIDATE_40 = "BORROW_60_LIQUIDATE_40"
    BORROW_40_LIQUIDATE_60 = "BORROW_40_LIQUIDATE_60"
    BORROW_20_LIQUIDATE_80 = "BORROW_20_LIQUIDATE_80"
    LIQUIDATE_100 = "LIQUIDATE_100"


class LoanPurpose(str, Enum):
    HOME = "HOME"
    VEHICLE = "VEHICLE"
    EDUCATION = "EDUCATION"
    PERSONAL = "PERSONAL"
    BUSINESS = "BUSINESS"
    MEDICAL = "MEDICAL"


class AssetType(str, Enum):
    """Portfolio holding types. Liquidity and haircuts per type live in config."""

    STOCKS = "STOCKS"
    MUTUAL_FUNDS = "MUTUAL_FUNDS"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    BONDS = "BONDS"
    CASH = "CASH"
    CRYPTO = "CRYPTO"


class EmploymentType(str, Enum):
    SALARIED = "SALARIED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    CONTRACT = "CONTRACT"
    RETIRED = "RETIRED"


class FeedbackEventType(str, Enum):
    """
    Interaction recorded by the personalization store (P3). A feature source only —
    an ACCEPTED event never approves anything and a DECLINED event never blocks
    anything.
    """

    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class RecommendationStatus(str, Enum):
    """
    WHAT happened. Separate axis from RecommendationSource (CONTEXT.md 5.2/5.3).

    A fallback is NOT a status. Never add DETERMINISTIC_FALLBACK here.
    """

    RECOMMENDED = "RECOMMENDED"
    NO_ELIGIBLE_PRODUCTS = "NO_ELIGIBLE_PRODUCTS"
    NO_FEASIBLE_CANDIDATES = "NO_FEASIBLE_CANDIDATES"
    ALL_CANDIDATES_BLOCKED = "ALL_CANDIDATES_BLOCKED"
    NO_SUITABLE_LOAN = "NO_SUITABLE_LOAN"


class RecommendationSource(str, Enum):
    """WHO decided. Separate axis from RecommendationStatus."""

    ML_RANKER = "ML_RANKER"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class CandidateOutcome(str, Enum):
    """Per-candidate fate, recorded in the decision trace."""

    RECOMMENDED = "RECOMMENDED"
    ELIGIBLE_UNSUITABLE = "ELIGIBLE_UNSUITABLE"
    INELIGIBLE = "INELIGIBLE"
    INFEASIBLE = "INFEASIBLE"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    DOMINATED = "DOMINATED"


class GroundingOutcome(str, Enum):
    """
    THREE OUTCOMES, NOT A BOOLEAN (P13, CONTEXT.md 17.3).

    An unparseable token is a limitation of the GUARD, not evidence of a
    hallucination, and must not cost the user their explanation. Only a confident
    parse with no payload match rejects. Collapsing these back into a boolean is the
    change that makes the guard untrustworthy, and is forbidden.
    """

    GROUNDED = "GROUNDED"      # every extracted figure matched -> accept
    UNVERIFIED = "UNVERIFIED"  # could not be confidently parsed -> accept, flag, log
    UNGROUNDED = "UNGROUNDED"  # confident parse, no match -> reject, use the template


class ExplanationSource(str, Enum):
    """Who wrote the prose. A degraded explanation is always flagged."""

    LLM = "LLM"
    TEMPLATE = "TEMPLATE"


class XaiMethod(str, Enum):
    """
    Which mechanism produced the contributions. TreeSHAP is exact; feature importance
    is a degradation and must be flagged as one (AGENTS.md section 7).
    """

    TREE_SHAP = "TREE_SHAP"
    FEATURE_IMPORTANCE = "FEATURE_IMPORTANCE"


class GuardrailRule(str, Enum):
    """
    The four risk-appetite policy caps (P6).

    Their EVALUATION ORDER lives in config, so "the first violation" is deterministic
    and the same input always names the same rule. Each maps to exactly one
    MismatchReasonCode.
    """

    MAX_DEBT_BURDEN_RATIO = "MAX_DEBT_BURDEN_RATIO"
    MAX_LOAN_TO_INCOME_MULTIPLE = "MAX_LOAN_TO_INCOME_MULTIPLE"
    MAX_LIQUIDATION_SHARE = "MAX_LIQUIDATION_SHARE"
    VOLATILE_ASSET_LIQUIDATION = "VOLATILE_ASSET_LIQUIDATION"


class MismatchReasonCode(str, Enum):
    """
    CONTEXT.md 7.2. Every code must be traceable to a rule that actually fired or a
    score that was actually computed. No code here may be emitted speculatively.
    """

    # Eligibility (P4)
    CREDIT_SCORE_BELOW_MINIMUM = "CREDIT_SCORE_BELOW_MINIMUM"
    INCOME_BELOW_MINIMUM = "INCOME_BELOW_MINIMUM"
    AMOUNT_ABOVE_PRODUCT_MAX = "AMOUNT_ABOVE_PRODUCT_MAX"
    AMOUNT_BELOW_PRODUCT_MIN = "AMOUNT_BELOW_PRODUCT_MIN"
    TENURE_OUT_OF_RANGE = "TENURE_OUT_OF_RANGE"
    PURPOSE_NOT_SUPPORTED = "PURPOSE_NOT_SUPPORTED"

    # Feasibility (P5)
    EMI_EXCEEDS_AFFORDABILITY = "EMI_EXCEEDS_AFFORDABILITY"
    LIQUIDATION_EXCEEDS_PORTFOLIO = "LIQUIDATION_EXCEEDS_PORTFOLIO"
    REQUIRED_AMOUNT_UNREACHABLE = "REQUIRED_AMOUNT_UNREACHABLE"

    # Guardrails (P6)
    DEBT_BURDEN_CAP_EXCEEDED = "DEBT_BURDEN_CAP_EXCEEDED"
    LOAN_TO_INCOME_CAP_EXCEEDED = "LOAN_TO_INCOME_CAP_EXCEEDED"
    LIQUIDATION_SHARE_CAP_EXCEEDED = "LIQUIDATION_SHARE_CAP_EXCEEDED"
    VOLATILE_ASSET_LIQUIDATION_PROHIBITED = "VOLATILE_ASSET_LIQUIDATION_PROHIBITED"

    # Suitability (P10/P12)
    SUITABILITY_BELOW_THRESHOLD = "SUITABILITY_BELOW_THRESHOLD"
