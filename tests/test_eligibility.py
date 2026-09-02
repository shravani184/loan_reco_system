"""
Eligibility Engine (P4).

Every test uses tests/fixtures.py. The synthetic catalogue CSV does not exist until
P7, and nothing here reads data/.
"""

import pytest

from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.schemas import CustomerProfile, LoanProduct, LoanRequirement
from app.schemas.enums import (
    EligibilityStatus,
    LoanPurpose,
    MismatchReasonCode,
    RiskAppetite,
)
from tests import fixtures


def _check(customer=None, requirement=None, catalogue=None):
    customer = customer or fixtures.standard_customer()
    return check_eligibility(
        customer,
        analyze_financials(customer),
        requirement or fixtures.standard_requirement(),
        catalogue if catalogue is not None else fixtures.mock_catalogue(),
    )


def _home_product(**overrides) -> LoanProduct:
    """
    HL-002 is the permissive home product: min score 650, min income 35000, amount
    300k-5M, tenure 36-180. The standard customer and requirement clear all of it,
    so an override fails exactly one rule and nothing else.
    """
    payload = next(
        p for p in fixtures.mock_catalogue() if p.product_id == "HL-002"
    ).model_dump()
    payload.update(overrides)
    return LoanProduct.model_validate(payload)


def _only(results):
    assert len(results) == 1
    return results[0]


# --------------------------------------------------- the output-length invariant


def test_output_length_equals_catalogue_length():
    catalogue = fixtures.mock_catalogue()
    assert len(_check(catalogue=catalogue)) == len(catalogue)


def test_output_length_holds_when_every_product_fails():
    """A dropped product is an unexplainable gap in the funnel, so none is dropped."""
    catalogue = fixtures.mock_catalogue()
    results = _check(customer=fixtures.no_match_customer(), catalogue=catalogue)
    assert len(results) == len(catalogue)
    assert all(r.status is EligibilityStatus.INELIGIBLE for r in results)


def test_output_preserves_catalogue_order_and_ids():
    catalogue = fixtures.mock_catalogue()
    results = _check(catalogue=catalogue)
    assert [r.product_id for r in results] == [p.product_id for p in catalogue]


def test_every_product_appears_exactly_once():
    results = _check()
    ids = [r.product_id for r in results]
    assert len(ids) == len(set(ids))


def test_empty_catalogue_returns_empty_list():
    assert _check(catalogue=[]) == []


def test_inputs_are_not_mutated():
    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    catalogue = fixtures.mock_catalogue()
    before = (
        customer.model_dump(),
        requirement.model_dump(),
        [p.model_dump() for p in catalogue],
    )
    check_eligibility(customer, analyze_financials(customer), requirement, catalogue)
    assert (
        customer.model_dump(),
        requirement.model_dump(),
        [p.model_dump() for p in catalogue],
    ) == before


# ------------------------------------------------------ each rule, in isolation


def test_credit_score_below_minimum():
    customer = fixtures.standard_customer().model_copy(update={"credit_score": 649})
    result = _only(_check(customer=customer, catalogue=[_home_product()]))
    assert result.status is EligibilityStatus.INELIGIBLE
    assert result.reason_code is MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM
    assert result.observed_value == 649.0
    assert result.threshold_value == 650.0


def test_credit_score_exactly_at_the_minimum_is_eligible():
    customer = fixtures.standard_customer().model_copy(update={"credit_score": 650})
    assert (
        _only(_check(customer=customer, catalogue=[_home_product()])).status
        is EligibilityStatus.ELIGIBLE
    )


def test_income_below_minimum():
    product = _home_product(min_monthly_income=150_000.0)
    result = _only(_check(catalogue=[product]))
    assert result.reason_code is MismatchReasonCode.INCOME_BELOW_MINIMUM
    assert result.observed_value == 120_000.0
    assert result.threshold_value == 150_000.0


def test_income_exactly_at_the_minimum_is_eligible():
    product = _home_product(min_monthly_income=120_000.0)
    assert _only(_check(catalogue=[product])).status is EligibilityStatus.ELIGIBLE


def test_income_is_read_from_financial_metrics_not_the_raw_profile():
    """
    FinancialMetrics owns income. Passing metrics that disagree with the profile
    must change the outcome, proving which source the rule actually reads.
    """
    customer = fixtures.standard_customer()
    metrics = analyze_financials(customer).model_copy(
        update={"monthly_income": 1_000.0}
    )
    product = _home_product(min_monthly_income=50_000.0)
    result = _only(
        check_eligibility(
            customer, metrics, fixtures.standard_requirement(), [product]
        )
    )
    assert result.reason_code is MismatchReasonCode.INCOME_BELOW_MINIMUM
    assert result.observed_value == 1_000.0


def test_amount_above_product_max():
    product = _home_product(max_amount=1_000_000.0)
    result = _only(_check(catalogue=[product]))
    assert result.reason_code is MismatchReasonCode.AMOUNT_ABOVE_PRODUCT_MAX
    assert result.observed_value == 2_000_000.0
    assert result.threshold_value == 1_000_000.0


def test_amount_below_product_min():
    product = _home_product(min_amount=3_000_000.0)
    result = _only(_check(catalogue=[product]))
    assert result.reason_code is MismatchReasonCode.AMOUNT_BELOW_PRODUCT_MIN
    assert result.observed_value == 2_000_000.0
    assert result.threshold_value == 3_000_000.0


@pytest.mark.parametrize("amount", [300_000.0, 5_000_000.0])
def test_amount_exactly_at_either_product_limit_is_eligible(amount):
    requirement = fixtures.standard_requirement().model_copy(
        update={"required_amount": amount}
    )
    assert (
        _only(_check(requirement=requirement, catalogue=[_home_product()])).status
        is EligibilityStatus.ELIGIBLE
    )


def test_tenure_above_product_max():
    requirement = fixtures.standard_requirement().model_copy(
        update={"preferred_tenure_months": 240}
    )
    result = _only(_check(requirement=requirement, catalogue=[_home_product()]))
    assert result.reason_code is MismatchReasonCode.TENURE_OUT_OF_RANGE
    assert result.observed_value == 240.0
    assert result.threshold_value == 180.0


def test_tenure_below_product_min():
    requirement = fixtures.standard_requirement().model_copy(
        update={"preferred_tenure_months": 24}
    )
    result = _only(_check(requirement=requirement, catalogue=[_home_product()]))
    assert result.reason_code is MismatchReasonCode.TENURE_OUT_OF_RANGE
    assert result.observed_value == 24.0
    assert result.threshold_value == 36.0


def test_tenure_out_of_range_reports_the_bound_it_actually_crossed():
    """One code, two bounds — the threshold must say which one."""
    low = _only(
        _check(
            requirement=fixtures.standard_requirement().model_copy(
                update={"preferred_tenure_months": 24}
            ),
            catalogue=[_home_product()],
        )
    )
    high = _only(
        _check(
            requirement=fixtures.standard_requirement().model_copy(
                update={"preferred_tenure_months": 240}
            ),
            catalogue=[_home_product()],
        )
    )
    assert low.threshold_value == 36.0
    assert high.threshold_value == 180.0


@pytest.mark.parametrize("tenure", [36, 180])
def test_tenure_exactly_at_either_product_limit_is_eligible(tenure):
    requirement = fixtures.standard_requirement().model_copy(
        update={"preferred_tenure_months": tenure}
    )
    assert (
        _only(_check(requirement=requirement, catalogue=[_home_product()])).status
        is EligibilityStatus.ELIGIBLE
    )


def test_purpose_not_supported():
    requirement = fixtures.standard_requirement().model_copy(
        update={"purpose": LoanPurpose.BUSINESS}
    )
    result = _only(_check(requirement=requirement, catalogue=[_home_product()]))
    assert result.reason_code is MismatchReasonCode.PURPOSE_NOT_SUPPORTED


def test_purpose_mismatch_carries_no_observed_or_threshold():
    """Purpose is categorical; there is no numeric pair to report."""
    requirement = fixtures.standard_requirement().model_copy(
        update={"purpose": LoanPurpose.BUSINESS}
    )
    result = _only(_check(requirement=requirement, catalogue=[_home_product()]))
    assert result.observed_value is None
    assert result.threshold_value is None


def test_a_multi_purpose_product_accepts_either_of_its_purposes():
    personal = next(
        p for p in fixtures.mock_catalogue() if p.product_id == "PL-001"
    )
    for purpose in (LoanPurpose.PERSONAL, LoanPurpose.MEDICAL):
        requirement = LoanRequirement(
            purpose=purpose,
            required_amount=500_000.0,
            preferred_tenure_months=36,
            risk_appetite=RiskAppetite.MODERATE,
        )
        assert (
            _only(_check(requirement=requirement, catalogue=[personal])).status
            is EligibilityStatus.ELIGIBLE
        )


# ------------------------------------------------------------------ rule order


def test_purpose_is_reported_before_any_numeric_failure():
    """A product for the wrong purpose is not a near miss; it is the wrong product."""
    customer = fixtures.standard_customer().model_copy(update={"credit_score": 400})
    requirement = fixtures.standard_requirement().model_copy(
        update={"purpose": LoanPurpose.BUSINESS, "required_amount": 50_000_000.0}
    )
    result = _only(_check(customer=customer, requirement=requirement, catalogue=[_home_product()]))
    assert result.reason_code is MismatchReasonCode.PURPOSE_NOT_SUPPORTED


def test_credit_score_is_reported_before_amount():
    """The least-adjustable failure is the one the customer is shown."""
    customer = fixtures.standard_customer().model_copy(update={"credit_score": 400})
    # Both rules genuinely fail: score 400 < 650, and the 2M request exceeds a 1M cap.
    product = _home_product(max_amount=1_000_000.0)
    assert _only(_check(catalogue=[product])).reason_code is (
        MismatchReasonCode.AMOUNT_ABOVE_PRODUCT_MAX
    )
    result = _only(_check(customer=customer, catalogue=[product]))
    assert result.reason_code is MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM


def test_income_is_reported_before_tenure():
    product = _home_product(min_monthly_income=999_999.0, max_tenure_months=48)
    result = _only(_check(catalogue=[product]))
    assert result.reason_code is MismatchReasonCode.INCOME_BELOW_MINIMUM


# ------------------------------------------------------------- whole catalogue


def test_qualifying_customer_passes_every_product_it_can_apply_for():
    """
    No single requirement can pass all six products, because the catalogue's purposes
    are near-disjoint by design. So a strong customer is checked against each product
    with a requirement matched to that product's own purpose and limits, and must be
    ELIGIBLE for every one.
    """
    strong = CustomerProfile(
        user_id="cust-strong",
        monthly_income=500_000.0,
        monthly_expenses=100_000.0,
        existing_emi=0.0,
        credit_score=820,
        employment_type=fixtures.standard_customer().employment_type,
        employment_years=12.0,
        age=40,
        dependents=0,
    )
    for product in fixtures.mock_catalogue():
        requirement = LoanRequirement(
            purpose=product.purposes[0],
            required_amount=product.min_amount,
            preferred_tenure_months=product.min_tenure_months,
            risk_appetite=RiskAppetite.MODERATE,
        )
        result = _only(
            _check(customer=strong, requirement=requirement, catalogue=[product])
        )
        assert result.status is EligibilityStatus.ELIGIBLE, product.product_id
        assert result.reason_code is None


def test_standard_customer_passes_both_home_products():
    results = {r.product_id: r for r in _check()}
    assert results["HL-001"].status is EligibilityStatus.ELIGIBLE
    assert results["HL-002"].status is EligibilityStatus.ELIGIBLE


def test_standard_customer_fails_non_home_products_on_purpose():
    results = {r.product_id: r for r in _check()}
    for product_id in ("VL-001", "PL-001", "EL-001", "BL-001"):
        assert results[product_id].status is EligibilityStatus.INELIGIBLE
        assert (
            results[product_id].reason_code
            is MismatchReasonCode.PURPOSE_NOT_SUPPORTED
        )


def test_no_match_customer_is_ineligible_everywhere_with_reason_codes():
    results = _check(customer=fixtures.no_match_customer())
    assert all(r.status is EligibilityStatus.INELIGIBLE for r in results)
    assert all(r.reason_code is not None for r in results)


def test_no_match_customer_fails_home_products_on_credit_score():
    """Purpose matches for the home products, so the next rule is what fires."""
    results = {r.product_id: r for r in _check(customer=fixtures.no_match_customer())}
    for product_id in ("HL-001", "HL-002"):
        assert (
            results[product_id].reason_code
            is MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM
        )
        assert results[product_id].observed_value == 545.0


def test_every_ineligible_result_carries_a_documented_eligibility_code():
    """P4 may not invent a code outside the six eligibility reasons."""
    eligibility_codes = {
        MismatchReasonCode.CREDIT_SCORE_BELOW_MINIMUM,
        MismatchReasonCode.INCOME_BELOW_MINIMUM,
        MismatchReasonCode.AMOUNT_ABOVE_PRODUCT_MAX,
        MismatchReasonCode.AMOUNT_BELOW_PRODUCT_MIN,
        MismatchReasonCode.TENURE_OUT_OF_RANGE,
        MismatchReasonCode.PURPOSE_NOT_SUPPORTED,
    }
    for customer in (fixtures.standard_customer(), fixtures.no_match_customer()):
        for result in _check(customer=customer):
            if result.status is EligibilityStatus.INELIGIBLE:
                assert result.reason_code in eligibility_codes


def test_numeric_failures_always_carry_observed_and_threshold():
    """CONTEXT.md 7.2 — a reason without its values is not a usable explanation."""
    results = _check(customer=fixtures.no_match_customer())
    for result in results:
        if (
            result.status is EligibilityStatus.INELIGIBLE
            and result.reason_code is not MismatchReasonCode.PURPOSE_NOT_SUPPORTED
        ):
            assert result.observed_value is not None
            assert result.threshold_value is not None
