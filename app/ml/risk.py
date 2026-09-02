"""
Risk inference — the SECONDARY model (P11).

ITS OUTPUT IS A FEATURE AND A DISCLOSURE, NEVER A DECISION. It does not determine
eligibility, does not compute an EMI, does not select a loan and does not block a
candidate (CONTEXT.md non-negotiable 3). There is no selection logic in this module
and none may be added.

MODEL LOADING RULE. Nothing is loaded at import. Importing this module must not touch
the filesystem — that is what keeps pytest collection fast and service startup
predictable (AGENTS.md section 2). Use:

    load_models()      explicit, called once by the API lifespan handler
    get_risk_model()   lazy accessor, loads on first call

FALLBACK. A missing or corrupt artifact is logged with its path and the exception,
then handled: the PD is imputed at the training-set median recorded in the manifest
and RiskPrediction.imputed is True. Never silent, never a 500 on the primary path
(AGENTS.md section 7).
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.config import settings
from app.ml.features import (
    assert_manifest_matches,
    build_risk_features,
    set_lender_encoding,
)
from app.schemas import (
    CustomerProfile,
    FinancialMetrics,
    LoanRequirement,
    PortfolioMetrics,
    RiskPrediction,
)
from app.schemas.enums import RiskClass

logger = logging.getLogger(__name__)

# Used only when the manifest itself cannot be read, so there is no recorded median to
# impute with. Deliberately a visible, middling value rather than 0.0: imputing "no
# risk" when the model is broken would be the dangerous direction to fail in.
LAST_RESORT_PD = 0.5


@dataclass
class _RiskModelState:
    """Module-level state. Empty until load_models() or the first lazy access."""

    booster: object | None = None
    manifest: dict = field(default_factory=dict)
    training_pd_median: float | None = None
    load_attempted: bool = False
    degraded: bool = False
    failure: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self.booster is not None


_state = _RiskModelState()


def reset_state() -> None:
    """Drop the loaded model. For tests and for a deliberate reload only."""
    global _state
    _state = _RiskModelState()


def _manifest_path() -> Path:
    return Path(settings.RISK_MODEL_PATH).with_name("risk_model_manifest.json")


def load_models() -> None:
    """
    Load the risk booster and its manifest. Idempotent: a second call is a no-op, so
    the lifespan handler and a lazy accessor cannot load twice.

    A FEATURE-CONTRACT MISMATCH IS A HARD FAILURE and is re-raised. That is different
    from a missing artifact: a missing model is a degradation the system is designed
    to survive, while a model whose columns disagree with this code would produce
    confident nonsense from every prediction.
    """
    if _state.load_attempted:
        return
    _state.load_attempted = True

    model_path = Path(settings.RISK_MODEL_PATH)
    manifest_path = _manifest_path()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _state.manifest = manifest
        _state.training_pd_median = manifest.get("training_pd_median")

        # Contract first: never load a booster this code cannot feed correctly.
        assert_manifest_matches(manifest["feature_manifest"])
        set_lender_encoding(manifest["feature_manifest"]["lender_encoding"])

        import xgboost

        booster = xgboost.Booster()
        booster.load_model(str(model_path))
        _state.booster = booster
        logger.info(
            "risk model loaded: %s (version %s)",
            model_path,
            manifest.get("model_version"),
        )
    except FileNotFoundError as error:
        _state.degraded = True
        _state.failure = f"{type(error).__name__}: {error}"
        logger.warning(
            "risk model artifact not found at %s (%s). PD will be imputed and flagged.",
            model_path,
            error,
        )
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        _state.degraded = True
        _state.failure = f"{type(error).__name__}: {error}"
        logger.warning(
            "risk model artifact at %s could not be loaded (%s). PD will be imputed "
            "and flagged.",
            model_path,
            error,
            exc_info=True,
        )


def get_risk_model():
    """Lazy accessor. Returns None when the artifact is unavailable."""
    if not _state.load_attempted:
        load_models()
    return _state.booster


def is_degraded() -> bool:
    return _state.degraded


def imputed_pd() -> float:
    """
    The PD used when the model is unavailable: the training-set median recorded in the
    manifest. Recorded at P9 precisely so this path has a real value rather than an
    invented one.
    """
    if _state.training_pd_median is not None:
        return float(_state.training_pd_median)
    return LAST_RESORT_PD


def risk_class_for(probability: float) -> RiskClass:
    """
    Band a PD. The ladder is derived from RISK_CLASS_MIN_PD sorted descending, with
    LOW as the floor — the same pattern as the financial-health and portfolio-risk
    bands, so one config dict is the single source of cut-points and order.

    THIS IS A DISCLOSURE, NOT A GATE.
    """
    for band, minimum in sorted(
        settings.RISK_CLASS_MIN_PD.items(), key=lambda item: item[1], reverse=True
    ):
        if probability >= minimum:
            return band
    return RiskClass.LOW


def predict_risk(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    requirement: LoanRequirement,
) -> RiskPrediction:
    """
    Probability of default plus its band.

    `customer` is required because CONTEXT.md 6.3 puts age and credit score in the
    feature set and both live on the profile — the same P8 decision that shaped
    build_risk_features.
    """
    booster = get_risk_model()

    if booster is None:
        probability = imputed_pd()
        return RiskPrediction(
            risk_class=risk_class_for(probability),
            probability_of_default=probability,
            model_version=settings.RISK_MODEL_VERSION,
            imputed=True,
        )

    import xgboost

    features = build_risk_features(
        customer, financial_metrics, portfolio_metrics, requirement
    )
    matrix = xgboost.DMatrix(features.reshape(1, -1))
    probability = float(np.clip(booster.predict(matrix)[0], 0.0, 1.0))

    return RiskPrediction(
        risk_class=risk_class_for(probability),
        probability_of_default=probability,
        model_version=_state.manifest.get("model_version", settings.RISK_MODEL_VERSION),
        imputed=False,
    )
