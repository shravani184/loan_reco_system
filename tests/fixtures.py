"""
Shared in-memory test inputs for EVERY phase.

Tests never read from data/ and never require a trained model (AGENTS.md section 2,
test data rule). Any phase needing a loan catalogue imports MOCK_CATALOGUE from here
rather than generating a CSV early.

Everything is a factory function, so a test mutating an object cannot leak into
another test.
"""

from app.personalization.context import neutral_personalization_context
from app.schemas import (
    CustomerProfile,
    Holding,
    LoanProduct,
    LoanRequirement,
    PersonalizationContext,
    Portfolio,
)
from app.schemas.enums import (
    AssetType,
    EmploymentType,
    LoanPurpose,
    RiskAppetite,
)


def mock_catalogue() -> list[LoanProduct]:
    """
    Six synthetic products spanning purposes, lenders and credit tiers.

    SYNTHETIC DATA. Not a real lender catalogue and never presented as one.
    """
    return [
        LoanProduct(
            product_id="HL-001",
            lender="Meridian Bank",
            product_name="Meridian Home Advantage",
            purposes=[LoanPurpose.HOME],
            annual_rate=8.5,
            min_amount=500_000.0,
            max_amount=10_000_000.0,
            min_tenure_months=60,
            max_tenure_months=240,
            min_credit_score=720,
            min_monthly_income=60_000.0,
            processing_fee_pct=0.5,
        ),
        LoanProduct(
            product_id="HL-002",
            lender="Kestrel Housing Finance",
            product_name="Kestrel FlexiHome",
            purposes=[LoanPurpose.HOME],
            annual_rate=9.75,
            min_amount=300_000.0,
            max_amount=5_000_000.0,
            min_tenure_months=36,
            max_tenure_months=180,
            min_credit_score=650,
            min_monthly_income=35_000.0,
            processing_fee_pct=1.0,
        ),
        LoanProduct(
            product_id="VL-001",
            lender="Meridian Bank",
            product_name="Meridian Auto Loan",
            purposes=[LoanPurpose.VEHICLE],
            annual_rate=10.25,
            min_amount=100_000.0,
            max_amount=2_500_000.0,
            min_tenure_months=12,
            max_tenure_months=84,
            min_credit_score=700,
            min_monthly_income=40_000.0,
            processing_fee_pct=0.75,
        ),
        LoanProduct(
            product_id="PL-001",
            lender="Anvil Credit",
            product_name="Anvil Personal Line",
            purposes=[LoanPurpose.PERSONAL, LoanPurpose.MEDICAL],
            annual_rate=14.0,
            min_amount=50_000.0,
            max_amount=1_500_000.0,
            min_tenure_months=12,
            max_tenure_months=60,
            min_credit_score=680,
            min_monthly_income=30_000.0,
            processing_fee_pct=2.0,
        ),
        LoanProduct(
            product_id="EL-001",
            lender="Kestrel Housing Finance",
            product_name="Kestrel Scholar",
            purposes=[LoanPurpose.EDUCATION],
            annual_rate=9.0,
            min_amount=200_000.0,
            max_amount=4_000_000.0,
            min_tenure_months=24,
            max_tenure_months=144,
            min_credit_score=640,
            min_monthly_income=25_000.0,
            processing_fee_pct=0.25,
        ),
        LoanProduct(
            product_id="BL-001",
            lender="Anvil Credit",
            product_name="Anvil Business Growth",
            purposes=[LoanPurpose.BUSINESS],
            annual_rate=13.5,
            min_amount=500_000.0,
            max_amount=7_500_000.0,
            min_tenure_months=24,
            max_tenure_months=120,
            min_credit_score=730,
            min_monthly_income=80_000.0,
            processing_fee_pct=1.5,
        ),
    ]


def standard_customer() -> CustomerProfile:
    """A salaried customer comfortably inside the middle of the catalogue."""
    return CustomerProfile(
        user_id="cust-0001",
        monthly_income=120_000.0,
        monthly_expenses=55_000.0,
        existing_emi=12_000.0,
        credit_score=760,
        employment_type=EmploymentType.SALARIED,
        employment_years=6.5,
        age=34,
        dependents=2,
    )


def no_match_customer() -> CustomerProfile:
    """
    Deliberately matches NO product: below every product's minimum credit score and
    minimum income. Drives the NO_ELIGIBLE_PRODUCTS path.
    """
    return CustomerProfile(
        user_id="cust-9999",
        monthly_income=14_000.0,
        monthly_expenses=13_000.0,
        existing_emi=1_500.0,
        credit_score=545,
        employment_type=EmploymentType.CONTRACT,
        employment_years=0.5,
        age=23,
        dependents=1,
    )


def mixed_portfolio() -> Portfolio:
    """Liquid and volatile holdings, with both gains and losses."""
    return Portfolio(
        holdings=[
            Holding(asset_type=AssetType.CASH, current_value=150_000.0, invested_value=150_000.0),
            Holding(asset_type=AssetType.FIXED_DEPOSIT, current_value=400_000.0, invested_value=370_000.0),
            Holding(asset_type=AssetType.MUTUAL_FUNDS, current_value=650_000.0, invested_value=500_000.0),
            Holding(asset_type=AssetType.STOCKS, current_value=800_000.0, invested_value=900_000.0),
            Holding(asset_type=AssetType.BONDS, current_value=200_000.0, invested_value=195_000.0),
            Holding(asset_type=AssetType.CRYPTO, current_value=100_000.0, invested_value=140_000.0),
        ]
    )


def empty_portfolio() -> Portfolio:
    """
    A customer with no investments. This is a FIRST-CLASS path, not an error
    (CONTEXT.md non-negotiable 16).
    """
    return Portfolio(holdings=[])


def standard_requirement() -> LoanRequirement:
    return LoanRequirement(
        purpose=LoanPurpose.HOME,
        required_amount=2_000_000.0,
        preferred_tenure_months=120,
        risk_appetite=RiskAppetite.MODERATE,
    )


def neutral_personalization() -> PersonalizationContext:
    """
    The cold-start block: a valid neutral context for an unknown or absent user_id.
    The pipeline runs identically with this as with a populated history.

    Delegates to the real constructor rather than rebuilding the block, so this
    fixture cannot drift from what the pipeline actually produces.
    """
    return neutral_personalization_context()
