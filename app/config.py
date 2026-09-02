"""
The single configuration module. One load, at import, and nothing else reads the
environment (AGENTS.md section 4).

Two kinds of config, split by type because .env parses nested structures badly:

  FLAT SCALARS   paths, keys, URLs, versions, flags -> read from environment / .env
  COMPLEX        caps, grids, weights, maps         -> typed defaults IN THIS CLASS

Both halves are equally config. Business logic may never hardcode either. If you
catch yourself typing a magic number in app/, it belongs here.

Complex defaults may optionally be overridden by a JSON file whose path comes from
COMPLEX_CONFIG_PATH, but the class defaults must work with no file present.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.enums import (
    AssetType,
    EmploymentType,
    FeedbackEventType,
    FinancialHealth,
    FinancingStrategy,
    GuardrailRule,
    PortfolioRisk,
    RiskAppetite,
    RiskClass,
)


class GuardrailCaps(BaseModel):
    """
    Policy caps for one risk appetite. Applied AFTER the recommender, pass/fail only.

    These are never widened to make a demo produce a recommendation
    (AGENTS.md section 10).
    """

    max_debt_burden_ratio: float
    max_liquidation_share: float
    max_loan_to_income_multiple: float
    allow_volatile_liquidation: bool


class DiagnosticWeights(BaseModel):
    """
    Weights of the ADVISORY diagnostic utility score (CONTEXT.md section 4).

    This score is the deterministic fallback ranking and an audit figure. It may
    never reorder an ML recommendation during normal operation.
    """

    w1_affordability_headroom: float
    w2_inverse_risk: float
    w3_cost_efficiency: float
    w4_portfolio_impact_penalty: float
    w5_soft_constraint_penalty: float


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------- flat scalars
    # Version strings stamped into every decision trace.
    CONFIG_VERSION: str = "2.0.0"
    FEATURE_VERSION: str = "2.0.0"
    PROMPT_VERSION: str = "2.0.0"
    LABELING_POLICY_VERSION: str = "2.0.0"
    # Both model versions appear in every decision trace (AGENTS.md section 4).
    RISK_MODEL_VERSION: str = "risk-2.0.0"
    RECOMMENDER_MODEL_VERSION: str = "recommender-2.0.0"

    RISK_MODEL_PATH: str = "models/risk_model.json"
    RECOMMENDER_MODEL_PATH: str = "models/loan_recommender.json"
    # Named to match the artifacts P10 actually writes. The calibrator is a TRANSFORM
    # belonging to the recommender bundle, not a standalone model, which is why both
    # files carry the recommender's name.
    CALIBRATION_KNOTS_PATH: str = "models/loan_recommender_calibration.json"
    ENCODER_MAPPING_PATH: str = "models/loan_recommender_encoders.json"
    LOAN_CATALOGUE_PATH: str = "data/loan_products.csv"

    LLM_API_KEY: str = ""
    LLM_API_ENDPOINT: str = ""
    LLM_MODEL: str = ""

    PERSONALIZATION_DB_URL: str = "sqlite:///data/personalization.db"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"

    LOG_LEVEL: str = "INFO"
    ENABLE_XAI_ENDPOINT: bool = True

    # Optional JSON override for the complex block below.
    COMPLEX_CONFIG_PATH: str = ""

    # ------------------------------------------------------------ complex defaults
    # The sole definition of "suitable enough to recommend". Compared ONLY against
    # the calibrated suitability, never a raw ranker margin (CONTEXT.md 6.4).
    SUITABILITY_ACCEPTANCE_THRESHOLD: float = 0.55
    MAX_ALTERNATIVES_RETURNED: int = 3

    # Guardrail caps per declared risk appetite (P6).
    GUARDRAIL_CAPS: dict[RiskAppetite, GuardrailCaps] = Field(
        default_factory=lambda: {
            RiskAppetite.CONSERVATIVE: GuardrailCaps(
                max_debt_burden_ratio=0.35,
                max_liquidation_share=0.25,
                max_loan_to_income_multiple=8.0,
                allow_volatile_liquidation=False,
            ),
            RiskAppetite.MODERATE: GuardrailCaps(
                max_debt_burden_ratio=0.45,
                max_liquidation_share=0.50,
                max_loan_to_income_multiple=12.0,
                allow_volatile_liquidation=True,
            ),
            RiskAppetite.AGGRESSIVE: GuardrailCaps(
                max_debt_burden_ratio=0.55,
                max_liquidation_share=0.75,
                max_loan_to_income_multiple=18.0,
                allow_volatile_liquidation=True,
            ),
        }
    )

    # Order in which guardrail caps are evaluated (P6). The FIRST violation is what
    # the trace and the UI name, so this order is what makes that deterministic.
    # Affordability policy first, then leverage, then portfolio impact, then the
    # categorical prohibition — most fundamental to most specific.
    GUARDRAIL_RULE_ORDER: list[GuardrailRule] = Field(
        default_factory=lambda: [
            GuardrailRule.MAX_DEBT_BURDEN_RATIO,
            GuardrailRule.MAX_LOAN_TO_INCOME_MULTIPLE,
            GuardrailRule.MAX_LIQUIDATION_SHARE,
            GuardrailRule.VOLATILE_ASSET_LIQUIDATION,
        ]
    )

    # --- Financial Intelligence (P1) ---
    # Income-relative ratios are undefined when income is zero, but they become ML
    # features and so need a finite stand-in. This is that stand-in, deliberately
    # far outside the range a real ratio occupies so it is recognisable in a trace.
    UNDEFINED_RATIO_VALUE: float = 99.0

    # income_stability_score = base(employment type) * (1 - tenure weight)
    #                        + capped tenure fraction * tenure weight
    EMPLOYMENT_STABILITY_BASE: dict[EmploymentType, float] = Field(
        default_factory=lambda: {
            EmploymentType.SALARIED: 0.70,
            EmploymentType.SELF_EMPLOYED: 0.45,
            EmploymentType.CONTRACT: 0.35,
            EmploymentType.RETIRED: 0.50,
        }
    )
    STABILITY_FULL_TENURE_YEARS: float = 10.0
    STABILITY_TENURE_WEIGHT: float = 0.40

    # Minimum savings rate (disposable income / income) for each health band. POOR is
    # the floor and deliberately has no entry. The band ladder is derived from these
    # values in descending order, so this dict is the single source of both the
    # thresholds and the ordering.
    FINANCIAL_HEALTH_MIN_SAVINGS_RATE: dict[FinancialHealth, float] = Field(
        default_factory=lambda: {
            FinancialHealth.EXCELLENT: 0.40,
            FinancialHealth.GOOD: 0.25,
            FinancialHealth.FAIR: 0.10,
        }
    )
    # A customer above this existing debt burden is demoted exactly one band.
    FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD: float = 0.40

    # --- Portfolio Intelligence (P2) ---
    # Exposure classification. CASH is deliberately in neither list: it is neither an
    # equity nor a debt instrument, so the three exposures do not sum to 1.0. Each is
    # an independent share of the portfolio, not a partition of it.
    EQUITY_ASSET_TYPES: list[AssetType] = Field(
        default_factory=lambda: [AssetType.STOCKS, AssetType.MUTUAL_FUNDS]
    )
    DEBT_ASSET_TYPES: list[AssetType] = Field(
        default_factory=lambda: [AssetType.FIXED_DEPOSIT, AssetType.BONDS]
    )

    # Per-asset-type risk contribution, [0,1]. The portfolio risk score is the
    # value-weighted mean of these.
    ASSET_RISK_WEIGHT: dict[AssetType, float] = Field(
        default_factory=lambda: {
            AssetType.CASH: 0.00,
            AssetType.FIXED_DEPOSIT: 0.05,
            AssetType.BONDS: 0.15,
            AssetType.MUTUAL_FUNDS: 0.50,
            AssetType.STOCKS: 0.75,
            AssetType.CRYPTO: 1.00,
        }
    )
    # Minimum risk score for each band. CONSERVATIVE is the floor and deliberately
    # has no entry; the ladder is derived from these values in descending order.
    PORTFOLIO_RISK_MIN_SCORE: dict[PortfolioRisk, float] = Field(
        default_factory=lambda: {
            PortfolioRisk.AGGRESSIVE: 0.70,
            PortfolioRisk.GROWTH: 0.45,
            PortfolioRisk.BALANCED: 0.20,
        }
    )

    # --- Risk model (P9/P11) ---
    # Minimum predicted default probability for each risk class. LOW is the floor and
    # deliberately has no entry; the ladder is derived from these values in descending
    # order, the same pattern as the financial-health and portfolio-risk bands.
    #
    # THE RISK CLASS IS A DISCLOSURE, NOT A DECISION. It never gates or vetoes a
    # candidate (CONTEXT.md non-negotiable 3).
    RISK_CLASS_MIN_PD: dict[RiskClass, float] = Field(
        default_factory=lambda: {
            RiskClass.HIGH: 0.35,
            RiskClass.MEDIUM: 0.15,
        }
    )

    # --- Personalization (P3) ---
    # An event's weight halves every this many days. Nothing here decides anything;
    # these shape FEATURES handed to the recommender.
    PERSONALIZATION_DECAY_HALF_LIFE_DAYS: float = 90.0
    PERSONALIZATION_EVENT_WEIGHT: dict[FeedbackEventType, float] = Field(
        default_factory=lambda: {
            FeedbackEventType.VIEWED: 0.25,
            FeedbackEventType.ACCEPTED: 1.00,
            FeedbackEventType.DECLINED: 0.50,
        }
    )
    # Engagement saturates: score = weighted / (weighted + this). Keeps the value in
    # [0,1) without a clamp, and makes the first few interactions matter most.
    ENGAGEMENT_SATURATION: float = 5.0
    # Accepted tenures are grouped into bands this many months wide.
    TENURE_BAND_WIDTH_MONTHS: int = 12

    # Eligibility thresholds that are NOT product attributes (P4). Per-product
    # minimums come from the catalogue, not from here.
    MAX_EMI_SHARE_OF_DISPOSABLE_INCOME: float = 0.50
    # NOTE ON AGE (resolved at P12 after four deferrals). MIN_APPLICANT_AGE and
    # MAX_AGE_AT_LOAN_MATURITY previously sat here and were never read by any module.
    # Age is not an eligibility rule in this architecture: CONTEXT.md section 4 lists
    # exactly five hard constraints and age is not among them, section 7.2 defines no
    # reason code for it, and the P4/P5/P6 prompts each name their rules exhaustively
    # without it. Config keys that imply a rule nobody enforces are worse than absent
    # ones — a reader assumes age is checked somewhere. They are therefore removed.
    #
    # To ADD an age rule properly: a new MismatchReasonCode, a new rule in either
    # app/core/eligibility.py (a hard gate) or app/core/candidates.py (a feasibility
    # limit on long tenures for older applicants), and an update to CONTEXT.md
    # section 4 and 7.2. That is a named schema change, not a config default.

    # Candidate enumeration grid (P5). Amount steps are fractions of the requested
    # amount; tenures are absolute months.
    CANDIDATE_AMOUNT_STEPS: list[float] = Field(
        default_factory=lambda: [0.6, 0.8, 1.0]
    )
    CANDIDATE_TENURE_OPTIONS_MONTHS: list[int] = Field(
        default_factory=lambda: [12, 24, 36, 48, 60, 84, 120]
    )
    # Borrow share per strategy; the remainder is funded by liquidation.
    CANDIDATE_STRATEGY_BORROW_SHARE: dict[FinancingStrategy, float] = Field(
        default_factory=lambda: {
            FinancingStrategy.BORROW_100: 1.0,
            FinancingStrategy.BORROW_80_LIQUIDATE_20: 0.8,
            FinancingStrategy.BORROW_60_LIQUIDATE_40: 0.6,
            FinancingStrategy.BORROW_40_LIQUIDATE_60: 0.4,
            FinancingStrategy.BORROW_20_LIQUIDATE_80: 0.2,
            FinancingStrategy.LIQUIDATE_100: 0.0,
        }
    )
    MAX_CANDIDATES_PER_PRODUCT: int = 60
    MAX_CANDIDATES_TOTAL: int = 500

    # Which asset types count as liquid, and the haircut applied when liquidating.
    LIQUID_ASSET_TYPES: list[AssetType] = Field(
        default_factory=lambda: [
            AssetType.CASH,
            AssetType.FIXED_DEPOSIT,
            AssetType.MUTUAL_FUNDS,
        ]
    )
    VOLATILE_ASSET_TYPES: list[AssetType] = Field(
        default_factory=lambda: [AssetType.STOCKS, AssetType.CRYPTO]
    )
    ASSET_LIQUIDATION_HAIRCUT: dict[AssetType, float] = Field(
        default_factory=lambda: {
            AssetType.CASH: 0.00,
            AssetType.FIXED_DEPOSIT: 0.01,
            AssetType.MUTUAL_FUNDS: 0.02,
            AssetType.BONDS: 0.03,
            AssetType.STOCKS: 0.05,
            AssetType.CRYPTO: 0.10,
        }
    )

    DIAGNOSTIC_WEIGHTS: DiagnosticWeights = Field(
        default_factory=lambda: DiagnosticWeights(
            w1_affordability_headroom=0.30,
            w2_inverse_risk=0.25,
            w3_cost_efficiency=0.25,
            w4_portfolio_impact_penalty=0.15,
            w5_soft_constraint_penalty=0.05,
        )
    )

    # Deterministic validation recomputes EMI and asserts it matches to the rupee.
    # Money is float, so the comparison uses this tolerance, not exact equality.
    EMI_VALIDATION_TOLERANCE_RUPEES: float = 1.0

    # Serving memory ceiling. Phase R measured 186.3 MB for the serving dependency
    # set; 290 is that plus ~60% headroom. Verified again at P11, P13 and P17.
    MEMORY_CEILING_MB: int = 290

    # --- Numeric-grounding guard (P13) ---
    # EVERY VALUE HERE WAS VALIDATED IN PHASE R against the 78-case corpus now at
    # tests/data/grounding_corpus.jsonl. They are not free parameters: the corpus
    # scores 100% on UNGROUNDED with zero false rejections at these settings, and a
    # test fails if that stops being true. WIDENING A TOLERANCE TO MAKE A DEMO PASS IS
    # FORBIDDEN (AGENTS.md section 5) — if a false positive appears, the normalizer is
    # the bug.
    #
    # A bare number at least this large is financial even with no cue word.
    GROUNDING_MAGNITUDE_FLOOR: float = 1000.0
    # A CUED number at least this large is a confident financial claim even without a
    # unit. Below it, an unmatched cued integer degrades to UNVERIFIED rather than
    # being called invented — that band is where false positives live.
    GROUNDING_SMALL_CUED_FLOOR: float = 100.0
    # Rounding allowance when matching against the accepted set.
    GROUNDING_RELATIVE_TOLERANCE: float = 0.01
    GROUNDING_ABSOLUTE_TOLERANCE: float = 1.0
    # The +/-1 rupee allowance applies only to figures this large. Applying it to small
    # derived numbers made "5 years" match a 4-year tenure and "9%" match an 8% rate.
    GROUNDING_ABSOLUTE_TOLERANCE_MIN_MAGNITUDE: float = 100.0
    GROUNDING_CUE_WORDS: list[str] = Field(
        default_factory=lambda: [
            "emi", "interest", "rate", "tenure", "principal", "amount", "loan",
            "repayment", "instalment", "installment", "months", "month", "years",
            "year", "yrs", "yr", "score", "lakh", "lakhs", "crore", "crores", "rs",
            "inr", "percent", "pa", "suitability", "total", "cost", "portfolio",
            "liquidate", "liquidated", "fee",
        ]
    )


def _apply_complex_overrides(s: Settings) -> Settings:
    """Optional JSON override of the complex block. Absent file is the normal case."""
    if not s.COMPLEX_CONFIG_PATH:
        return s
    path = Path(s.COMPLEX_CONFIG_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"COMPLEX_CONFIG_PATH points at no file: {path}")
    overrides = json.loads(path.read_text(encoding="utf-8"))
    return Settings(**{**s.model_dump(), **overrides})


settings = _apply_complex_overrides(Settings())
