"""
Customer-supplied inputs: profile, portfolio, requirement.

MONEY REPRESENTATION (decided at P0, applies system-wide):
    Money is `float`, in RUPEES. Never paise, never Decimal, never a mix.
    Rationale: every downstream consumer (EMI formula, NumPy feature vectors,
    XGBoost) is float-native, and rupee-level precision is what the product
    displays. Where an exact comparison is needed — deterministic validation
    re-checking EMI "to the rupee" — the comparison uses an explicit tolerance
    from config, not exact float equality.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.enums import AssetType, EmploymentType, LoanPurpose, RiskAppetite


class CustomerProfile(BaseModel):
    """The customer's financial situation as declared. No derived values here."""

    model_config = ConfigDict(extra="forbid")

    # Pseudonymous only. Never a name, phone, email or identity number:
    # traces and the personalization store are non-PII by construction.
    user_id: str | None = None

    monthly_income: float = Field(ge=0.0)
    monthly_expenses: float = Field(ge=0.0)
    existing_emi: float = Field(default=0.0, ge=0.0)
    credit_score: int = Field(ge=300, le=900)
    employment_type: EmploymentType
    employment_years: float = Field(ge=0.0)
    age: int = Field(ge=18, le=100)
    dependents: int = Field(default=0, ge=0)


class Holding(BaseModel):
    """One line item in the portfolio."""

    model_config = ConfigDict(extra="forbid")

    asset_type: AssetType
    current_value: float = Field(ge=0.0)
    invested_value: float = Field(ge=0.0)


class Portfolio(BaseModel):
    """
    The customer's investments.

    A portfolio with zero holdings is VALID and is a first-class path
    (CONTEXT.md non-negotiable 16). It is not an error and not a None.
    """

    model_config = ConfigDict(extra="forbid")

    holdings: list[Holding] = Field(default_factory=list)


class LoanRequirement(BaseModel):
    """What the customer is trying to fund."""

    model_config = ConfigDict(extra="forbid")

    purpose: LoanPurpose
    required_amount: float = Field(gt=0.0)
    preferred_tenure_months: int = Field(gt=0)
    risk_appetite: RiskAppetite

    @field_validator("required_amount")
    @classmethod
    def _finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("required_amount must be finite")
        return v


class LoanProduct(BaseModel):
    """
    One catalogue product. Loaded from CSV via the stdlib `csv` module into this
    model — never into a DataFrame (CONTEXT.md 17.2).
    """

    model_config = ConfigDict(extra="forbid")

    product_id: str
    lender: str
    product_name: str
    purposes: list[LoanPurpose] = Field(min_length=1)
    annual_rate: float = Field(ge=0.0, le=100.0)
    min_amount: float = Field(gt=0.0)
    max_amount: float = Field(gt=0.0)
    min_tenure_months: int = Field(gt=0)
    max_tenure_months: int = Field(gt=0)
    min_credit_score: int = Field(ge=300, le=900)
    min_monthly_income: float = Field(ge=0.0)
    processing_fee_pct: float = Field(ge=0.0, le=100.0)

    @field_validator("max_amount")
    @classmethod
    def _amount_range(cls, v: float, info) -> float:
        lo = info.data.get("min_amount")
        if lo is not None and v < lo:
            raise ValueError("max_amount must be >= min_amount")
        return v

    @field_validator("max_tenure_months")
    @classmethod
    def _tenure_range(cls, v: int, info) -> int:
        lo = info.data.get("min_tenure_months")
        if lo is not None and v < lo:
            raise ValueError("max_tenure_months must be >= min_tenure_months")
        return v
