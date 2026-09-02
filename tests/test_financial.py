"""
Financial Intelligence (P1).

The worked example is hand-computed and checked field by field; nothing here would
still pass if the function returned a constant.
"""

import pytest

from app.config import settings
from app.core.financial import analyze_financials
from app.schemas import CustomerProfile
from app.schemas.enums import EmploymentType, FinancialHealth
from tests import fixtures


def _customer(**overrides) -> CustomerProfile:
    payload = fixtures.standard_customer().model_dump()
    payload.update(overrides)
    return CustomerProfile.model_validate(payload)


# ------------------------------------------------------------- worked example


def test_worked_example_from_the_phase_prompt():
    """income 100000, expenses 35000, existing EMI 8000 -> disposable 57000, DBR 8%."""
    metrics = analyze_financials(
        _customer(
            monthly_income=100_000.0,
            monthly_expenses=35_000.0,
            existing_emi=8_000.0,
        )
    )
    assert metrics.disposable_income == 57_000.0
    assert metrics.debt_burden_ratio == pytest.approx(0.08)
    assert metrics.expense_ratio == pytest.approx(0.35)
    # savings rate 0.57 clears the EXCELLENT cut-point, DBR is far below the
    # demotion threshold.
    assert metrics.financial_health is FinancialHealth.EXCELLENT
    # 57000 * MAX_EMI_SHARE_OF_DISPOSABLE_INCOME (0.50)
    assert metrics.emi_affordability_ceiling == pytest.approx(
        57_000.0 * settings.MAX_EMI_SHARE_OF_DISPOSABLE_INCOME
    )


def test_passthrough_fields_are_not_altered():
    metrics = analyze_financials(fixtures.standard_customer())
    customer = fixtures.standard_customer()
    assert metrics.monthly_income == customer.monthly_income
    assert metrics.monthly_expenses == customer.monthly_expenses
    assert metrics.existing_emi == customer.existing_emi


def test_input_is_not_mutated():
    customer = fixtures.standard_customer()
    before = customer.model_dump()
    analyze_financials(customer)
    assert customer.model_dump() == before


# ------------------------------------------------------------------ boundaries


def test_zero_income_does_not_crash_and_reports_undefined_ratios():
    metrics = analyze_financials(
        _customer(monthly_income=0.0, monthly_expenses=5_000.0, existing_emi=1_000.0)
    )
    assert metrics.disposable_income == -6_000.0
    assert metrics.expense_ratio == settings.UNDEFINED_RATIO_VALUE
    assert metrics.debt_burden_ratio == settings.UNDEFINED_RATIO_VALUE
    assert metrics.emi_affordability_ceiling == 0.0
    assert metrics.financial_health is FinancialHealth.POOR


def test_zero_income_and_zero_outgoings_is_zero_not_undefined():
    metrics = analyze_financials(
        _customer(monthly_income=0.0, monthly_expenses=0.0, existing_emi=0.0)
    )
    assert metrics.expense_ratio == 0.0
    assert metrics.debt_burden_ratio == 0.0
    assert metrics.disposable_income == 0.0


def test_expenses_exceeding_income_give_negative_disposable_and_zero_ceiling():
    """The negative is reported, not clamped — hiding it would misinform P5."""
    metrics = analyze_financials(
        _customer(
            monthly_income=40_000.0, monthly_expenses=52_000.0, existing_emi=0.0
        )
    )
    assert metrics.disposable_income == -12_000.0
    assert metrics.expense_ratio == pytest.approx(1.3)
    assert metrics.emi_affordability_ceiling == 0.0
    assert metrics.financial_health is FinancialHealth.POOR


def test_no_existing_emi_gives_zero_debt_burden():
    metrics = analyze_financials(
        _customer(
            monthly_income=90_000.0, monthly_expenses=40_000.0, existing_emi=0.0
        )
    )
    assert metrics.debt_burden_ratio == 0.0
    assert metrics.disposable_income == 50_000.0


def test_zero_expenses_is_handled():
    metrics = analyze_financials(
        _customer(monthly_income=50_000.0, monthly_expenses=0.0, existing_emi=0.0)
    )
    assert metrics.expense_ratio == 0.0
    assert metrics.emi_affordability_ceiling == pytest.approx(
        50_000.0 * settings.MAX_EMI_SHARE_OF_DISPOSABLE_INCOME
    )


# ------------------------------------------------------- health band transitions


def _band_for_savings_rate(savings_rate: float) -> FinancialHealth:
    """Income fixed at 100000, no existing EMI, so savings rate is set by expenses."""
    income = 100_000.0
    return analyze_financials(
        _customer(
            monthly_income=income,
            monthly_expenses=income * (1.0 - savings_rate),
            existing_emi=0.0,
        )
    ).financial_health


@pytest.mark.parametrize(
    "band",
    [FinancialHealth.EXCELLENT, FinancialHealth.GOOD, FinancialHealth.FAIR],
)
def test_band_transition_exactly_at_each_threshold(band):
    """At the cut-point the customer is IN the band; a hair below, they are not."""
    threshold = settings.FINANCIAL_HEALTH_MIN_SAVINGS_RATE[band]
    assert _band_for_savings_rate(threshold) is band
    assert _band_for_savings_rate(threshold - 0.001) is not band


def test_below_the_lowest_threshold_is_poor():
    lowest = min(settings.FINANCIAL_HEALTH_MIN_SAVINGS_RATE.values())
    assert _band_for_savings_rate(lowest - 0.001) is FinancialHealth.POOR


def test_bands_are_ordered_by_savings_rate():
    thresholds = settings.FINANCIAL_HEALTH_MIN_SAVINGS_RATE
    assert (
        thresholds[FinancialHealth.EXCELLENT]
        > thresholds[FinancialHealth.GOOD]
        > thresholds[FinancialHealth.FAIR]
    )


def test_poor_has_no_threshold_entry_because_it_is_the_floor():
    assert FinancialHealth.POOR not in settings.FINANCIAL_HEALTH_MIN_SAVINGS_RATE


def test_high_debt_burden_demotes_exactly_one_band():
    """
    Same savings rate, two debt burdens. Expenses are reduced by the existing EMI so
    the savings rate is held constant and only the demotion differs.
    """
    income = 100_000.0
    demoting_emi = income * (
        settings.FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD + 0.05
    )
    savings_rate = 0.30  # inside GOOD

    clean = analyze_financials(
        _customer(
            monthly_income=income,
            monthly_expenses=income * (1.0 - savings_rate),
            existing_emi=0.0,
        )
    )
    burdened = analyze_financials(
        _customer(
            monthly_income=income,
            monthly_expenses=income * (1.0 - savings_rate) - demoting_emi,
            existing_emi=demoting_emi,
        )
    )
    assert clean.financial_health is FinancialHealth.GOOD
    assert burdened.financial_health is FinancialHealth.FAIR
    assert burdened.disposable_income == pytest.approx(clean.disposable_income)


def test_demotion_cannot_fall_below_poor():
    metrics = analyze_financials(
        _customer(
            monthly_income=50_000.0,
            monthly_expenses=20_000.0,
            existing_emi=29_000.0,
        )
    )
    assert metrics.debt_burden_ratio > (
        settings.FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD
    )
    assert metrics.financial_health is FinancialHealth.POOR


# ---------------------------------------------------------- income stability


def test_income_stability_is_bounded_and_ordered_by_employment_type():
    scores = {
        employment: analyze_financials(
            _customer(employment_type=employment, employment_years=0.0)
        ).income_stability_score
        for employment in EmploymentType
    }
    assert all(0.0 <= score <= 1.0 for score in scores.values())
    assert scores[EmploymentType.SALARIED] > scores[EmploymentType.SELF_EMPLOYED]
    assert scores[EmploymentType.SELF_EMPLOYED] > scores[EmploymentType.CONTRACT]


def test_longer_tenure_raises_stability():
    short = analyze_financials(_customer(employment_years=0.0)).income_stability_score
    long = analyze_financials(_customer(employment_years=9.0)).income_stability_score
    assert long > short


def test_tenure_contribution_saturates():
    at_full = analyze_financials(
        _customer(employment_years=settings.STABILITY_FULL_TENURE_YEARS)
    ).income_stability_score
    beyond = analyze_financials(_customer(employment_years=40.0)).income_stability_score
    assert at_full == pytest.approx(beyond)
    assert beyond <= 1.0


def test_stability_score_matches_the_documented_formula():
    customer = _customer(
        employment_type=EmploymentType.SALARIED, employment_years=6.5
    )
    base = settings.EMPLOYMENT_STABILITY_BASE[EmploymentType.SALARIED]
    weight = settings.STABILITY_TENURE_WEIGHT
    expected = base * (1.0 - weight) + (
        6.5 / settings.STABILITY_FULL_TENURE_YEARS
    ) * weight
    assert analyze_financials(customer).income_stability_score == pytest.approx(expected)


# ------------------------------------------------------------------ fixtures


def test_no_match_customer_is_financially_weak():
    metrics = analyze_financials(fixtures.no_match_customer())
    assert metrics.disposable_income == -500.0
    assert metrics.emi_affordability_ceiling == 0.0
    assert metrics.financial_health is FinancialHealth.POOR
