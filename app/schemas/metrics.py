"""
Derived metric blocks. Each is produced by exactly one module and consumed
downstream; no consumer recomputes a field it finds here.

Producers: FinancialMetrics -> app/core/financial.py (P1)
           PortfolioMetrics -> app/core/portfolio.py (P2)
           PersonalizationContext -> app/personalization/context.py (P3)
           RiskPrediction -> app/ml/risk.py (P9/P11)
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    AssetType,
    FinancialHealth,
    FinancingStrategy,
    LoanPurpose,
    PortfolioRisk,
    RiskClass,
)


class FinancialMetrics(BaseModel):
    """Produced by Financial Intelligence (P1)."""

    model_config = ConfigDict(extra="forbid")

    monthly_income: float = Field(ge=0.0)
    monthly_expenses: float = Field(ge=0.0)
    existing_emi: float = Field(ge=0.0)
    disposable_income: float
    debt_burden_ratio: float = Field(ge=0.0)
    expense_ratio: float = Field(ge=0.0)
    emi_affordability_ceiling: float = Field(ge=0.0)
    income_stability_score: float = Field(ge=0.0, le=1.0)
    financial_health: FinancialHealth


class PortfolioMetrics(BaseModel):
    """
    Produced by Portfolio Intelligence (P2).

    Every field is valid and zeroed for a customer with no holdings; that case is
    signalled by `has_portfolio = False`, never by a None or a missing block.
    """

    model_config = ConfigDict(extra="forbid")

    has_portfolio: bool
    total_value: float = Field(ge=0.0)

    # Share of total value per asset type. EVERY AssetType is always present, zeroed
    # when absent, so the feature path never has to test for a missing key.
    allocation: dict[AssetType, float] = Field(default_factory=dict)

    # Gross value of the holdings classified liquid. Liquidation HAIRCUTS are NOT
    # applied here — P5 applies them when it computes an actual liquidation, and
    # applying them in both places would double-count them.
    liquid_value: float = Field(ge=0.0)
    liquidity_ratio: float = Field(ge=0.0, le=1.0)
    equity_exposure: float = Field(ge=0.0, le=1.0)
    debt_exposure: float = Field(ge=0.0, le=1.0)
    crypto_exposure: float = Field(ge=0.0, le=1.0)
    concentration_risk: float = Field(ge=0.0, le=1.0)
    unrealized_gain_loss: float
    portfolio_risk: PortfolioRisk


class PersonalizationContext(BaseModel):
    """
    Produced by the personalization layer (P3). A FEATURE SOURCE ONLY — it scores
    nothing and decides nothing.

    Cold start is first-class: an unknown or absent user_id yields a valid neutral
    block with `is_cold_start = True`, and the pipeline runs identically.
    """

    model_config = ConfigDict(extra="forbid")

    is_cold_start: bool
    session_count: int = Field(default=0, ge=0)
    prior_declines: int = Field(default=0, ge=0)
    engagement_score: float = Field(default=0.0, ge=0.0, le=1.0)
    preferred_tenure_band_months: int | None = None
    purpose_affinity: dict[LoanPurpose, float] = Field(default_factory=dict)
    strategy_affinity: dict[FinancingStrategy, float] = Field(default_factory=dict)


class RiskPrediction(BaseModel):
    """
    Produced by the SECONDARY risk classifier (P9/P11).

    This is a feature and a user-facing disclosure. It never gates, vetoes or
    selects (CONTEXT.md non-negotiable 3). When the model cannot load, `pd` is the
    training-set median and `imputed` is True — the pipeline continues.
    """

    model_config = ConfigDict(extra="forbid")

    risk_class: RiskClass
    probability_of_default: float = Field(ge=0.0, le=1.0)
    model_version: str
    imputed: bool = False
