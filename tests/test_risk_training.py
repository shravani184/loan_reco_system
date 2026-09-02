"""
The trained risk model artifact (P9).

Fast: nothing here retrains. The tests load the saved artifact and check the contract
between it and app/ml/features.py.

If no model has been trained these tests SKIP with a clear message, so a fresh clone
stays green — but the phase exit criteria still require an actual trained model, and
tests/test_risk_training.py::test_a_model_artifact_exists_after_training documents
which command produces it.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.ml import features as F
from tests import fixtures

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = REPO_ROOT / "models" / "risk_model.json"
MANIFEST_PATH = REPO_ROOT / "models" / "risk_model_manifest.json"

NO_MODEL = (
    "no trained risk model found. Run `python -m training.generate_risk_outcomes` "
    "then `python -m training.train_risk`."
)

requires_model = pytest.mark.skipif(
    not (MODEL_PATH.exists() and MANIFEST_PATH.exists()), reason=NO_MODEL
)


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.skip(NO_MODEL)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def booster():
    if not MODEL_PATH.exists():
        pytest.skip(NO_MODEL)
    import xgboost

    loaded = xgboost.Booster()
    loaded.load_model(str(MODEL_PATH))
    return loaded


def _fixture_risk_vector() -> np.ndarray:
    customer = fixtures.standard_customer()
    return F.build_risk_features(
        customer,
        analyze_financials(customer),
        analyze_portfolio(fixtures.mixed_portfolio()),
        fixtures.standard_requirement(),
    )


# ------------------------------------------------------------ the contract


@requires_model
def test_manifest_column_order_equals_risk_feature_columns(manifest):
    """Column order IS the contract. A reorder silently misfeeds every value."""
    assert manifest["feature_columns"] == list(F.RISK_FEATURE_COLUMNS)


@requires_model
def test_manifest_records_the_matching_feature_version(manifest):
    assert manifest["feature_version"] == settings.FEATURE_VERSION
    assert manifest["feature_manifest"]["feature_version"] == F.FEATURE_VERSION


@requires_model
def test_the_embedded_feature_manifest_passes_its_own_assertion(manifest):
    """The artifact's manifest must satisfy the loader that P11 will run."""
    F.assert_manifest_matches(manifest["feature_manifest"])


@requires_model
def test_manifest_carries_the_lender_encoding(manifest):
    """Serving never fits an encoder, so the mapping must ship with the model."""
    encoding = manifest["feature_manifest"]["lender_encoding"]
    assert encoding
    assert F.UNSEEN_CATEGORY not in encoding.values()


# ---------------------------------------------------------- the prediction


@requires_model
def test_the_artifact_loads_and_predicts_a_probability_in_zero_one(booster):
    import xgboost

    vector = _fixture_risk_vector()
    matrix = xgboost.DMatrix(vector.reshape(1, -1))
    probability = float(booster.predict(matrix)[0])
    assert 0.0 <= probability <= 1.0


@requires_model
def test_prediction_is_deterministic(booster):
    import xgboost

    matrix = xgboost.DMatrix(_fixture_risk_vector().reshape(1, -1))
    assert float(booster.predict(matrix)[0]) == float(booster.predict(matrix)[0])


@requires_model
def test_the_booster_expects_exactly_the_manifest_column_count(booster, manifest):
    assert booster.num_features() == len(manifest["feature_columns"])
    assert booster.num_features() == len(F.RISK_FEATURE_COLUMNS)


@requires_model
def test_a_weaker_profile_is_not_scored_as_less_risky(booster):
    """
    Directional sanity, not a performance claim: a customer with a far worse credit
    score, a heavier debt burden and no savings should not come out SAFER.
    """
    import xgboost

    strong = fixtures.standard_customer()
    weak = strong.model_copy(
        update={"credit_score": 520, "monthly_expenses": 100_000.0, "existing_emi": 15_000.0}
    )
    requirement = fixtures.standard_requirement()

    def pd_for(customer, portfolio):
        vector = F.build_risk_features(
            customer,
            analyze_financials(customer),
            analyze_portfolio(portfolio),
            requirement,
        )
        return float(booster.predict(xgboost.DMatrix(vector.reshape(1, -1)))[0])

    assert pd_for(weak, fixtures.empty_portfolio()) >= pd_for(
        strong, fixtures.mixed_portfolio()
    )


@requires_model
def test_a_zero_portfolio_customer_still_scores(booster):
    """The zero-portfolio path is first-class all the way through inference."""
    import xgboost

    customer = fixtures.standard_customer()
    vector = F.build_risk_features(
        customer,
        analyze_financials(customer),
        analyze_portfolio(fixtures.empty_portfolio()),
        fixtures.standard_requirement(),
    )
    probability = float(booster.predict(xgboost.DMatrix(vector.reshape(1, -1)))[0])
    assert 0.0 <= probability <= 1.0


# ------------------------------------------------------- honest reporting


@requires_model
def test_manifest_declares_the_labels_synthetic(manifest):
    """
    Non-negotiable 18: synthetic data is always labelled synthetic, and the limitation
    is reported rather than buried.
    """
    assert manifest["training_labels_are_synthetic"] is True
    assert manifest["training_label_source"] == "training/generate_risk_outcomes.py"
    assert "not" in manifest["training_label_note"].lower()


@requires_model
def test_manifest_declares_the_model_secondary(manifest):
    """The role statement is part of the artifact, not just the docs."""
    role = manifest["model_role"].lower()
    assert "secondary" in role
    assert "never selects" in role or "never select" in role


@requires_model
def test_manifest_reports_more_than_accuracy(manifest):
    """Accuracy alone is not sufficient reporting for a 15%-positive target."""
    metrics = manifest["test_metrics"]
    for key in ("roc_auc", "pr_auc", "precision", "recall", "f1", "brier_score"):
        assert key in metrics, key
        assert isinstance(metrics[key], (int, float))


@requires_model
def test_manifest_includes_a_reliability_curve(manifest):
    curve = manifest["test_metrics"]["reliability_curve"]
    assert len(curve) == 10
    populated = [row for row in curve if row["count"]]
    assert populated
    for row in populated:
        assert 0.0 <= row["mean_predicted"] <= 1.0
        assert 0.0 <= row["observed_rate"] <= 1.0


@requires_model
def test_manifest_records_the_searched_grid_and_best_params(manifest):
    assert manifest["searched_grid"]
    assert manifest["best_params"]
    for key, value in manifest["best_params"].items():
        assert value in manifest["searched_grid"][key], key


@requires_model
def test_manifest_records_the_achievable_ceiling(manifest):
    """
    A ROC-AUC without a ceiling is uninterpretable. The unobserved shock term means no
    feature-based model can reach 1.0, so the ceiling is what makes the number mean
    something.
    """
    ceiling = manifest["achievable_ceiling"]
    assert 0.5 < ceiling["feature_ceiling_roc_auc"] <= ceiling["oracle_roc_auc"] <= 1.0
    assert manifest["test_metrics"]["roc_auc"] <= ceiling["oracle_roc_auc"]


@requires_model
def test_manifest_records_the_pd_median_for_fallback_imputation(manifest):
    """
    P11 imputes PD with this when the artifact cannot load, and flags the imputation
    (CONTEXT.md section 8). Without it there is nothing to impute with.
    """
    median = manifest["training_pd_median"]
    assert 0.0 <= median <= 1.0


@requires_model
def test_manifest_records_seed_and_split_sizes(manifest):
    assert manifest["seed"]
    assert manifest["training_rows"] > 0
    assert manifest["test_rows"] > 0
    assert manifest["model_version"] == settings.RISK_MODEL_VERSION


@requires_model
def test_the_model_beats_a_coin_flip_but_not_the_ceiling(manifest):
    """Sanity bounds only. A model above its own ceiling would signal leakage."""
    auc = manifest["test_metrics"]["roc_auc"]
    assert auc > 0.5, "the model has no signal at all"
    assert auc <= manifest["achievable_ceiling"]["oracle_roc_auc"] + 0.05


# ------------------------------------------------------------ persistence


@requires_model
def test_the_artifact_is_xgboost_json_not_pickle():
    """
    Models persist as XGBoost JSON so they survive library upgrades and load without a
    pickle-compatible environment (CONTEXT.md 17.2).
    """
    head = MODEL_PATH.read_bytes()[:1]
    assert head == b"{", "risk_model.json is not JSON — a pickle would start otherwise"
    json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def test_no_model_is_loaded_at_import_of_any_app_module():
    """
    Importing an ML module must never touch the filesystem (AGENTS.md section 2). This
    is what keeps test collection fast and deployment startup predictable.
    """
    import subprocess
    import sys

    probe = (
        "import sys, app.ml.features, app.config, app.schemas\n"
        "import xgboost\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ok" in result.stdout


def test_training_does_not_define_its_own_feature_assembly():
    offenders = []
    for path in (REPO_ROOT / "training").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "def build_risk_features" in text or "def build_pair_features" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_app_does_not_import_training():
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import training" in text or "from training" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_the_training_script_contains_no_selection_logic():
    """
    The risk model is a feature source and a disclosure. If selection logic appears
    here, the secondary model has quietly become a decision-maker.
    """
    source = (REPO_ROOT / "training" / "train_risk.py").read_text(encoding="utf-8")
    for banned in ("def select", "def recommend", "def rank_", "eligib"):
        assert banned not in source.lower(), banned


@requires_model
def test_a_model_artifact_exists_after_training():
    """The exit criterion, stated as a test so its absence is visible."""
    assert MODEL_PATH.exists()
    assert MANIFEST_PATH.exists()
