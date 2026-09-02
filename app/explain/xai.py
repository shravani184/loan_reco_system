"""
XAI — model behaviour, explained (P13).

THE PRIMARY TARGET IS THE RECOMMENDER, not the risk model. Explaining only risk is a
v1.0 behaviour and is insufficient here: the question this product must answer is why
the model preferred THIS financing configuration over the others it scored.

CONTRIBUTIONS COME FROM XGBOOST'S NATIVE TreeSHAP — predict(..., pred_contribs=True).
Both models are tree ensembles, so this yields exact SHAP values with ZERO additional
serving dependency. THE `shap` PACKAGE IS NEVER IMPORTED HERE: it is a training-only
extra, and importing it in app/ breaks both the memory budget and the serving-import
test (AGENTS.md section 14).

STRUCTURED DATA ONLY. This module produces no prose. If contribution computation
fails it degrades to gain-based feature importances and FLAGS which was used — a
degradation that is not flagged is a correctness defect (AGENTS.md section 7).

Nothing is loaded at import; the recommender's lazy accessor is used.
"""

import logging

import numpy as np

from app.config import settings
from app.ml.features import PAIR_FEATURE_COLUMNS, RISK_FEATURE_COLUMNS, build_pair_feature_matrix
from app.ml.recommender import get_recommender_model
from app.ml.risk import get_risk_model
from app.schemas import (
    CustomerProfile,
    FinancialMetrics,
    LoanProduct,
    LoanRequirement,
    PersonalizationContext,
    PortfolioMetrics,
    ScoredCandidate,
)
from app.schemas.enums import XaiMethod
from app.schemas.explanation import (
    FeatureContrast,
    FeatureContribution,
    XaiExplanation,
)

logger = logging.getLogger(__name__)

# How many features to surface. All are computed; this bounds what is handed to a UI
# or a prompt, ranked by absolute contribution.
TOP_FEATURES = 10


class XaiDisabled(RuntimeError):
    """Raised when the XAI endpoint is switched off by config."""


def _require_enabled() -> None:
    if not settings.ENABLE_XAI_ENDPOINT:
        raise XaiDisabled(
            "the XAI endpoint is disabled by ENABLE_XAI_ENDPOINT. This is the one "
            "permitted lever if the serving memory target cannot be met "
            "(CONTEXT.md 17.2)."
        )


def _contributions(booster, matrix: np.ndarray) -> np.ndarray | None:
    """
    Exact per-feature contributions from XGBoost's own TreeSHAP.

    Returns an array of shape (rows, n_features + 1); the final column is the bias.
    None on failure, so the caller can degrade and flag it.
    """
    try:
        import xgboost

        return booster.predict(xgboost.DMatrix(matrix), pred_contribs=True)
    except Exception as error:  # noqa: BLE001 - degradation must never propagate
        logger.warning(
            "TreeSHAP contribution computation failed (%s); degrading to gain-based "
            "feature importances and flagging the response.",
            error,
            exc_info=True,
        )
        return None


def _importance_fallback(booster, columns: tuple[str, ...]) -> list[FeatureContribution]:
    """
    Gain-based importances. GLOBAL, not per-prediction: they say which features matter
    to the MODEL, not which pushed THIS candidate. That is a real loss of meaning,
    which is why every consumer is told the result is degraded.
    """
    try:
        scores = booster.get_score(importance_type="gain")
    except Exception:  # noqa: BLE001
        scores = {}
    return [
        FeatureContribution(
            feature=name,
            value=0.0,
            contribution=float(scores.get(f"f{index}", 0.0)),
        )
        for index, name in enumerate(columns)
    ]


def explain_recommendation_choice(
    customer: CustomerProfile,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    personalization_context: PersonalizationContext,
    requirement: LoanRequirement,
    products_by_id: dict[str, LoanProduct],
    scored_candidates: list[ScoredCandidate],
    risk_pd: float,
    winner_candidate_id: str | None = None,
) -> XaiExplanation:
    """
    Why the winning candidate outranked the others.

    The signature takes the same inputs as score_candidates because contributions
    require the FEATURE ROW, and a ScoredCandidate carries only the candidate. Rebuilding
    the matrix here through the shared feature module keeps one feature path rather than
    caching a second copy of it (AGENTS.md section 6 rule 4).

    `winner_candidate_id` defaults to rank 1, but the SELECTED candidate is not always
    rank 1 — a guardrail may have blocked the model's first pick — so the caller can
    name the one that was actually recommended.

    The contrast is against the highest-ranked OTHER candidate, which is the comparison
    the product needs: not "why is this good" but "why this one rather than that one".
    """
    _require_enabled()

    if not scored_candidates:
        return XaiExplanation(
            candidate_id="",
            method=XaiMethod.TREE_SHAP,
            degraded=True,
            note="no candidates were scored, so there is nothing to explain",
        )

    ordered = sorted(scored_candidates, key=lambda item: item.rank)
    winner_index = 0
    if winner_candidate_id is not None:
        for index, item in enumerate(ordered):
            if item.candidate.candidate_id == winner_candidate_id:
                winner_index = index
                break
    winner = ordered[winner_index]
    runner_up_index = 1 if winner_index == 0 else 0
    runner_up = ordered[runner_up_index] if len(ordered) > 1 else None

    booster = get_recommender_model()
    if booster is None:
        # In DETERMINISTIC_FALLBACK there is no model to explain. Saying so is the
        # honest answer; inventing contributions for a ranking the model did not
        # produce would be worse than none.
        return XaiExplanation(
            candidate_id=winner.candidate.candidate_id,
            method=XaiMethod.FEATURE_IMPORTANCE,
            degraded=True,
            note=(
                "the recommender artifact is unavailable, so this ranking came from "
                "the deterministic fallback and there is no model to explain"
            ),
        )

    matrix = build_pair_feature_matrix(
        customer,
        financial_metrics,
        portfolio_metrics,
        personalization_context,
        requirement,
        [item.candidate for item in ordered],
        products_by_id,
        risk_pd,
    )
    raw = _contributions(booster, matrix)

    if raw is None:
        return XaiExplanation(
            candidate_id=winner.candidate.candidate_id,
            method=XaiMethod.FEATURE_IMPORTANCE,
            degraded=True,
            runner_up_candidate_id=(
                runner_up.candidate.candidate_id if runner_up else None
            ),
            contributions=_importance_fallback(booster, PAIR_FEATURE_COLUMNS)[
                :TOP_FEATURES
            ],
            note=(
                "TreeSHAP failed; these are GLOBAL gain-based importances, not "
                "per-candidate contributions"
            ),
        )

    # The last column is the bias/base value, not a feature.
    winner_row = raw[winner_index]
    base_value = float(winner_row[-1])
    winner_contributions = winner_row[:-1]

    contributions = [
        FeatureContribution(
            feature=name,
            value=float(matrix[winner_index][index]),
            contribution=float(winner_contributions[index]),
        )
        for index, name in enumerate(PAIR_FEATURE_COLUMNS)
    ]
    contributions.sort(key=lambda item: -abs(item.contribution))

    contrast: list[FeatureContrast] = []
    if runner_up is not None:
        runner_up_contributions = raw[runner_up_index][:-1]
        contrast = [
            FeatureContrast(
                feature=name,
                winner_value=float(matrix[winner_index][index]),
                runner_up_value=float(matrix[runner_up_index][index]),
                winner_contribution=float(winner_contributions[index]),
                runner_up_contribution=float(runner_up_contributions[index]),
                delta=float(winner_contributions[index] - runner_up_contributions[index]),
            )
            for index, name in enumerate(PAIR_FEATURE_COLUMNS)
        ]
        contrast.sort(key=lambda item: -abs(item.delta))

    return XaiExplanation(
        candidate_id=winner.candidate.candidate_id,
        method=XaiMethod.TREE_SHAP,
        degraded=False,
        base_value=base_value,
        contributions=contributions[:TOP_FEATURES],
        contrast=contrast[:TOP_FEATURES],
        runner_up_candidate_id=runner_up.candidate.candidate_id if runner_up else None,
    )


def explain_risk(features: np.ndarray) -> XaiExplanation:
    """
    Contributions for the SECONDARY risk classifier.

    Secondary in this phase too: the risk model explains a disclosure, not a decision.
    """
    _require_enabled()

    booster = get_risk_model()
    if booster is None:
        return XaiExplanation(
            candidate_id="risk",
            method=XaiMethod.FEATURE_IMPORTANCE,
            degraded=True,
            note="the risk artifact is unavailable; the PD was imputed, not predicted",
        )

    row = np.asarray(features, dtype=np.float64).reshape(1, -1)
    raw = _contributions(booster, row)
    if raw is None:
        return XaiExplanation(
            candidate_id="risk",
            method=XaiMethod.FEATURE_IMPORTANCE,
            degraded=True,
            contributions=_importance_fallback(booster, RISK_FEATURE_COLUMNS)[
                :TOP_FEATURES
            ],
            note="TreeSHAP failed; these are GLOBAL gain-based importances",
        )

    contributions = [
        FeatureContribution(
            feature=name,
            value=float(row[0][index]),
            contribution=float(raw[0][index]),
        )
        for index, name in enumerate(RISK_FEATURE_COLUMNS)
    ]
    contributions.sort(key=lambda item: -abs(item.contribution))
    return XaiExplanation(
        candidate_id="risk",
        method=XaiMethod.TREE_SHAP,
        degraded=False,
        base_value=float(raw[0][-1]),
        contributions=contributions[:TOP_FEATURES],
    )
