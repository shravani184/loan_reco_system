"""
The trained primary-recommender bundle (P10).

Fast: nothing here retrains. These tests check the contract between the saved bundle
and app/ml/features.py, and the properties the serving layer will depend on at P11.

Skips cleanly with a clear message when no artifact is present.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.core.candidates import generate_candidates
from app.core.diagnostics import diagnostic_utility_score
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.ml import features as F
from app.schemas.enums import EligibilityStatus
from tests import fixtures

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "models"
MODEL_PATH = MODEL_DIR / "loan_recommender.json"
CALIBRATION_PATH = MODEL_DIR / "loan_recommender_calibration.json"
ENCODERS_PATH = MODEL_DIR / "loan_recommender_encoders.json"
MANIFEST_PATH = MODEL_DIR / "loan_recommender_manifest.json"

NO_MODEL = (
    "no trained recommender bundle found. Run `python -m training.build_dataset`, "
    "`python -m training.train_risk`, then `python -m training.train_recommender`."
)

requires_bundle = pytest.mark.skipif(
    not all(
        path.exists()
        for path in (MODEL_PATH, CALIBRATION_PATH, ENCODERS_PATH, MANIFEST_PATH)
    ),
    reason=NO_MODEL,
)


def _read(path: Path):
    if not path.exists():
        pytest.skip(NO_MODEL)
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    return _read(MANIFEST_PATH)


@pytest.fixture(scope="module")
def calibration():
    return _read(CALIBRATION_PATH)


@pytest.fixture(scope="module")
def booster():
    if not MODEL_PATH.exists():
        pytest.skip(NO_MODEL)
    import xgboost

    loaded = xgboost.Booster()
    loaded.load_model(str(MODEL_PATH))
    return loaded


@pytest.fixture(scope="module")
def fixture_candidates():
    """A real candidate list from the mock catalogue — not a hand-built stub."""
    catalogue = fixtures.mock_catalogue()
    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    financial = analyze_financials(customer)
    portfolio = analyze_portfolio(fixtures.mixed_portfolio())
    eligible = {
        result.product_id
        for result in check_eligibility(customer, financial, requirement, catalogue)
        if result.status is EligibilityStatus.ELIGIBLE
    }
    candidates = generate_candidates(
        requirement,
        financial,
        portfolio,
        [p for p in catalogue if p.product_id in eligible],
    ).candidates
    return customer, financial, portfolio, requirement, catalogue, candidates


@pytest.fixture
def feature_matrix(fixture_candidates):
    customer, financial, portfolio, requirement, catalogue, candidates = (
        fixture_candidates
    )
    before = F.get_lender_encoding()
    F.set_lender_encoding(F.build_lender_encoding(catalogue))
    matrix = F.build_pair_feature_matrix(
        customer,
        financial,
        portfolio,
        fixtures.neutral_personalization(),
        requirement,
        candidates,
        {p.product_id: p for p in catalogue},
        0.1,
    )
    yield matrix, candidates
    F.set_lender_encoding(before)


def _apply_knots(margins, calibration) -> np.ndarray:
    """Exactly what serving does: numpy.interp over the exported knots."""
    return np.interp(
        np.asarray(margins, dtype=np.float64),
        np.asarray(calibration["knots_x"], dtype=np.float64),
        np.asarray(calibration["knots_y"], dtype=np.float64),
    )


# ------------------------------------------------------------ the contract


@requires_bundle
def test_manifest_column_order_equals_pair_feature_columns(manifest):
    """Column order IS the contract. A reorder silently misfeeds every value."""
    assert manifest["feature_columns"] == list(F.PAIR_FEATURE_COLUMNS)


@requires_bundle
def test_manifest_feature_version_matches(manifest):
    assert manifest["feature_version"] == settings.FEATURE_VERSION
    assert manifest["feature_manifest"]["feature_version"] == F.FEATURE_VERSION


@requires_bundle
def test_the_embedded_feature_manifest_passes_its_own_assertion(manifest):
    """This is what P11 will run at load; it must already pass."""
    F.assert_manifest_matches(manifest["feature_manifest"])


@requires_bundle
def test_the_booster_expects_the_manifest_column_count(booster, manifest):
    assert booster.num_features() == len(manifest["feature_columns"])
    assert booster.num_features() == len(F.PAIR_FEATURE_COLUMNS)


@requires_bundle
def test_encoders_are_saved_as_a_dict_mapping_not_a_pickle():
    """CONTEXT.md 17.2 — a saved dict, so an unseen category is a handled case."""
    encoders = _read(ENCODERS_PATH)
    assert isinstance(encoders["lender_encoding"], dict)
    assert isinstance(encoders["enum_encodings"], dict)
    assert encoders["unseen_category"] == F.UNSEEN_CATEGORY


@requires_bundle
def test_saved_encoders_match_the_manifest(manifest):
    encoders = _read(ENCODERS_PATH)
    assert encoders["enum_encodings"] == manifest["feature_manifest"]["enum_encodings"]
    assert encoders["lender_encoding"] == manifest["feature_manifest"]["lender_encoding"]


# ---------------------------------------------------------------- scoring


@requires_bundle
def test_the_bundle_produces_one_score_per_candidate(booster, feature_matrix):
    import xgboost

    matrix, candidates = feature_matrix
    scores = booster.predict(xgboost.DMatrix(matrix))
    assert len(scores) == len(candidates)
    assert np.isfinite(scores).all()


@requires_bundle
def test_scoring_is_deterministic(booster, feature_matrix):
    import xgboost

    matrix, _ = feature_matrix
    first = booster.predict(xgboost.DMatrix(matrix))
    second = booster.predict(xgboost.DMatrix(matrix))
    assert np.array_equal(first, second)


@requires_bundle
def test_an_empty_candidate_list_scores_to_nothing(booster):
    """The recommender handed an empty list returns an empty list."""
    import xgboost

    empty = np.empty((0, len(F.PAIR_FEATURE_COLUMNS)), dtype=np.float64)
    assert len(booster.predict(xgboost.DMatrix(empty))) == 0


@requires_bundle
def test_the_ranker_does_not_give_every_candidate_the_same_score(booster, feature_matrix):
    """A constant score would make the ordering meaningless and the walk arbitrary."""
    import xgboost

    matrix, _ = feature_matrix
    scores = booster.predict(xgboost.DMatrix(matrix))
    assert len(set(np.round(scores, 6).tolist())) > 1


# ------------------------------------------------------------ calibration


@requires_bundle
def test_calibrated_suitability_is_within_zero_one(booster, feature_matrix, calibration):
    import xgboost

    matrix, _ = feature_matrix
    margins = booster.predict(xgboost.DMatrix(matrix))
    suitability = _apply_knots(margins, calibration)
    assert suitability.min() >= 0.0
    assert suitability.max() <= 1.0


@requires_bundle
def test_calibration_is_monotone(calibration):
    """
    A higher raw margin never yields a lower suitability. Isotonic regression
    guarantees it by construction; this asserts the EXPORTED knots preserved it.
    """
    knots_y = calibration["knots_y"]
    assert knots_y == sorted(knots_y)


@requires_bundle
def test_calibration_is_monotone_over_a_dense_sweep(calibration):
    """Monotone knots are necessary but the interpolation is what serving runs."""
    low = min(calibration["knots_x"]) - 5.0
    high = max(calibration["knots_x"]) + 5.0
    sweep = np.linspace(low, high, 2000)
    suitability = _apply_knots(sweep, calibration)
    assert np.all(np.diff(suitability) >= -1e-12)


@requires_bundle
def test_calibration_clips_outside_the_fitted_range(calibration):
    """
    numpy.interp clamps to the end knots. A margin far outside the fitted range must
    produce a valid suitability, not an extrapolated one outside [0,1].
    """
    extreme = _apply_knots([-1e6, 1e6], calibration)
    assert 0.0 <= extreme[0] <= 1.0
    assert 0.0 <= extreme[1] <= 1.0


@requires_bundle
def test_exported_knots_reproduced_the_fitted_estimator(calibration):
    """
    Asserted during training; recorded here so a future export cannot regress it
    silently. Serving disagreeing with training about every suitability score is the
    failure this prevents.
    """
    assert calibration["knot_reproduction_max_diff"] <= 1e-9


@requires_bundle
def test_calibration_is_applied_with_numpy_interp_not_sklearn(calibration):
    assert calibration["applied_with"] == "numpy.interp"
    assert "isotonic" in calibration["method"].lower()
    assert calibration["target"] == "P(relevance >= 2)"


@requires_bundle
def test_calibration_quality_is_reported(manifest):
    quality = manifest["calibration_quality"]
    assert 0.0 <= quality["brier_score"] <= 1.0
    populated = [row for row in quality["reliability_curve"] if row["count"]]
    assert populated


# ------------------------------------------------------- honest reporting


@requires_bundle
def test_manifest_declares_relevance_labels_synthetic(manifest):
    assert manifest["relevance_labels_are_synthetic"] is True
    assert manifest["relevance_label_source"] == "training/labeling.py"
    note = manifest["reporting_note"].lower()
    assert "not real recommendation quality" in note
    assert "share ancestry" in note


@requires_bundle
def test_manifest_declares_the_model_primary(manifest):
    role = manifest["model_role"].lower()
    assert "primary" in role
    assert "reorder" in role


@requires_bundle
def test_no_classification_accuracy_is_reported_for_the_ranker(manifest):
    """
    Accuracy is not a meaningful metric for a ranker and is not reported for it
    (AGENTS.md section 6 rule 7).
    """
    assert "accuracy" not in manifest["test_metrics"]
    for baseline in manifest["baselines"].values():
        assert "accuracy" not in baseline


@requires_bundle
def test_every_required_ranking_metric_is_reported(manifest):
    for metric in (
        "ndcg@1",
        "ndcg@3",
        "ndcg@5",
        "precision@1",
        "precision@3",
        "recall@5",
        "map@5",
        "mrr",
        "kendall_tau",
    ):
        assert metric in manifest["test_metrics"], metric


@requires_bundle
def test_all_three_mandatory_baselines_are_reported(manifest):
    """Reported side by side, always — including when the model loses."""
    assert set(manifest["baselines"]) == {
        "random",
        "cheapest_emi",
        "diagnostic_utility",
    }
    for baseline in manifest["baselines"].values():
        assert baseline["ndcg@5"] is not None


@requires_bundle
def test_the_model_is_compared_against_the_diagnostic_baseline(manifest):
    """The comparison is recorded whichever way it went."""
    assert isinstance(manifest["beats_diagnostic_utility_on_ndcg@5"], bool)


@requires_bundle
def test_the_model_does_not_exceed_the_policy_oracle(manifest):
    """
    The oracle is the labeling policy's own score. A model ABOVE it would mean the
    labels leaked into the features.
    """
    oracle = manifest["policy_oracle_ceiling"]["ndcg@5"]
    assert manifest["test_metrics"]["ndcg@5"] <= oracle + 1e-6


@requires_bundle
def test_the_model_beats_random(manifest):
    """The floor. Below this the model is not worth deploying at all."""
    assert (
        manifest["test_metrics"]["ndcg@5"] > manifest["baselines"]["random"]["ndcg@5"]
    )


@requires_bundle
def test_cross_validation_was_group_aware(manifest):
    """Splitting a customer's candidates across folds leaks a group into its own fold."""
    assert manifest["cv_group_aware"] is True
    assert manifest["searched_grid"]
    assert manifest["best_params"] in manifest["searched_grid"]


@requires_bundle
def test_calibration_groups_were_held_out_from_the_fit(manifest):
    """Calibrating on training margins produces a confident, wrong curve."""
    assert manifest["calibration_groups"] > 0
    assert manifest["fit_groups"] > 0
    assert manifest["test_groups"] > 0


@requires_bundle
def test_threshold_is_a_recommendation_not_a_silent_config_change(manifest):
    """
    Moving SUITABILITY_ACCEPTANCE_THRESHOLD is the easiest way to falsify the product,
    so training recommends and a human decides.
    """
    recommendation = manifest["threshold_recommendation"]
    assert 0.0 < recommendation["recommended_threshold"] < 1.0
    assert "RECOMMENDATION ONLY" in recommendation["note"]
    assert (
        recommendation["current_config_value"]
        == settings.SUITABILITY_ACCEPTANCE_THRESHOLD
    )


# -------------------------------------------------------- exactly two models


def test_exactly_two_model_artifacts_exist():
    """
    Two models and no more: the primary recommender and the secondary risk classifier
    (CONTEXT.md non-negotiable 2). The calibrator is a TRANSFORM, the encoders are a
    saved mapping, and manifests are metadata — none of them is a model.
    """
    if not MODEL_PATH.exists():
        pytest.skip(NO_MODEL)
    boosters = sorted(
        path.name
        for path in MODEL_DIR.glob("*.json")
        if not path.name.endswith(("_manifest.json", "_calibration.json", "_encoders.json"))
    )
    assert boosters == ["loan_recommender.json", "risk_model.json"], boosters


@requires_bundle
def test_the_recommender_artifact_is_xgboost_json_not_pickle():
    assert MODEL_PATH.read_bytes()[:1] == b"{"
    json.loads(MODEL_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------- the diagnostic baseline


def test_diagnostic_utility_is_deterministic_and_orders_candidates(fixture_candidates):
    """
    The fallback ranking must be usable when the ML model is unavailable, so it has to
    produce a real order rather than a constant.
    """
    _, financial, portfolio, _, _, candidates = fixture_candidates
    scores = [
        diagnostic_utility_score(financial, portfolio, candidate, 0.1)
        for candidate in candidates
    ]
    again = [
        diagnostic_utility_score(financial, portfolio, candidate, 0.1)
        for candidate in candidates
    ]
    assert scores == again
    assert len(set(round(score, 9) for score in scores)) > 1


def test_diagnostic_utility_prefers_lower_risk(fixture_candidates):
    _, financial, portfolio, _, _, candidates = fixture_candidates
    candidate = candidates[0]
    safe = diagnostic_utility_score(financial, portfolio, candidate, 0.02)
    risky = diagnostic_utility_score(financial, portfolio, candidate, 0.90)
    assert safe > risky


def test_diagnostic_utility_penalises_a_bigger_portfolio_hit(fixture_candidates):
    _, financial, portfolio, _, _, candidates = fixture_candidates
    heavy = min(candidates, key=lambda c: c.remaining_portfolio_value)
    light = max(candidates, key=lambda c: c.remaining_portfolio_value)
    from app.core.diagnostics import portfolio_impact_component

    assert portfolio_impact_component(portfolio, heavy) >= portfolio_impact_component(
        portfolio, light
    )


ALLOWED_DIAGNOSTIC_CONSUMERS = {
    # P11's fallback path. The ONLY place the diagnostic score may ORDER anything, and
    # only when the recommender artifact is unavailable. An AST test in
    # test_ml_inference.py pins the call to _fallback_ranking.
    "app/ml/recommender.py",
    # P12's orchestrator, for RECORDING the winner's advisory score in the trace so the
    # ML and deterministic views can be compared offline (CONTEXT.md section 4). It
    # orders nothing: two AST tests in test_recommendation.py assert the call happens
    # only in recommend(), and that no identifier containing "diagnostic" appears
    # inside any sorted/max/min expression in that module.
    "app/core/recommendation.py",
}


def test_only_the_fallback_path_imports_the_diagnostic_score():
    """
    The diagnostic score may produce an ordering ONLY in fallback, and only with
    recommendation_source = DETERMINISTIC_FALLBACK stamped on the result
    (CONTEXT.md section 4). Any other module importing it is a route by which a
    deterministic score could reorder an ML recommendation.

    Updated at P11: app/ml/recommender.py became a legitimate consumer when the
    fallback was built. Before that, no module imported it at all.
    """
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path.name == "diagnostics.py":
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in ALLOWED_DIAGNOSTIC_CONSUMERS:
            continue
        text = path.read_text(encoding="utf-8")
        # An IMPORT, not a mention. DecisionTrace declares a
        # winner_diagnostic_utility_score field, which is the score being RECORDED for
        # audit — exactly what the architecture asks for — not a module calling it.
        if "core.diagnostics" in text or "from app.core import diagnostics" in text:
            offenders.append(relative)
    assert offenders == [], (
        f"{offenders} import the diagnostic score. It may never reorder an ML "
        "recommendation during normal operation."
    )


def test_the_recommender_calls_the_diagnostic_score_only_inside_its_fallback():
    """
    Importing it is permitted; calling it on the normal path is not. This checks the
    AST, so the call must genuinely live inside the fallback helper.
    """
    import ast

    tree = ast.parse(
        (REPO_ROOT / "app" / "ml" / "recommender.py").read_text(encoding="utf-8")
    )
    callers = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "diagnostic_utility_score"
            ):
                callers.add(node.name)
    assert callers == {"_fallback_ranking"}, (
        f"diagnostic_utility_score is called from {callers}; it may only order "
        "candidates on the fallback path."
    )


def test_the_trace_schema_records_the_diagnostic_score_as_advisory():
    """
    The score IS recorded in the trace beside the ML score, so the two can be compared
    offline. Recording it is required; letting it decide anything is forbidden.
    """
    from app.schemas import DecisionTrace

    field = DecisionTrace.model_fields["winner_diagnostic_utility_score"]
    # Nullable and defaulted: a trace is valid without it, so nothing downstream can
    # come to depend on it being present.
    assert field.default is None
    assert field.is_required() is False
    source = (REPO_ROOT / "app" / "schemas" / "recommendation.py").read_text(
        encoding="utf-8"
    )
    assert "Advisory only" in source
