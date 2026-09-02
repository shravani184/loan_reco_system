"""
Financial Intelligence — deterministic, no ML.

Owns the customer's income-side metrics and nothing else. It does not decide
eligibility, does not touch loan products, does not compute an EMI for any specific
loan, and never calls a model (CONTEXT.md section 4).

Every threshold comes from app/config.py. There are no numbers in this file.
"""

from app.config import settings
from app.schemas import CustomerProfile, FinancialMetrics
from app.schemas.enums import FinancialHealth


def income_ratio(numerator: float, income: float) -> float:
    """
    A ratio measured against monthly income.

    Public because P5 computes a post-loan debt burden against the same convention.
    Two implementations of the zero-income rule would be a defect even if they agreed.

    With zero income the true ratio is undefined or infinite. These values become ML
    features, so a finite stand-in from config is used rather than a None or a crash.
    A zero numerator over zero income is genuinely zero, not undefined.
    """
    if income > 0.0:
        return numerator / income
    return 0.0 if numerator <= 0.0 else settings.UNDEFINED_RATIO_VALUE


def _income_stability_score(customer: CustomerProfile) -> float:
    """
    Bounded [0, 1]: how dependable this income is, from employment type and tenure.

    Tenure contributes up to STABILITY_TENURE_WEIGHT of the score and saturates at
    STABILITY_FULL_TENURE_YEARS.
    """
    base = settings.EMPLOYMENT_STABILITY_BASE[customer.employment_type]
    weight = settings.STABILITY_TENURE_WEIGHT
    tenure_fraction = min(
        customer.employment_years / settings.STABILITY_FULL_TENURE_YEARS, 1.0
    )
    return base * (1.0 - weight) + tenure_fraction * weight


def _health_band(savings_rate: float, debt_burden_ratio: float) -> FinancialHealth:
    """
    The band, in two independent steps so each is separately testable:

      1. place the customer by savings rate
      2. demote exactly one band if existing debt burden is above the threshold

    The ladder is derived from the config thresholds sorted descending, so config is
    the single source of both the cut-points and their order. POOR is the floor and
    has no threshold entry.
    """
    ordered = sorted(
        settings.FINANCIAL_HEALTH_MIN_SAVINGS_RATE.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    ladder = [band for band, _ in ordered] + [FinancialHealth.POOR]

    index = len(ladder) - 1
    for position, (_, min_savings_rate) in enumerate(ordered):
        if savings_rate >= min_savings_rate:
            index = position
            break

    if debt_burden_ratio > settings.FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD:
        index = min(index + 1, len(ladder) - 1)

    return ladder[index]


def analyze_financials(customer: CustomerProfile) -> FinancialMetrics:
    """
    Derive the customer's financial metrics. Pure: no I/O, no global state, no model
    calls, and the input is not mutated.

    Zero income and zero expenses are handled, not special-cased away.
    """
    income = customer.monthly_income
    expenses = customer.monthly_expenses
    existing_emi = customer.existing_emi

    # Deliberately not clamped: a customer whose outgoings exceed their income has a
    # negative disposable income, and hiding that would misinform every later stage.
    disposable_income = income - expenses - existing_emi

    expense_ratio = income_ratio(expenses, income)
    debt_burden_ratio = income_ratio(existing_emi, income)
    savings_rate = income_ratio(max(disposable_income, 0.0), income)

    # The ceiling is what the customer can sustain, so it floors at zero: a negative
    # disposable income affords no EMI at all, it does not afford a negative one.
    emi_affordability_ceiling = (
        max(disposable_income, 0.0) * settings.MAX_EMI_SHARE_OF_DISPOSABLE_INCOME
    )

    return FinancialMetrics(
        monthly_income=income,
        monthly_expenses=expenses,
        existing_emi=existing_emi,
        disposable_income=disposable_income,
        debt_burden_ratio=debt_burden_ratio,
        expense_ratio=expense_ratio,
        emi_affordability_ceiling=emi_affordability_ceiling,
        income_stability_score=_income_stability_score(customer),
        financial_health=_health_band(savings_rate, debt_burden_ratio),
    )
