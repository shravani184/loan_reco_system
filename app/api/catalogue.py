"""
Catalogue loading for the API layer (P14).

The catalogue is loaded from CSV into Pydantic models via the STDLIB csv module —
never into a DataFrame (CONTEXT.md 17.2). Loading lives here, in the API layer,
because the catalogue is a runtime input, not an offline artifact, and app/ must
stay free of the offline package. P7's generator wrote the file; this module turns
rows back into LoanProduct contracts for the pipeline.

Lines beginning with '#' are provenance comments written by generate_data.py and are
skipped. `purposes` is a '|'-separated column.
"""

import csv
from pathlib import Path

from app.config import settings
from app.schemas import LoanProduct
from app.schemas.enums import LoanPurpose


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def load_catalogue(path: Path | None = None) -> list[LoanProduct]:
    """Load the synthetic loan catalogue from CSV into LoanProduct contracts."""
    rows = _rows(path or Path(settings.LOAN_CATALOGUE_PATH))
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
        for row in rows
    ]
