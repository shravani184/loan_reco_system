"""
THE feature-assembly module. Imported by BOTH training and serving.

One feature path. Writing a second assembly path in training/ is the specific defect
this rule exists to prevent (AGENTS.md section 6 rule 4) — training imports these same
functions, so a training/serving skew is not expressible.

WHAT THIS MODULE MAY NOT DO:
  - call a model. `risk_pd` is a PARAMETER, supplied by the caller. That keeps the
    dependency acyclic: P9 trains the risk model, P10/P11 feed its PD in as a number.
  - touch the filesystem at import (AGENTS.md section 2, model loading rule).
  - return a DataFrame. Feature builders return NumPy arrays; pandas is a training-only
    dependency and never crosses into app/ (CONTEXT.md 17.2).
  - use a value the pipeline does not have at inference time. If it cannot be produced
    at serving, it is not a feature.

COLUMN ORDER IS THE CONTRACT. Both column tuples are derived at import from a single
reference call to the same function that produces the values, so a name and its value
cannot drift apart — the classic way a feature contract silently rots.

CATEGORICAL ENCODING lives here and nowhere else. Enum categoricals encode by their
position in the enum definition, which is deterministic and needs no fitting. Lender is
catalogue data rather than an enum, so its mapping is built once at training time and
SHIPPED IN THE MANIFEST — never fitted at serving. An unseen lender is a handled case
with a documented default, never an exception.
"""

import numpy as np

from app.config import settings
from app.schemas import (
    Candidate,
    CustomerProfile,
    FinancialMetrics,
    LoanProduct,
    LoanRequirement,
    PersonalizationContext,
    PortfolioMetrics,
)
from app.schemas.enums import (
    EmploymentType,
    FinancialHealth,
    FinancingStrategy,
    LoanPurpose,
    PortfolioRisk,
    RiskAppetite,
)

FEATURE_VERSION = settings.FEATURE_VERSION

# A category the encoder has never seen. Documented default, never an exception
# (CONTEXT.md 17.2). Distinct from every real index, which start at 0.
UNSEEN_CATEGORY = -1


def _enum_encoding(enum_class) -> dict[str, int]:
    """Position in the enum definition. Deterministic, so it needs no fitting."""
    return {member.value: index for index, member in enumerate(enum_class)}


ENUM_ENCODINGS: dict[str, dict[str, int]] = {
    "loan_purpose": _enum_encoding(LoanPurpose),
    "employment_type": _enum_encoding(EmploymentType),
    "financing_strategy": _enum_encoding(FinancingStrategy),
    "financial_health": _enum_encoding(FinancialHealth),
    "portfolio_risk": _enum_encoding(PortfolioRisk),
    "risk_appetite": _enum_encoding(RiskAppetite),
}

# Lender is catalogue data, not an enum, so its mapping cannot be derived from code.
# It is built once from the catalogue at training time and shipped in the manifest.
# Module-level rather than a threaded-through parameter because it is a saved mapping,
# not a fitted object — P11 installs it at model load via set_lender_encoding().
_LENDER_ENCODING: dict[str, int] = {}


def build_lender_encoding(products: list[LoanProduct]) -> dict[str, int]:
    """
    Deterministic lender mapping, built once at training time.

    Sorted by name so the same catalogue always yields the same mapping regardless of
    row order.
    """
    return {lender: index for index, lender in enumerate(sorted({p.lender for p in products}))}


def set_lender_encoding(mapping: dict[str, int]) -> None:
    """Install the saved mapping. Called at training and at model load — never fitted."""
    global _LENDER_ENCODING
    _LENDER_ENCODING = dict(mapping)


def get_lender_encoding() -> dict[str, int]:
    return dict(_LENDER_ENCODING)


def _encode(kind: str, value) -> float:
    if value is None:
        return float(UNSEEN_CATEGORY)
    raw = value.value if hasattr(value, "value") else value
    return float(ENUM_ENCODINGS[kind].get(raw, UNSEEN_CATEGORY))


def _encode_lender(lender: str | None) -> float:
    if lender is None:
        return float(UNSEEN_CATEGORY)
    return float(_LENDER_ENCODING.get(lender, UNSEEN_CATEGORY))


def _ratio(numerator: float, denominator: float) -> float:
    """
    Guarded division. A zero denominator yields 0.0 rather than NaN or an exception:
    every one of these is "share of something the customer does not have", which is
    genuinely zero, and NaN would poison the vector.
    """
    return numerator / denominator if denominator > 0.0 else 0.0


MONTHS_PER_YEAR = 12


# ==========================================================================
# RISK FEATURES — consumed by the SECONDARY risk classifier (P9)
# ==========================================================================
def _risk_feature_items(
    customer: CustomerProfile,
    financial: FinancialMetrics,
    portfolio: PortfolioMetrics,
    requirement: LoanRequirement,
) -> list[tuple[str, float]]:
    annual_income = financial.monthly_income * MONTHS_PER_YEAR
    return [
        # --- customer
        ("credit_score", float(customer.credit_score)),
        ("age", float(customer.age)),
        ("dependents", float(customer.dependents)),
        ("employment_type", _encode("employment_type", customer.employment_type)),
        ("employment_years", float(customer.employment_years)),
        # --- financial
        ("monthly_income", financial.monthly_income),
        ("monthly_expenses", financial.monthly_expenses),
        ("existing_emi", financial.existing_emi),
        ("disposable_income", financial.disposable_income),
        ("debt_burden_ratio", financial.debt_burden_ratio),
        ("expense_ratio", financial.expense_ratio),
        ("emi_affordability_ceiling", financial.emi_affordability_ceiling),
        ("income_stability_score", financial.income_stability_score),
        ("financial_health", _encode("financial_health", financial.financial_health)),
        # --- portfolio (all valid and zeroed with no holdings)
        ("has_portfolio", float(portfolio.has_portfolio)),
        ("portfolio_total_value", portfolio.total_value),
        ("portfolio_liquid_value", portfolio.liquid_value),
        ("liquidity_ratio", portfolio.liquidity_ratio),
        ("equity_exposure", portfolio.equity_exposure),
        ("debt_exposure", portfolio.debt_exposure),
        ("crypto_exposure", portfolio.crypto_exposure),
        ("concentration_risk", portfolio.concentration_risk),
        ("unrealized_gain_loss", portfolio.unrealized_gain_loss),
        ("portfolio_risk", _encode("portfolio_risk", portfolio.portfolio_risk)),
        # --- requirement
        ("loan_purpose", _encode("loan_purpose", requirement.purpose)),
        ("requested_amount", requirement.required_amount),
        ("preferred_tenure_months", float(requirement.preferred_tenure_months)),
        ("risk_appetite", _encode("risk_appetite", requirement.risk_appetite)),
        ("requested_to_annual_income", _ratio(requirement.required_amount, annual_income)),
        ("portfolio_to_requested", _ratio(portfolio.total_value, requirement.required_amount)),
    ]


# ==========================================================================
# PAIR FEATURES — one vector per (customer, candidate), consumed by the
# PRIMARY recommender (P10)
# ==========================================================================
def _pair_feature_items(
    customer: CustomerProfile,
    financial: FinancialMetrics,
    portfolio: PortfolioMetrics,
    personalization: PersonalizationContext,
    requirement: LoanRequirement,
    product: LoanProduct | None,
    candidate: Candidate,
    risk_pd: float,
) -> list[tuple[str, float]]:
    """
    THE NO-LOAN CANDIDATE has no product, lender or tenure. Its product features are
    zeroed and `is_no_loan` flags it, so the model sees "borrow nothing" rather than a
    missing product or a zero-month loan.
    """
    annual_income = financial.monthly_income * MONTHS_PER_YEAR
    is_no_loan = candidate.strategy is FinancingStrategy.LIQUIDATE_100
    tenure = float(candidate.tenure_months or 0)

    # Personalization affinities are FULLY SHAPED maps (P3), so no missing-key branch
    # is needed. Cold start yields a uniform map, which is on the same scale as an
    # observed one.
    purpose_affinity = personalization.purpose_affinity.get(requirement.purpose, 0.0)
    strategy_affinity = personalization.strategy_affinity.get(candidate.strategy, 0.0)
    preferred_band = personalization.preferred_tenure_band_months
    tenure_band_affinity = (
        1.0
        if preferred_band is not None
        and candidate.tenure_months is not None
        and preferred_band
        <= candidate.tenure_months
        < preferred_band + settings.TENURE_BAND_WIDTH_MONTHS
        else 0.0
    )

    return [
        # --- customer financial
        ("credit_score", float(customer.credit_score)),
        ("age", float(customer.age)),
        ("dependents", float(customer.dependents)),
        ("employment_type", _encode("employment_type", customer.employment_type)),
        ("employment_years", float(customer.employment_years)),
        ("monthly_income", financial.monthly_income),
        ("monthly_expenses", financial.monthly_expenses),
        ("existing_emi", financial.existing_emi),
        ("disposable_income", financial.disposable_income),
        ("debt_burden_ratio", financial.debt_burden_ratio),
        ("expense_ratio", financial.expense_ratio),
        ("emi_affordability_ceiling", financial.emi_affordability_ceiling),
        ("income_stability_score", financial.income_stability_score),
        ("financial_health", _encode("financial_health", financial.financial_health)),
        # --- portfolio
        ("has_portfolio", float(portfolio.has_portfolio)),
        ("portfolio_total_value", portfolio.total_value),
        ("portfolio_liquid_value", portfolio.liquid_value),
        ("liquidity_ratio", portfolio.liquidity_ratio),
        ("equity_exposure", portfolio.equity_exposure),
        ("debt_exposure", portfolio.debt_exposure),
        ("crypto_exposure", portfolio.crypto_exposure),
        ("concentration_risk", portfolio.concentration_risk),
        ("unrealized_gain_loss", portfolio.unrealized_gain_loss),
        ("portfolio_risk", _encode("portfolio_risk", portfolio.portfolio_risk)),
        # --- personalization (neutral, never absent, for cold start)
        ("is_cold_start", float(personalization.is_cold_start)),
        ("purpose_affinity", purpose_affinity),
        ("strategy_affinity", strategy_affinity),
        ("tenure_band_affinity", tenure_band_affinity),
        ("session_count", float(personalization.session_count)),
        ("engagement_score", personalization.engagement_score),
        ("prior_declines", float(personalization.prior_declines)),
        # --- requirement
        ("loan_purpose", _encode("loan_purpose", requirement.purpose)),
        ("requested_amount", requirement.required_amount),
        ("preferred_tenure_months", float(requirement.preferred_tenure_months)),
        ("risk_appetite", _encode("risk_appetite", requirement.risk_appetite)),
        # --- product (zeroed for the no-loan candidate)
        ("is_no_loan", float(is_no_loan)),
        ("product_lender", _encode_lender(candidate.lender)),
        (
            "product_primary_purpose",
            _encode("loan_purpose", product.purposes[0]) if product else float(UNSEEN_CATEGORY),
        ),
        ("product_annual_rate", product.annual_rate if product else 0.0),
        ("product_min_amount", product.min_amount if product else 0.0),
        ("product_max_amount", product.max_amount if product else 0.0),
        ("product_min_tenure_months", float(product.min_tenure_months) if product else 0.0),
        ("product_max_tenure_months", float(product.max_tenure_months) if product else 0.0),
        ("product_min_credit_score", float(product.min_credit_score) if product else 0.0),
        ("product_min_monthly_income", product.min_monthly_income if product else 0.0),
        ("product_processing_fee_pct", product.processing_fee_pct if product else 0.0),
        # --- derived candidate
        ("financing_strategy", _encode("financing_strategy", candidate.strategy)),
        ("candidate_tenure_months", tenure),
        ("loan_amount", candidate.loan_amount),
        ("emi", candidate.emi),
        ("loan_to_annual_income", _ratio(candidate.loan_amount, annual_income)),
        ("emi_to_income", _ratio(candidate.emi, financial.monthly_income)),
        (
            "emi_to_disposable_income",
            _ratio(candidate.emi, max(financial.disposable_income, 0.0)),
        ),
        ("total_interest", candidate.total_interest),
        ("total_repayment", candidate.total_repayment),
        ("interest_to_loan_amount", _ratio(candidate.total_interest, candidate.loan_amount)),
        ("post_loan_debt_burden", candidate.resulting_debt_burden_ratio),
        ("affordability_headroom", candidate.affordability_headroom),
        (
            "affordability_headroom_ratio",
            _ratio(candidate.affordability_headroom, financial.emi_affordability_ceiling),
        ),
        ("liquidation_amount", candidate.liquidation_amount),
        (
            "liquidation_to_portfolio",
            _ratio(candidate.liquidation_amount, portfolio.total_value),
        ),
        ("volatile_liquidation_amount", candidate.volatile_liquidation_amount),
        (
            "volatile_liquidation_to_portfolio",
            _ratio(candidate.volatile_liquidation_amount, portfolio.total_value),
        ),
        ("remaining_portfolio_value", candidate.remaining_portfolio_value),
        ("post_strategy_liquidity_ratio", candidate.resulting_liquidity_ratio),
        (
            "tenure_delta_vs_preferred",
            tenure - float(requirement.preferred_tenure_months) if not is_no_loan else 0.0,
        ),
        (
            "amount_delta_vs_requested",
            (candidate.loan_amount + candidate.liquidation_amount)
            - candidate.required_amount,
        ),
        (
            "funding_coverage",
            _ratio(
                candidate.loan_amount + candidate.liquidation_amount,
                candidate.required_amount,
            ),
        ),
        # --- risk signal (a PARAMETER; this module never calls a model)
        ("risk_pd", float(risk_pd)),
    ]


# --------------------------------------------------------------------------
# Column order, derived from the builders themselves so a name and its value
# can never drift apart.
# --------------------------------------------------------------------------
def _reference_inputs():
    from app.core.financial import analyze_financials
    from app.core.portfolio import analyze_portfolio
    from app.schemas import Portfolio

    customer = CustomerProfile(
        monthly_income=1.0,
        monthly_expenses=0.0,
        existing_emi=0.0,
        credit_score=700,
        employment_type=EmploymentType.SALARIED,
        employment_years=1.0,
        age=30,
    )
    requirement = LoanRequirement(
        purpose=LoanPurpose.PERSONAL,
        required_amount=1.0,
        preferred_tenure_months=12,
        risk_appetite=RiskAppetite.MODERATE,
    )
    candidate = Candidate(
        candidate_id="reference",
        product_id="REF",
        lender="REF",
        tenure_months=12,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=1.0,
        loan_amount=1.0,
        emi=1.0,
        total_interest=0.0,
        total_repayment=1.0,
        liquidation_amount=0.0,
        volatile_liquidation_amount=0.0,
        remaining_portfolio_value=0.0,
        resulting_liquidity_ratio=0.0,
        resulting_debt_burden_ratio=0.0,
        affordability_headroom=0.0,
    )
    product = LoanProduct(
        product_id="REF",
        lender="REF",
        product_name="Reference",
        purposes=[LoanPurpose.PERSONAL],
        annual_rate=10.0,
        min_amount=1.0,
        max_amount=2.0,
        min_tenure_months=12,
        max_tenure_months=24,
        min_credit_score=300,
        min_monthly_income=0.0,
        processing_fee_pct=0.0,
    )
    return (
        customer,
        analyze_financials(customer),
        analyze_portfolio(Portfolio(holdings=[])),
        PersonalizationContext(is_cold_start=True),
        requirement,
        product,
        candidate,
    )


def _derive_columns() -> tuple[tuple[str, ...], tuple[str, ...]]:
    customer, financial, portfolio, personalization, requirement, product, candidate = (
        _reference_inputs()
    )
    risk = _risk_feature_items(customer, financial, portfolio, requirement)
    pair = _pair_feature_items(
        customer,
        financial,
        portfolio,
        personalization,
        requirement,
        product,
        candidate,
        0.0,
    )
    return tuple(name for name, _ in risk), tuple(name for name, _ in pair)


RISK_FEATURE_COLUMNS, PAIR_FEATURE_COLUMNS = _derive_columns()


# --------------------------------------------------------------------------
# public builders
# --------------------------------------------------------------------------
def build_risk_features(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    requirement: LoanRequirement,
) -> np.ndarray:
    """One row for the secondary risk classifier. Shape (len(RISK_FEATURE_COLUMNS),)."""
    items = _risk_feature_items(
        customer, financial_metrics, portfolio_metrics, requirement
    )
    return np.asarray([value for _, value in items], dtype=np.float64)


def build_pair_features(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    personalization_context: PersonalizationContext,
    requirement: LoanRequirement,
    product: LoanProduct | None,
    candidate: Candidate,
    risk_pd: float,
) -> np.ndarray:
    """One (customer, candidate) row. Shape (len(PAIR_FEATURE_COLUMNS),)."""
    items = _pair_feature_items(
        customer,
        financial_metrics,
        portfolio_metrics,
        personalization_context,
        requirement,
        product,
        candidate,
        risk_pd,
    )
    return np.asarray([value for _, value in items], dtype=np.float64)


def build_pair_feature_matrix(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    personalization_context: PersonalizationContext,
    requirement: LoanRequirement,
    candidates: list[Candidate],
    products_by_id: dict[str, LoanProduct],
    risk_pd: float,
) -> np.ndarray:
    """
    A whole candidate list in one call, so serving scores every candidate with a single
    prediction rather than looping. Shape (len(candidates), len(PAIR_FEATURE_COLUMNS)).

    An empty candidate list returns a correctly-shaped empty matrix, not an error —
    the recommender handed an empty list returns an empty list (AGENTS.md section 6).
    """
    if not candidates:
        return np.empty((0, len(PAIR_FEATURE_COLUMNS)), dtype=np.float64)
    return np.vstack(
        [
            build_pair_features(
                customer,
                financial_metrics,
                portfolio_metrics,
                personalization_context,
                requirement,
                products_by_id.get(candidate.product_id) if candidate.product_id else None,
                candidate,
                risk_pd,
            )
            for candidate in candidates
        ]
    )


# --------------------------------------------------------------------------
# the manifest — the feature contract, asserted at model load
# --------------------------------------------------------------------------
def feature_manifest() -> dict:
    """
    Emitted by a training script and saved beside its model. Carries the encoder
    mappings, so serving never fits an encoder.
    """
    return {
        "feature_version": FEATURE_VERSION,
        "risk_feature_columns": list(RISK_FEATURE_COLUMNS),
        "pair_feature_columns": list(PAIR_FEATURE_COLUMNS),
        "enum_encodings": {key: dict(value) for key, value in ENUM_ENCODINGS.items()},
        "lender_encoding": get_lender_encoding(),
        "unseen_category": UNSEEN_CATEGORY,
    }


class FeatureManifestMismatch(RuntimeError):
    """A model artifact disagrees with this module about the feature contract."""


def assert_manifest_matches(manifest: dict) -> None:
    """
    A mismatch is a STARTUP FAILURE with a clear message — never a warning, never a
    silent reorder, never a truncation to the shorter list (AGENTS.md section 2).

    Pure validation. It installs nothing; P11 calls set_lender_encoding() explicitly
    with manifest["lender_encoding"] so the installation is visible at the call site.
    """
    expected_version = manifest.get("feature_version")
    if expected_version != FEATURE_VERSION:
        raise FeatureManifestMismatch(
            f"FEATURE_VERSION mismatch: artifact was built with "
            f"{expected_version!r}, this code is {FEATURE_VERSION!r}. Retrain, or "
            f"deploy the matching code. Do not proceed."
        )

    for key, expected in (
        ("risk_feature_columns", list(RISK_FEATURE_COLUMNS)),
        ("pair_feature_columns", list(PAIR_FEATURE_COLUMNS)),
    ):
        found = list(manifest.get(key, []))
        if found != expected:
            missing = [c for c in expected if c not in found]
            extra = [c for c in found if c not in expected]
            detail = (
                f"missing={missing} unexpected={extra}"
                if (missing or extra)
                else "same columns in a DIFFERENT ORDER"
            )
            raise FeatureManifestMismatch(
                f"{key} mismatch between the model artifact and app/ml/features.py: "
                f"{detail}. Column order is the contract; a reorder silently feeds "
                f"every value to the wrong feature."
            )

    found_enums = manifest.get("enum_encodings", {})
    if found_enums != {key: dict(value) for key, value in ENUM_ENCODINGS.items()}:
        raise FeatureManifestMismatch(
            "enum encoding mismatch between the model artifact and "
            "app/ml/features.py: a category has been added, removed or reordered."
        )
