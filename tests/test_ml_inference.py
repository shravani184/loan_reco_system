"""
ML inference layer and both fallback paths (P11).

MODULE STATE IS GLOBAL, so every test resets it before and after. A test that left a
loaded model behind would make the next test pass for the wrong reason.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.core.candidates import generate_candidates
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.ml import features as F
from app.ml import recommender, risk
from app.schemas.enums import (
    EligibilityStatus,
    RecommendationSource,
    RiskClass,
)
from tests import fixtures

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "models"

NO_MODEL = (
    "no trained artifacts. Run `python -m training.build_dataset`, "
    "`python -m training.train_risk`, then `python -m training.train_recommender`."
)
requires_models = pytest.mark.skipif(
    not (
        (MODEL_DIR / "risk_model.json").exists()
        and (MODEL_DIR / "loan_recommender.json").exists()
    ),
    reason=NO_MODEL,
)


@pytest.fixture(autouse=True)
def clean_model_state():
    """No test may inherit or leak a loaded model."""
    risk.reset_state()
    recommender.reset_state()
    encoding = F.get_lender_encoding()
    yield
    risk.reset_state()
    recommender.reset_state()
    F.set_lender_encoding(encoding)


@pytest.fixture
def pipeline_inputs():
    customer = fixtures.standard_customer()
    requirement = fixtures.standard_requirement()
    catalogue = fixtures.mock_catalogue()
    financial = analyze_financials(customer)
    portfolio = analyze_portfolio(fixtures.mixed_portfolio())
    eligible = {
        result.product_id
        for result in check_eligibility(customer, financial, requirement, catalogue)
        if result.status is EligibilityStatus.ELIGIBLE
    }
    candidates = [
        candidate
        for candidate in generate_candidates(
            requirement,
            financial,
            portfolio,
            [p for p in catalogue if p.product_id in eligible],
        ).candidates
        if candidate.feasible
    ]
    return {
        "customer": customer,
        "financial": financial,
        "portfolio": portfolio,
        "personalization": fixtures.neutral_personalization(),
        "requirement": requirement,
        "products_by_id": {p.product_id: p for p in catalogue},
        "candidates": candidates,
    }


def _score(pipeline_inputs, risk_pd=0.1):
    return recommender.score_candidates(
        pipeline_inputs["customer"],
        pipeline_inputs["financial"],
        pipeline_inputs["portfolio"],
        pipeline_inputs["personalization"],
        pipeline_inputs["requirement"],
        pipeline_inputs["products_by_id"],
        pipeline_inputs["candidates"],
        risk_pd,
    )


# ============================================== no loading at import time


def test_importing_the_ml_modules_loads_no_model_file():
    """
    Importing an ML module must never touch the filesystem (AGENTS.md section 2).
    Checked in a SUBPROCESS so a model loaded by an earlier test cannot make this
    pass for the wrong reason.
    """
    probe = (
        "import json\n"
        "import app.ml.risk as r, app.ml.recommender as c\n"
        "print(json.dumps({\n"
        "  'risk_booster': r._state.booster is None,\n"
        "  'risk_attempted': r._state.load_attempted,\n"
        "  'rec_booster': c._state.booster is None,\n"
        "  'rec_attempted': c._state.load_attempted,\n"
        "  'rec_knots': c._state.knots_x is None,\n"
        "}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(result.stdout.strip().splitlines()[-1])
    assert state == {
        "risk_booster": True,
        "risk_attempted": False,
        "rec_booster": True,
        "rec_attempted": False,
        "rec_knots": True,
    }


def test_state_is_empty_immediately_after_reset():
    assert risk._state.booster is None
    assert risk._state.load_attempted is False
    assert recommender._state.booster is None
    assert recommender._state.load_attempted is False


@requires_models
def test_load_models_is_idempotent():
    """The lifespan handler and a lazy accessor must not load twice."""
    recommender.load_models()
    first = recommender._state.booster
    recommender.load_models()
    assert recommender._state.booster is first

    risk.load_models()
    first_risk = risk._state.booster
    risk.load_models()
    assert risk._state.booster is first_risk


@requires_models
def test_the_lazy_accessor_loads_on_first_call():
    assert recommender._state.load_attempted is False
    assert recommender.get_recommender_model() is not None
    assert recommender._state.load_attempted is True


# ============================================================ scoring


@requires_models
def test_one_scored_candidate_per_input_candidate(pipeline_inputs):
    result = _score(pipeline_inputs)
    assert len(result.scored_candidates) == len(pipeline_inputs["candidates"])


@requires_models
def test_candidates_come_back_in_descending_suitability(pipeline_inputs):
    scores = [item.suitability for item in _score(pipeline_inputs).scored_candidates]
    assert scores == sorted(scores, reverse=True)


@requires_models
def test_ranks_are_one_to_n_contiguous(pipeline_inputs):
    ranks = [item.rank for item in _score(pipeline_inputs).scored_candidates]
    assert ranks == list(range(1, len(ranks) + 1))


@requires_models
def test_suitability_is_within_zero_one(pipeline_inputs):
    for item in _score(pipeline_inputs).scored_candidates:
        assert 0.0 <= item.suitability <= 1.0


@requires_models
def test_both_the_raw_margin_and_the_calibrated_score_are_carried(pipeline_inputs):
    """Only the calibrated value is thresholded; the margin is kept for audit."""
    for item in _score(pipeline_inputs).scored_candidates:
        assert item.raw_ranker_margin is not None
        assert item.suitability is not None


@requires_models
def test_the_source_is_the_ml_ranker_when_the_model_loads(pipeline_inputs):
    assert _score(pipeline_inputs).source is RecommendationSource.ML_RANKER


@requires_models
def test_every_input_candidate_survives_scoring(pipeline_inputs):
    """The recommender never filters. Every candidate in must come back out."""
    result = _score(pipeline_inputs)
    assert {item.candidate.candidate_id for item in result.scored_candidates} == {
        candidate.candidate_id for candidate in pipeline_inputs["candidates"]
    }


@requires_models
def test_scoring_is_deterministic(pipeline_inputs):
    first = _score(pipeline_inputs)
    second = _score(pipeline_inputs)
    assert [i.candidate.candidate_id for i in first.scored_candidates] == [
        i.candidate.candidate_id for i in second.scored_candidates
    ]
    assert [i.suitability for i in first.scored_candidates] == [
        i.suitability for i in second.scored_candidates
    ]


@requires_models
def test_the_recommender_never_mutates_a_candidates_financial_fields(pipeline_inputs):
    """
    Every rupee figure was computed deterministically by P5. The ML layer may not
    produce or alter one (CONTEXT.md non-negotiable 6).
    """
    before = [candidate.model_dump() for candidate in pipeline_inputs["candidates"]]
    result = _score(pipeline_inputs)
    after = [candidate.model_dump() for candidate in pipeline_inputs["candidates"]]
    assert before == after
    returned = {item.candidate.candidate_id: item.candidate for item in result.scored_candidates}
    for original in pipeline_inputs["candidates"]:
        assert returned[original.candidate_id].model_dump() == original.model_dump()


@requires_models
def test_the_no_loan_candidate_is_scored_like_any_other(pipeline_inputs):
    """It has no product, lender or tenure, and must still receive a suitability."""
    from app.schemas.enums import FinancingStrategy

    result = _score(pipeline_inputs)
    no_loan = [
        item
        for item in result.scored_candidates
        if item.candidate.strategy is FinancingStrategy.LIQUIDATE_100
    ]
    assert len(no_loan) == 1
    assert 0.0 <= no_loan[0].suitability <= 1.0


def test_an_empty_candidate_list_returns_an_empty_list(pipeline_inputs):
    pipeline_inputs["candidates"] = []
    result = _score(pipeline_inputs)
    assert result.scored_candidates == []
    assert result.source in set(RecommendationSource)


# ======================================================== calibration


@requires_models
def test_calibration_is_applied_with_numpy_interp_over_the_saved_knots():
    recommender.load_models()
    calibration = json.loads(
        (MODEL_DIR / "loan_recommender_calibration.json").read_text(encoding="utf-8")
    )
    margins = np.linspace(-10.0, 10.0, 101)
    expected = np.interp(
        margins,
        np.asarray(calibration["knots_x"]),
        np.asarray(calibration["knots_y"]),
    )
    assert np.allclose(recommender.calibrate(margins), expected)


@requires_models
def test_calibration_is_monotone_across_a_dense_sweep():
    recommender.load_models()
    suitability = recommender.calibrate(np.linspace(-50.0, 50.0, 5000))
    assert np.all(np.diff(suitability) >= -1e-12)


@requires_models
def test_calibration_clamps_outside_the_fitted_range():
    recommender.load_models()
    extreme = recommender.calibrate(np.array([-1e9, 1e9]))
    assert 0.0 <= extreme[0] <= 1.0
    assert 0.0 <= extreme[1] <= 1.0


def test_calibrating_without_loaded_knots_raises_rather_than_guessing():
    with pytest.raises(RuntimeError):
        recommender.calibrate(np.array([0.0]))


def test_serving_calibration_imports_no_scikit_learn():
    """The whole point of exporting knots (CONTEXT.md 17.2)."""
    import inspect

    source = inspect.getsource(recommender)
    assert "sklearn" not in source
    assert "IsotonicRegression" not in source


# ================================================ the manifest contract


@requires_models
def test_a_feature_version_mismatch_raises_at_load_naming_both_versions(
    tmp_path, monkeypatch
):
    """
    A mismatch is a hard, clearly-messaged failure — never a warning, never a silent
    reorder or truncation (AGENTS.md section 2). It is NOT degraded into a fallback:
    a model whose columns disagree with this code produces confident nonsense, which
    is worse than no model.
    """
    manifest = json.loads(
        (MODEL_DIR / "loan_recommender_manifest.json").read_text(encoding="utf-8")
    )
    manifest["feature_manifest"]["feature_version"] = "0.0.1-stale"

    model_copy = tmp_path / "loan_recommender.json"
    model_copy.write_bytes((MODEL_DIR / "loan_recommender.json").read_bytes())
    (tmp_path / "loan_recommender_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "loan_recommender_calibration.json").write_bytes(
        (MODEL_DIR / "loan_recommender_calibration.json").read_bytes()
    )

    monkeypatch.setattr(settings, "RECOMMENDER_MODEL_PATH", str(model_copy))
    monkeypatch.setattr(
        settings,
        "CALIBRATION_KNOTS_PATH",
        str(tmp_path / "loan_recommender_calibration.json"),
    )

    with pytest.raises(F.FeatureManifestMismatch) as excinfo:
        recommender.load_models()
    message = str(excinfo.value)
    assert "0.0.1-stale" in message
    assert settings.FEATURE_VERSION in message


@requires_models
def test_a_reordered_column_list_raises_at_load(tmp_path, monkeypatch):
    manifest = json.loads(
        (MODEL_DIR / "loan_recommender_manifest.json").read_text(encoding="utf-8")
    )
    columns = list(manifest["feature_manifest"]["pair_feature_columns"])
    columns[0], columns[1] = columns[1], columns[0]
    manifest["feature_manifest"]["pair_feature_columns"] = columns

    model_copy = tmp_path / "loan_recommender.json"
    model_copy.write_bytes((MODEL_DIR / "loan_recommender.json").read_bytes())
    (tmp_path / "loan_recommender_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "loan_recommender_calibration.json").write_bytes(
        (MODEL_DIR / "loan_recommender_calibration.json").read_bytes()
    )
    monkeypatch.setattr(settings, "RECOMMENDER_MODEL_PATH", str(model_copy))
    monkeypatch.setattr(
        settings,
        "CALIBRATION_KNOTS_PATH",
        str(tmp_path / "loan_recommender_calibration.json"),
    )

    with pytest.raises(F.FeatureManifestMismatch) as excinfo:
        recommender.load_models()
    assert "DIFFERENT ORDER" in str(excinfo.value)


@requires_models
def test_loading_installs_the_saved_lender_encoding(monkeypatch):
    """Serving never fits an encoder; the mapping arrives with the model."""
    F.set_lender_encoding({})
    recommender.load_models()
    manifest = recommender._state.manifest["feature_manifest"]
    assert F.get_lender_encoding() == manifest["lender_encoding"]
    assert F.get_lender_encoding()


@requires_models
def test_non_monotone_calibration_knots_are_rejected(tmp_path, monkeypatch):
    """A non-monotone calibrator would let a better margin score worse."""
    calibration = json.loads(
        (MODEL_DIR / "loan_recommender_calibration.json").read_text(encoding="utf-8")
    )
    calibration["knots_y"] = list(reversed(calibration["knots_y"]))
    broken = tmp_path / "loan_recommender_calibration.json"
    broken.write_text(json.dumps(calibration), encoding="utf-8")
    monkeypatch.setattr(settings, "CALIBRATION_KNOTS_PATH", str(broken))

    recommender.load_models()
    # Rejected as a degradation, not a crash: the service still answers.
    assert recommender.is_degraded() is True
    assert recommender.get_recommender_model() is None


# ============================================ fallback: the recommender


@pytest.fixture
def missing_recommender(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "RECOMMENDER_MODEL_PATH", str(tmp_path / "absent.json")
    )
    monkeypatch.setattr(
        settings, "CALIBRATION_KNOTS_PATH", str(tmp_path / "absent_calibration.json")
    )


def test_a_missing_recommender_activates_the_deterministic_fallback(
    missing_recommender, pipeline_inputs
):
    result = _score(pipeline_inputs)
    assert result.source is RecommendationSource.DETERMINISTIC_FALLBACK
    assert recommender.is_degraded() is True


def test_the_fallback_still_ranks_every_candidate_one_to_n(
    missing_recommender, pipeline_inputs
):
    result = _score(pipeline_inputs)
    assert len(result.scored_candidates) == len(pipeline_inputs["candidates"])
    ranks = [item.rank for item in result.scored_candidates]
    assert ranks == list(range(1, len(ranks) + 1))


def test_the_fallback_reports_no_suitability(missing_recommender, pipeline_inputs):
    """
    Never a rescaled diagnostic score in a field named for ML output
    (AGENTS.md section 7.3). The Recommendation schema also rejects it downstream.
    """
    for item in _score(pipeline_inputs).scored_candidates:
        assert item.suitability is None
        assert item.raw_ranker_margin is None


def test_the_fallback_order_matches_the_diagnostic_utility_score(
    missing_recommender, pipeline_inputs
):
    """The fallback ordering IS the diagnostic ranking, not an arbitrary one."""
    from app.core.diagnostics import diagnostic_utility_score

    result = _score(pipeline_inputs, risk_pd=0.1)
    scores = [
        diagnostic_utility_score(
            pipeline_inputs["financial"],
            pipeline_inputs["portfolio"],
            item.candidate,
            0.1,
        )
        for item in result.scored_candidates
    ]
    assert scores == sorted(scores, reverse=True)


def test_a_corrupt_recommender_artifact_falls_back_rather_than_crashing(
    tmp_path, monkeypatch, pipeline_inputs
):
    """A corrupt artifact is logged and handled — never a 500 on the primary path."""
    broken = tmp_path / "loan_recommender.json"
    broken.write_text("this is not json", encoding="utf-8")
    (tmp_path / "loan_recommender_manifest.json").write_text(
        "also not json", encoding="utf-8"
    )
    monkeypatch.setattr(settings, "RECOMMENDER_MODEL_PATH", str(broken))
    monkeypatch.setattr(
        settings, "CALIBRATION_KNOTS_PATH", str(tmp_path / "missing.json")
    )

    result = _score(pipeline_inputs)
    assert result.source is RecommendationSource.DETERMINISTIC_FALLBACK
    assert recommender._state.failure is not None


def test_the_fallback_records_why_it_degraded(missing_recommender, pipeline_inputs):
    """A degradation with no recorded cause cannot be diagnosed later."""
    _score(pipeline_inputs)
    assert recommender._state.failure
    assert "FileNotFoundError" in recommender._state.failure


def test_the_fallback_does_not_mutate_candidates(missing_recommender, pipeline_inputs):
    before = [candidate.model_dump() for candidate in pipeline_inputs["candidates"]]
    _score(pipeline_inputs)
    assert [c.model_dump() for c in pipeline_inputs["candidates"]] == before


# ================================================== fallback: the risk model


@pytest.fixture
def missing_risk_model(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RISK_MODEL_PATH", str(tmp_path / "absent.json"))


def test_a_missing_risk_model_imputes_the_pd_and_flags_it(
    missing_risk_model, pipeline_inputs
):
    prediction = risk.predict_risk(
        pipeline_inputs["customer"],
        pipeline_inputs["financial"],
        pipeline_inputs["portfolio"],
        pipeline_inputs["requirement"],
    )
    assert prediction.imputed is True
    assert 0.0 <= prediction.probability_of_default <= 1.0
    assert prediction.risk_class in set(RiskClass)
    assert risk.is_degraded() is True


def test_the_imputed_pd_is_the_recorded_training_median_when_available():
    """P9 recorded it precisely so this path has a real value, not an invented one."""
    if not (MODEL_DIR / "risk_model_manifest.json").exists():
        pytest.skip(NO_MODEL)
    manifest = json.loads(
        (MODEL_DIR / "risk_model_manifest.json").read_text(encoding="utf-8")
    )
    risk.load_models()
    assert risk.imputed_pd() == pytest.approx(manifest["training_pd_median"])


def test_the_last_resort_pd_is_not_optimistic():
    """
    With no manifest at all there is no median to impute. Failing towards "no risk"
    would be the dangerous direction.
    """
    assert risk.LAST_RESORT_PD >= 0.5


def test_the_pipeline_continues_when_the_risk_model_is_missing(
    missing_risk_model, pipeline_inputs
):
    """A degraded secondary model must not stop the primary path."""
    prediction = risk.predict_risk(
        pipeline_inputs["customer"],
        pipeline_inputs["financial"],
        pipeline_inputs["portfolio"],
        pipeline_inputs["requirement"],
    )
    result = _score(pipeline_inputs, risk_pd=prediction.probability_of_default)
    assert len(result.scored_candidates) == len(pipeline_inputs["candidates"])


@requires_models
def test_a_loaded_risk_model_is_not_flagged_as_imputed(pipeline_inputs):
    prediction = risk.predict_risk(
        pipeline_inputs["customer"],
        pipeline_inputs["financial"],
        pipeline_inputs["portfolio"],
        pipeline_inputs["requirement"],
    )
    assert prediction.imputed is False
    assert risk.is_degraded() is False


# ---------------------------------------------------------- risk banding


@pytest.mark.parametrize(
    "probability,expected",
    [
        (0.0, RiskClass.LOW),
        (0.05, RiskClass.LOW),
        (0.15, RiskClass.MEDIUM),
        (0.30, RiskClass.MEDIUM),
        (0.35, RiskClass.HIGH),
        (0.99, RiskClass.HIGH),
    ],
)
def test_risk_bands_follow_the_configured_ladder(probability, expected):
    assert risk.risk_class_for(probability) is expected


def test_low_is_the_floor_and_has_no_configured_threshold():
    assert RiskClass.LOW not in settings.RISK_CLASS_MIN_PD


def test_risk_bands_are_ordered():
    assert (
        settings.RISK_CLASS_MIN_PD[RiskClass.HIGH]
        > settings.RISK_CLASS_MIN_PD[RiskClass.MEDIUM]
    )


# ------------------------------------------------- the module boundaries


def _defined_names(module) -> set[str]:
    """
    Identifiers DEFINED by a module, from its AST. Not a text scan — a module's own
    prose about what it does not do must neither satisfy nor break these checks.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def test_the_risk_module_defines_no_selection_identifier():
    """Its output is a feature and a disclosure, never a decision."""
    names = _defined_names(risk)
    for banned in ("select", "recommend", "rank", "eligib", "guardrail"):
        offenders = [name for name in names if banned in name.lower()]
        assert offenders == [], (banned, offenders)


def test_the_risk_module_imports_nothing_that_could_decide():
    """
    A structural check: the risk model may not reach eligibility, guardrails or the
    recommender, because a feature source that can see them can start gating on them.
    """
    import inspect

    source = inspect.getsource(risk)
    for banned in (
        "app.core.eligibility",
        "app.core.guardrails",
        "app.ml.recommender",
        "app.core.candidates",
    ):
        assert f"import {banned}" not in source
        assert f"from {banned}" not in source


def test_the_recommender_never_recomputes_money():
    """No EMI formula, no interest arithmetic in the ML layer."""
    import inspect

    source = inspect.getsource(recommender)
    assert "def emi(" not in source
    assert "/ 12 / 100" not in source


def test_no_training_module_is_imported_by_the_inference_layer():
    for module in (risk, recommender):
        import inspect

        source = inspect.getsource(module)
        assert "import training" not in source
        assert "from training" not in source
