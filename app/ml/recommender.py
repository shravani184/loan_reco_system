"""
Primary recommender inference (P11).

THIS PRODUCES THE ORDERING THAT IS THE RECOMMENDATION. Only this module may order
candidates during normal operation (AGENTS.md section 2, authority rule).

WHAT IT MUST NOT DO:
  - filter, reject, or drop a candidate. It receives candidates that already passed
    eligibility and feasibility, and it scores ALL of them. Handed an empty list it
    returns an empty list (AGENTS.md section 6 rule 2).
  - re-check eligibility. That was decided before it ran and is not its business.
  - compute any rupee figure. Every money value on a candidate was computed
    deterministically by P5 and is passed through untouched.

MODEL LOADING RULE. Nothing is loaded at import; importing this module must not touch
the filesystem. Use load_models() (called once by the API lifespan handler) and
get_recommender_model() (lazy).

CALIBRATION. The booster emits an unbounded relative margin. Suitability is that
margin passed through the isotonic knots exported at P10, applied with numpy.interp —
no scikit-learn at serving. ONLY the calibrated value is ever compared against
SUITABILITY_ACCEPTANCE_THRESHOLD; the raw margin is carried for audit
(CONTEXT.md 6.4).

FALLBACK. A missing or corrupt artifact is logged with its path and the exception,
then candidates are ordered by app/core/diagnostics.py's diagnostic_utility_score and
the result is stamped DETERMINISTIC_FALLBACK. In that mode suitability is None —
never a rescaled utility value in a field named for ML output (AGENTS.md section 7.3).
This is the ONLY code path on which the diagnostic score may produce an ordering.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.config import settings
from app.core.diagnostics import diagnostic_utility_score
from app.ml.features import (
    assert_manifest_matches,
    build_pair_feature_matrix,
    set_lender_encoding,
)
from app.schemas import (
    Candidate,
    CustomerProfile,
    FinancialMetrics,
    LoanProduct,
    LoanRequirement,
    PersonalizationContext,
    PortfolioMetrics,
    ScoredCandidate,
    ScoringResult,
)
from app.schemas.enums import RecommendationSource

logger = logging.getLogger(__name__)


@dataclass
class _RecommenderState:
    """Module-level state. Empty until load_models() or the first lazy access."""

    booster: object | None = None
    manifest: dict = field(default_factory=dict)
    knots_x: np.ndarray | None = None
    knots_y: np.ndarray | None = None
    load_attempted: bool = False
    degraded: bool = False
    failure: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self.booster is not None and self.knots_x is not None


_state = _RecommenderState()


def reset_state() -> None:
    """Drop the loaded model. For tests and for a deliberate reload only."""
    global _state
    _state = _RecommenderState()


def _artifact_paths() -> tuple[Path, Path, Path]:
    model_path = Path(settings.RECOMMENDER_MODEL_PATH)
    return (
        model_path,
        model_path.with_name("loan_recommender_manifest.json"),
        Path(settings.CALIBRATION_KNOTS_PATH),
    )


def load_models() -> None:
    """
    Load the booster, its manifest and the calibration knots. Idempotent.

    A FEATURE-CONTRACT MISMATCH IS RE-RAISED, not degraded into a fallback. A missing
    model is a degradation the system is designed to survive; a model whose column
    order disagrees with app/ml/features.py would silently feed every value to the
    wrong feature and produce confident nonsense, which is worse than no model at all.
    """
    if _state.load_attempted:
        return
    _state.load_attempted = True

    model_path, manifest_path, calibration_path = _artifact_paths()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _state.manifest = manifest

        # Contract first.
        assert_manifest_matches(manifest["feature_manifest"])
        set_lender_encoding(manifest["feature_manifest"]["lender_encoding"])

        calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
        knots_x = np.asarray(calibration["knots_x"], dtype=np.float64)
        knots_y = np.asarray(calibration["knots_y"], dtype=np.float64)
        if knots_x.size == 0 or knots_x.size != knots_y.size:
            raise ValueError(
                f"calibration knots are unusable: {knots_x.size} x-values against "
                f"{knots_y.size} y-values"
            )
        if np.any(np.diff(knots_y) < 0):
            raise ValueError(
                "calibration knots are not monotone — a higher ranker margin would "
                "yield a lower suitability"
            )

        import xgboost

        booster = xgboost.Booster()
        booster.load_model(str(model_path))

        _state.booster = booster
        _state.knots_x = knots_x
        _state.knots_y = knots_y
        logger.info(
            "recommender loaded: %s (version %s, %d calibration knots)",
            model_path,
            manifest.get("model_version"),
            knots_x.size,
        )
    except FileNotFoundError as error:
        _state.degraded = True
        _state.failure = f"{type(error).__name__}: {error}"
        logger.warning(
            "recommender artifact not found at %s (%s). Falling back to the "
            "deterministic diagnostic ranking; the response will be flagged "
            "DETERMINISTIC_FALLBACK.",
            model_path,
            error,
        )
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        _state.degraded = True
        _state.failure = f"{type(error).__name__}: {error}"
        logger.warning(
            "recommender artifact at %s could not be loaded (%s). Falling back to the "
            "deterministic diagnostic ranking; the response will be flagged "
            "DETERMINISTIC_FALLBACK.",
            model_path,
            error,
            exc_info=True,
        )


def get_recommender_model():
    """Lazy accessor. Returns None when the artifact is unavailable."""
    if not _state.load_attempted:
        load_models()
    return _state.booster if _state.is_loaded else None


def is_degraded() -> bool:
    return _state.degraded


def calibrate(margins: np.ndarray) -> np.ndarray:
    """
    Raw margin -> calibrated suitability in [0,1], via numpy.interp over the exported
    knots. Exactly what P10 asserted its export reproduces.

    numpy.interp CLAMPS outside the fitted range, which is the correct behaviour: a
    margin beyond anything seen during calibration gets the end knot rather than an
    extrapolation that could leave [0,1].
    """
    if _state.knots_x is None or _state.knots_y is None:
        raise RuntimeError("calibration knots are not loaded")
    return np.interp(margins, _state.knots_x, _state.knots_y)


def _fallback_ranking(
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    candidates: list[Candidate],
    risk_pd: float,
) -> ScoringResult:
    """
    The ONLY path on which the diagnostic score orders anything.

    Suitability is None on every candidate: the field is named for the ML model's
    output and must not carry a rescaled deterministic score. The raw margin is None
    for the same reason — there was no ranker margin.
    """
    scores = [
        diagnostic_utility_score(financial_metrics, portfolio_metrics, candidate, risk_pd)
        for candidate in candidates
    ]
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
    return ScoringResult(
        scored_candidates=[
            ScoredCandidate(candidate=candidates[index], rank=rank)
            for rank, index in enumerate(order, start=1)
        ],
        source=RecommendationSource.DETERMINISTIC_FALLBACK,
    )


def score_candidates(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    personalization_context: PersonalizationContext,
    requirement: LoanRequirement,
    products_by_id: dict[str, LoanProduct],
    candidates: list[Candidate],
    risk_pd: float,
) -> ScoringResult:
    """
    Score every candidate and return them in DESCENDING suitability with ranks 1..n.

    `customer` is required because CONTEXT.md 6.3 puts age and credit score in the
    feature set and both live on the profile — the same P8 decision that shaped
    build_pair_features.

    Candidates are never filtered, mutated, or re-checked. An empty list in gives an
    empty list out, with the source still reported so the caller knows which path ran.
    """
    booster = get_recommender_model()
    source = (
        RecommendationSource.ML_RANKER
        if booster is not None
        else RecommendationSource.DETERMINISTIC_FALLBACK
    )

    if not candidates:
        return ScoringResult(scored_candidates=[], source=source)

    if booster is None:
        return _fallback_ranking(
            financial_metrics, portfolio_metrics, candidates, risk_pd
        )

    import xgboost

    matrix = build_pair_feature_matrix(
        customer,
        financial_metrics,
        portfolio_metrics,
        personalization_context,
        requirement,
        candidates,
        products_by_id,
        risk_pd,
    )
    margins = np.asarray(booster.predict(xgboost.DMatrix(matrix)), dtype=np.float64)
    suitability = np.clip(calibrate(margins), 0.0, 1.0)

    # Descending suitability. Ties break by the raw margin, then by original position,
    # so the ordering is total and deterministic — an arbitrary tie-break would make
    # the same request produce different recommendations between runs.
    order = sorted(
        range(len(candidates)),
        key=lambda i: (-suitability[i], -margins[i], i),
    )
    return ScoringResult(
        scored_candidates=[
            ScoredCandidate(
                candidate=candidates[index],
                raw_ranker_margin=float(margins[index]),
                suitability=float(suitability[index]),
                rank=rank,
            )
            for rank, index in enumerate(order, start=1)
        ],
        source=RecommendationSource.ML_RANKER,
    )
