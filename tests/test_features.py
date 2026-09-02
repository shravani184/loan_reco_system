"""
Shared feature engineering (P8).

Uses tests/fixtures.py only. No model is loaded and nothing reads data/.
"""

import numpy as np
import pytest

from app.core.candidates import generate_candidates
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.ml import features as F
from app.schemas.enums import (
    EligibilityStatus,
    FinancingStrategy,
    LoanPurpose,
    RiskAppetite,
)
from tests import fixtures

CATALOGUE = fixtures.mock_catalogue()
PRODUCTS_BY_ID = {p.product_id: p for p in CATALOGUE}
RISK_PD = 0.07


@pytest.fixture(autouse=True)
def lender_encoding():
    """
    Install the saved mapping, as P11 will at model load, and restore afterwards so no
    test leaks module state into another.
    """
    before = F.get_lender_encoding()
    F.set_lender_encoding(F.build_lender_encoding(CATALOGUE))
    yield
    F.set_lender_encoding(before)


def _inputs(portfolio=None, personalization=None, requirement=None):
    customer = fixtures.standard_customer()
    return (
        customer,
        analyze_financials(customer),
        analyze_portfolio(
            fixtures.mixed_portfolio() if portfolio is None else portfolio
        ),
        personalization or fixtures.neutral_personalization(),
        requirement or fixtures.standard_requirement(),
    )


def _candidates(portfolio=None, requirement=None):
    customer, financial, portfolio_metrics, _, req = _inputs(
        portfolio=portfolio, requirement=requirement
    )
    outcomes = check_eligibility(customer, financial, req, CATALOGUE)
    eligible = {
        r.product_id for r in outcomes if r.status is EligibilityStatus.ELIGIBLE
    }
    return generate_candidates(
        req,
        financial,
        portfolio_metrics,
        [p for p in CATALOGUE if p.product_id in eligible],
    ).candidates


def _pair(candidate, portfolio=None, personalization=None, requirement=None):
    customer, financial, portfolio_metrics, personal, req = _inputs(
        portfolio=portfolio, personalization=personalization, requirement=requirement
    )
    return F.build_pair_features(
        customer,
        financial,
        portfolio_metrics,
        personal,
        req,
        PRODUCTS_BY_ID.get(candidate.product_id) if candidate.product_id else None,
        candidate,
        RISK_PD,
    )


# ------------------------------------------------------------------- shapes


def test_risk_vector_length_equals_its_column_count():
    customer, financial, portfolio, _, requirement = _inputs()
    vector = F.build_risk_features(customer, financial, portfolio, requirement)
    assert vector.shape == (len(F.RISK_FEATURE_COLUMNS),)


def test_pair_vector_length_equals_its_column_count():
    candidate = _candidates()[0]
    assert _pair(candidate).shape == (len(F.PAIR_FEATURE_COLUMNS),)


def test_vectors_are_numpy_float_arrays_not_dataframes():
    """No DataFrame crosses into app/ — pandas is a training-only dependency."""
    customer, financial, portfolio, _, requirement = _inputs()
    risk = F.build_risk_features(customer, financial, portfolio, requirement)
    pair = _pair(_candidates()[0])
    for vector in (risk, pair):
        assert isinstance(vector, np.ndarray)
        assert vector.dtype == np.float64


def test_column_names_are_unique():
    for columns in (F.RISK_FEATURE_COLUMNS, F.PAIR_FEATURE_COLUMNS):
        assert len(columns) == len(set(columns))


def test_no_column_is_empty_or_unnamed():
    for columns in (F.RISK_FEATURE_COLUMNS, F.PAIR_FEATURE_COLUMNS):
        assert all(isinstance(name, str) and name for name in columns)


# ------------------------------------------------------------- determinism


def test_identical_inputs_produce_byte_identical_vectors():
    candidate = _candidates()[0]
    first = _pair(candidate)
    second = _pair(candidate)
    assert first.tobytes() == second.tobytes()


def test_risk_features_are_byte_identical_on_repeat():
    customer, financial, portfolio, _, requirement = _inputs()
    first = F.build_risk_features(customer, financial, portfolio, requirement)
    second = F.build_risk_features(customer, financial, portfolio, requirement)
    assert first.tobytes() == second.tobytes()


def test_column_order_is_stable_across_calls():
    before = F.PAIR_FEATURE_COLUMNS
    _pair(_candidates()[0])
    assert F.PAIR_FEATURE_COLUMNS == before


# ------------------------------------------------------ the first-class paths


def test_no_portfolio_produces_a_valid_full_length_vector():
    candidates = _candidates(portfolio=fixtures.empty_portfolio())
    assert candidates
    vector = _pair(candidates[0], portfolio=fixtures.empty_portfolio())
    assert vector.shape == (len(F.PAIR_FEATURE_COLUMNS),)
    assert not np.isnan(vector).any()
    assert np.isfinite(vector).all()


def test_no_portfolio_and_mixed_portfolio_vectors_are_the_same_length():
    with_portfolio = _pair(_candidates()[0])
    without = _pair(
        _candidates(portfolio=fixtures.empty_portfolio())[0],
        portfolio=fixtures.empty_portfolio(),
    )
    assert with_portfolio.shape == without.shape


def test_cold_start_personalization_produces_a_valid_vector():
    vector = _pair(
        _candidates()[0], personalization=fixtures.neutral_personalization()
    )
    assert vector.shape == (len(F.PAIR_FEATURE_COLUMNS),)
    assert not np.isnan(vector).any()
    assert np.isfinite(vector).all()


def test_cold_start_is_flagged_in_the_vector():
    index = F.PAIR_FEATURE_COLUMNS.index("is_cold_start")
    vector = _pair(_candidates()[0], personalization=fixtures.neutral_personalization())
    assert vector[index] == 1.0


def test_populated_personalization_changes_the_vector():
    from app.schemas import PersonalizationContext

    warm = PersonalizationContext(
        is_cold_start=False,
        session_count=4,
        prior_declines=1,
        engagement_score=0.6,
        preferred_tenure_band_months=120,
        purpose_affinity={LoanPurpose.HOME: 1.0},
        strategy_affinity={FinancingStrategy.BORROW_100: 1.0},
    )
    candidate = _candidates()[0]
    assert not np.array_equal(_pair(candidate), _pair(candidate, personalization=warm))


def test_no_vector_contains_nan_for_any_generated_candidate():
    for candidate in _candidates():
        vector = _pair(candidate)
        assert not np.isnan(vector).any(), candidate.candidate_id
        assert np.isfinite(vector).all(), candidate.candidate_id


def test_zero_income_customer_produces_a_finite_vector():
    """Guarded division everywhere: no NaN, no inf, no exception."""
    from app.schemas import CustomerProfile

    customer = CustomerProfile(
        monthly_income=0.0,
        monthly_expenses=0.0,
        existing_emi=0.0,
        credit_score=600,
        employment_type=fixtures.standard_customer().employment_type,
        employment_years=0.0,
        age=30,
    )
    financial = analyze_financials(customer)
    portfolio = analyze_portfolio(fixtures.empty_portfolio())
    requirement = fixtures.standard_requirement()
    candidate = _candidates()[0]
    vector = F.build_pair_features(
        customer,
        financial,
        portfolio,
        fixtures.neutral_personalization(),
        requirement,
        PRODUCTS_BY_ID.get(candidate.product_id),
        candidate,
        RISK_PD,
    )
    assert np.isfinite(vector).all()


# ---------------------------------------------------------- the no-loan case


def _no_loan_candidate():
    return next(
        c
        for c in _candidates()
        if c.strategy is FinancingStrategy.LIQUIDATE_100
    )


def test_the_no_loan_candidate_produces_a_full_length_vector():
    vector = _pair(_no_loan_candidate())
    assert vector.shape == (len(F.PAIR_FEATURE_COLUMNS),)
    assert np.isfinite(vector).all()


def test_the_no_loan_candidate_is_flagged_not_encoded_as_a_missing_product():
    vector = _pair(_no_loan_candidate())
    assert vector[F.PAIR_FEATURE_COLUMNS.index("is_no_loan")] == 1.0
    assert vector[F.PAIR_FEATURE_COLUMNS.index("candidate_tenure_months")] == 0.0
    assert vector[F.PAIR_FEATURE_COLUMNS.index("loan_amount")] == 0.0
    # Not presented as a zero-month loan against the customer's preference.
    assert vector[F.PAIR_FEATURE_COLUMNS.index("tenure_delta_vs_preferred")] == 0.0


def test_a_borrowing_candidate_is_not_flagged_as_no_loan():
    borrowing = next(
        c for c in _candidates() if c.strategy is not FinancingStrategy.LIQUIDATE_100
    )
    vector = _pair(borrowing)
    assert vector[F.PAIR_FEATURE_COLUMNS.index("is_no_loan")] == 0.0


# ----------------------------------------------------- categorical encoding


def test_enum_encodings_cover_every_member():
    assert set(F.ENUM_ENCODINGS["loan_purpose"]) == {p.value for p in LoanPurpose}
    assert set(F.ENUM_ENCODINGS["financing_strategy"]) == {
        s.value for s in FinancingStrategy
    }
    assert set(F.ENUM_ENCODINGS["risk_appetite"]) == {a.value for a in RiskAppetite}


def test_lender_encoding_is_deterministic_regardless_of_catalogue_order():
    forward = F.build_lender_encoding(CATALOGUE)
    reversed_order = F.build_lender_encoding(list(reversed(CATALOGUE)))
    assert forward == reversed_order


def test_lender_encoding_covers_every_catalogue_lender():
    encoding = F.build_lender_encoding(CATALOGUE)
    assert set(encoding) == {p.lender for p in CATALOGUE}


def test_an_unseen_lender_is_a_handled_case_not_an_exception():
    """CONTEXT.md 17.2: an unseen category has a documented default."""
    F.set_lender_encoding({"Known Bank": 0})
    candidate = _candidates()[0]
    vector = _pair(candidate)
    assert vector[F.PAIR_FEATURE_COLUMNS.index("product_lender")] == F.UNSEEN_CATEGORY


def test_the_unseen_default_cannot_collide_with_a_real_category():
    encoding = F.build_lender_encoding(CATALOGUE)
    assert F.UNSEEN_CATEGORY not in encoding.values()
    for mapping in F.ENUM_ENCODINGS.values():
        assert F.UNSEEN_CATEGORY not in mapping.values()


def test_encoding_is_never_fitted_at_call_time():
    """Building features must not mutate the installed mapping."""
    before = F.get_lender_encoding()
    for candidate in _candidates():
        _pair(candidate)
    assert F.get_lender_encoding() == before


# ------------------------------------------------------------- the matrix


def test_matrix_rows_match_the_per_candidate_builder():
    customer, financial, portfolio, personal, requirement = _inputs()
    candidates = _candidates()
    matrix = F.build_pair_feature_matrix(
        customer,
        financial,
        portfolio,
        personal,
        requirement,
        candidates,
        PRODUCTS_BY_ID,
        RISK_PD,
    )
    assert matrix.shape == (len(candidates), len(F.PAIR_FEATURE_COLUMNS))
    for row, candidate in zip(matrix, candidates):
        assert np.array_equal(row, _pair(candidate))


def test_an_empty_candidate_list_returns_a_correctly_shaped_empty_matrix():
    customer, financial, portfolio, personal, requirement = _inputs()
    matrix = F.build_pair_feature_matrix(
        customer, financial, portfolio, personal, requirement, [], PRODUCTS_BY_ID, RISK_PD
    )
    assert matrix.shape == (0, len(F.PAIR_FEATURE_COLUMNS))


def test_the_matrix_contains_no_nan():
    customer, financial, portfolio, personal, requirement = _inputs()
    matrix = F.build_pair_feature_matrix(
        customer,
        financial,
        portfolio,
        personal,
        requirement,
        _candidates(),
        PRODUCTS_BY_ID,
        RISK_PD,
    )
    assert not np.isnan(matrix).any()


# ------------------------------------------------------------- the manifest


def test_manifest_reports_the_configured_feature_version():
    from app.config import settings

    assert F.feature_manifest()["feature_version"] == settings.FEATURE_VERSION


def test_manifest_columns_match_the_module_columns():
    manifest = F.feature_manifest()
    assert manifest["risk_feature_columns"] == list(F.RISK_FEATURE_COLUMNS)
    assert manifest["pair_feature_columns"] == list(F.PAIR_FEATURE_COLUMNS)


def test_manifest_carries_the_encoder_mappings():
    """Serving never fits an encoder, so the mapping must ship with the model."""
    manifest = F.feature_manifest()
    assert manifest["enum_encodings"]["loan_purpose"]
    assert manifest["lender_encoding"] == F.build_lender_encoding(CATALOGUE)


def test_a_matching_manifest_passes():
    F.assert_manifest_matches(F.feature_manifest())


def test_assert_manifest_raises_on_a_version_mismatch():
    manifest = F.feature_manifest()
    manifest["feature_version"] = "0.0.1-old"
    with pytest.raises(F.FeatureManifestMismatch) as excinfo:
        F.assert_manifest_matches(manifest)
    assert "FEATURE_VERSION mismatch" in str(excinfo.value)


def test_assert_manifest_raises_on_a_reordered_column_list():
    """Same columns, different order — the failure that silently misfeeds every value."""
    manifest = F.feature_manifest()
    columns = list(manifest["pair_feature_columns"])
    columns[0], columns[1] = columns[1], columns[0]
    manifest["pair_feature_columns"] = columns
    with pytest.raises(F.FeatureManifestMismatch) as excinfo:
        F.assert_manifest_matches(manifest)
    assert "DIFFERENT ORDER" in str(excinfo.value)


def test_assert_manifest_raises_on_a_missing_column():
    manifest = F.feature_manifest()
    manifest["pair_feature_columns"] = manifest["pair_feature_columns"][:-1]
    with pytest.raises(F.FeatureManifestMismatch):
        F.assert_manifest_matches(manifest)


def test_assert_manifest_raises_on_an_added_column():
    manifest = F.feature_manifest()
    manifest["risk_feature_columns"] = manifest["risk_feature_columns"] + ["invented"]
    with pytest.raises(F.FeatureManifestMismatch):
        F.assert_manifest_matches(manifest)


def test_assert_manifest_raises_on_a_changed_enum_encoding():
    manifest = F.feature_manifest()
    manifest["enum_encodings"]["loan_purpose"] = {"HOME": 99}
    with pytest.raises(F.FeatureManifestMismatch):
        F.assert_manifest_matches(manifest)


def test_manifest_never_truncates_to_the_shorter_list():
    """A mismatch is a startup failure, never a silent truncation."""
    manifest = F.feature_manifest()
    manifest["pair_feature_columns"] = manifest["pair_feature_columns"][:3]
    with pytest.raises(F.FeatureManifestMismatch):
        F.assert_manifest_matches(manifest)
    assert len(F.PAIR_FEATURE_COLUMNS) > 3


# ------------------------------------------------- one path, no model here


def test_this_module_imports_no_model():
    import inspect

    source = inspect.getsource(F)
    assert "xgboost" not in source
    assert "import shap" not in source
    assert "sklearn" not in source


def test_importing_features_touches_no_model_file():
    """Importing an ML module must never read the filesystem (AGENTS.md section 2)."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    probe = (
        "import json, sys\n"
        "import app.ml.features\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        "if m.split('.')[0] in ('pandas','sklearn','shap','xgboost'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_exactly_one_feature_assembly_path_exists():
    """
    Nothing under training/ may define its own feature assembly. A second path is the
    specific defect the shared-module rule exists to prevent.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in (root / "training").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "def build_pair_features" in text or "def build_risk_features" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"a second feature path exists in {offenders}"


def test_risk_pd_is_a_parameter_and_reaches_the_vector():
    """The module never calls a model; the PD is handed in as a number."""
    candidate = _candidates()[0]
    customer, financial, portfolio, personal, requirement = _inputs()
    index = F.PAIR_FEATURE_COLUMNS.index("risk_pd")
    for pd in (0.0, 0.25, 0.9):
        vector = F.build_pair_features(
            customer,
            financial,
            portfolio,
            personal,
            requirement,
            PRODUCTS_BY_ID.get(candidate.product_id),
            candidate,
            pd,
        )
        assert vector[index] == pd


def test_every_context_feature_group_is_represented():
    """CONTEXT.md 6.3 names seven groups; each must actually appear."""
    columns = set(F.PAIR_FEATURE_COLUMNS)
    for required in (
        "credit_score",  # customer financial
        "age",
        "liquidity_ratio",  # portfolio
        "purpose_affinity",  # personalization
        "requested_amount",  # requirement
        "product_annual_rate",  # product
        "emi_to_disposable_income",  # derived candidate
        "tenure_delta_vs_preferred",
        "amount_delta_vs_requested",
        "risk_pd",  # risk signal
    ):
        assert required in columns, required
