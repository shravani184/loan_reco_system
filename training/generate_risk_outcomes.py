"""
Generate the SYNTHETIC repayment outcome that the secondary risk classifier learns.

WHY THIS FILE EXISTS AS ITS OWN MODULE. Phase 7 generated customers, portfolios,
history and relevance labels — but nothing about repayment. The risk model therefore
had no target at all. Burying the invention of that target inside a training script
would hide the single most consequential assumption in the risk model, so the
generative process lives here, alone, documented, and readable.

THESE OUTCOMES ARE SYNTHETIC AND NOBODY DEFAULTED. There is no observed repayment data
in this project. A default flag is drawn from an explicit latent-risk model defined
below, so the trained classifier partially recovers THAT MODEL — exactly as the
recommender partially recovers the labeling policy (CONTEXT.md section 11). Reported
ROC-AUC measures agreement with this process, not real credit risk.

THE UNOBSERVED FACTOR IS THE POINT. Part of each customer's default propensity comes
from a latent shock term that is deliberately NOT in RISK_FEATURE_COLUMNS. Without it
the label would be a deterministic function of the features, the classifier would
recover it almost perfectly, and a near-1.0 ROC-AUC would be an artifact of the
generator rather than evidence of anything. The latent term puts a real ceiling on
achievable performance, which is what makes the reported metric meaningful.

OFFLINE ONLY. Run:

    python -m training.generate_risk_outcomes
"""

import csv
import math
import random
from pathlib import Path

from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.schemas.enums import EmploymentType
from training.datasets import load_customers, load_portfolios

DATA_DIR = Path("data")
RISK_SEED = 20260905

SYNTHETIC_HEADER = (
    "# SYNTHETIC REPAYMENT OUTCOMES — drawn by training/generate_risk_outcomes.py "
    "from a documented latent-risk model. Nobody defaulted; nobody exists."
)

# --------------------------------------------------------------------------
# THE LATENT RISK MODEL. Every coefficient is a log-odds contribution, applied to
# a RATIO or a standardised quantity so the process is scale-free like the labeling
# policy. Signs are stated so a reader can sanity-check the direction of each term.
# --------------------------------------------------------------------------

# Baseline log-odds. Sets the overall default rate before any customer effect.
# Calibrated so the population default rate lands near 15%, a plausible retail
# portfolio rate. Chosen before any model was trained, so it is a property of the
# generator rather than a number tuned to flatter a metric.
BASE_LOG_ODDS = -3.10

# Credit score, expressed as standard deviations below 700. Higher score -> lower risk.
CREDIT_SCORE_PIVOT = 700.0
CREDIT_SCORE_SCALE = 80.0
W_CREDIT_SCORE = 0.95  # per SD below the pivot

# Existing debt burden. More of the income already committed -> higher risk.
W_DEBT_BURDEN = 2.60

# Expense ratio. Less margin between income and outgoings -> higher risk.
W_EXPENSE_RATIO = 1.40

# Income stability (employment type and tenure), in [0,1]. More stable -> lower risk.
W_INCOME_STABILITY = -1.30

# Liquid savings measured in months of expenses, capped. A buffer absorbs shocks.
BUFFER_CAP_MONTHS = 12.0
W_LIQUID_BUFFER = -0.11  # per month of buffer, up to the cap

# Requested amount relative to annual income. Borrowing more of your income -> riskier.
W_LOAN_TO_INCOME = 0.42

# Dependents add fixed obligations.
W_DEPENDENTS = 0.16

# Self-employed and contract incomes are lumpier than the stability score alone
# captures.
EMPLOYMENT_LOG_ODDS = {
    EmploymentType.SALARIED: 0.00,
    EmploymentType.SELF_EMPLOYED: 0.35,
    EmploymentType.CONTRACT: 0.55,
    EmploymentType.RETIRED: 0.20,
}

# THE UNOBSERVED FACTOR: job loss, illness, a family emergency, a business failing.
# Real and material, and NOT a feature. This is what stops the classifier from
# recovering the label exactly.
W_LATENT_SHOCK = 1.25

MONTHS_PER_YEAR = 12


def _standardised_credit_deficit(credit_score: int) -> float:
    """Standard deviations BELOW the pivot. Negative for a strong score."""
    return (CREDIT_SCORE_PIVOT - credit_score) / CREDIT_SCORE_SCALE


def default_log_odds(
    customer, financial, portfolio, requirement, latent_shock: float
) -> float:
    """
    The latent-risk model, in full. Every term is documented above.

    `latent_shock` is a standard normal draw representing everything the feature set
    cannot see.
    """
    annual_income = financial.monthly_income * MONTHS_PER_YEAR
    loan_to_income = (
        requirement.required_amount / annual_income if annual_income > 0 else 0.0
    )
    buffer_months = (
        min(portfolio.liquid_value / financial.monthly_expenses, BUFFER_CAP_MONTHS)
        if financial.monthly_expenses > 0
        else BUFFER_CAP_MONTHS
    )

    return (
        BASE_LOG_ODDS
        + W_CREDIT_SCORE * _standardised_credit_deficit(customer.credit_score)
        + W_DEBT_BURDEN * min(financial.debt_burden_ratio, 1.0)
        + W_EXPENSE_RATIO * min(financial.expense_ratio, 2.0)
        + W_INCOME_STABILITY * financial.income_stability_score
        + W_LIQUID_BUFFER * buffer_months
        + W_LOAN_TO_INCOME * min(loan_to_income, 6.0)
        + W_DEPENDENTS * customer.dependents
        + EMPLOYMENT_LOG_ODDS[customer.employment_type]
        + W_LATENT_SHOCK * latent_shock
    )


def generate_outcomes() -> list[dict]:
    """One row per customer: the drawn outcome plus the propensity it was drawn from."""
    rng = random.Random(RISK_SEED)
    portfolios = load_portfolios()

    rows = []
    for profile, requirement in load_customers():
        financial = analyze_financials(profile)
        portfolio = analyze_portfolio(portfolios.get(profile.user_id))
        latent_shock = rng.gauss(0.0, 1.0)
        log_odds = default_log_odds(
            profile, financial, portfolio, requirement, latent_shock
        )
        probability = 1.0 / (1.0 + math.exp(-log_odds))
        rows.append(
            {
                "user_id": profile.user_id,
                "defaulted": int(rng.random() < probability),
                # Recorded for auditing the generator, NOT used as a feature and not
                # available at inference time.
                "latent_default_probability": round(probability, 6),
                "latent_shock": round(latent_shock, 6),
                "SYNTHETIC": "TRUE",
            }
        )
    return rows


def main() -> None:
    rows = generate_outcomes()
    path = DATA_DIR / "risk_outcomes.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        handle.write(SYNTHETIC_HEADER + "\n")
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    defaults = sum(row["defaulted"] for row in rows)
    mean_probability = sum(row["latent_default_probability"] for row in rows) / len(rows)
    print(f"risk_outcomes.csv      {len(rows)} customers")
    print(f"default rate           {defaults / len(rows):.4f} ({defaults} defaults)")
    print(f"mean latent propensity {mean_probability:.4f}")
    print("OUTCOMES ARE SYNTHETIC — drawn from a documented latent-risk model")


if __name__ == "__main__":
    main()
