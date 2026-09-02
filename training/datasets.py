"""
Load the synthetic CSVs into the real Pydantic schemas.

OFFLINE ONLY. training/ may import app/; the reverse is forbidden.

Every file written by generate_data.py starts with a '#' provenance comment, so every
reader here skips comment lines. Reading with the stdlib csv module rather than pandas
keeps this file usable from anywhere without pulling a heavy import into a test run.
"""

import csv
from pathlib import Path

from app.schemas import CustomerProfile, Holding, LoanProduct, LoanRequirement, Portfolio
from app.schemas.enums import AssetType, EmploymentType, LoanPurpose, RiskAppetite

DATA_DIR = Path("data")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def load_products(path: Path | None = None) -> list[LoanProduct]:
    return [
        LoanProduct(
            product_id=row["product_id"],
            lender=row["lender"],
            product_name=row["product_name"],
            purposes=[LoanPurpose(p) for p in row["purposes"].split("|")],
            annual_rate=float(row["annual_rate"]),
            min_amount=float(row["min_amount"]),
            max_amount=float(row["max_amount"]),
            min_tenure_months=int(row["min_tenure_months"]),
            max_tenure_months=int(row["max_tenure_months"]),
            min_credit_score=int(row["min_credit_score"]),
            min_monthly_income=float(row["min_monthly_income"]),
            processing_fee_pct=float(row["processing_fee_pct"]),
        )
        for row in _rows(path or DATA_DIR / "loan_products.csv")
    ]


def load_customers(
    path: Path | None = None,
) -> list[tuple[CustomerProfile, LoanRequirement]]:
    """The requirement travels with the profile — one request per synthetic customer."""
    out = []
    for row in _rows(path or DATA_DIR / "customers.csv"):
        profile = CustomerProfile(
            user_id=row["user_id"],
            monthly_income=float(row["monthly_income"]),
            monthly_expenses=float(row["monthly_expenses"]),
            existing_emi=float(row["existing_emi"]),
            credit_score=int(row["credit_score"]),
            employment_type=EmploymentType(row["employment_type"]),
            employment_years=float(row["employment_years"]),
            age=int(row["age"]),
            dependents=int(row["dependents"]),
        )
        requirement = LoanRequirement(
            purpose=LoanPurpose(row["purpose"]),
            required_amount=float(row["required_amount"]),
            preferred_tenure_months=int(row["preferred_tenure_months"]),
            risk_appetite=RiskAppetite(row["risk_appetite"]),
        )
        out.append((profile, requirement))
    return out


def load_portfolios(path: Path | None = None) -> dict[str, Portfolio]:
    """
    Keyed by user_id. A customer with no holdings is ABSENT from the file; callers
    get an empty Portfolio for them, which is the first-class zero-portfolio path.
    """
    holdings: dict[str, list[Holding]] = {}
    for row in _rows(path or DATA_DIR / "portfolios.csv"):
        holdings.setdefault(row["user_id"], []).append(
            Holding(
                asset_type=AssetType(row["asset_type"]),
                current_value=float(row["current_value"]),
                invested_value=float(row["invested_value"]),
            )
        )
    return {user_id: Portfolio(holdings=items) for user_id, items in holdings.items()}


def load_history(path: Path | None = None) -> list[dict[str, str]]:
    """Raw rows. The personalization store owns their interpretation, not this module."""
    return _rows(path or DATA_DIR / "history.csv")
