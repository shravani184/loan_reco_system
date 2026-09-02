"""
Assemble the (customer, candidate) training matrix for the primary recommender (P10).

Offline only. Every feature comes from app/ml/features.py — there is no feature
assembly here, only the plumbing that gathers its inputs.

CONSISTENCY WITH THE LABELS IS THE POINT. Candidates are rebuilt by re-running the
SAME population build that produced the labels (training/population.py), and the
labels themselves are read back from data/relevance_dataset.csv so the NOISED label
that was written to disk is the one the model trains on. Regenerating candidates a
second, different way is how a training set quietly stops matching its labels.
"""

import csv
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.ml.features import (
    build_lender_encoding,
    build_pair_feature_matrix,
    build_risk_features,
    set_lender_encoding,
)
from app.personalization.context import (
    get_personalization_context,
    neutral_personalization_context,
)
from app.personalization.store import PersonalizationStore
from app.schemas import Candidate, PersonalizationContext
from app.schemas.enums import FeedbackEventType, FinancingStrategy, LoanPurpose
from training.datasets import load_history, load_products
from training.labeling import CustomerContext
from training.population import build_population

DATA_DIR = Path("data")


@dataclass
class PairGroup:
    """One customer's whole candidate group — the unit a ranker learns from."""

    user_id: str
    split: str
    context: CustomerContext
    personalization: PersonalizationContext
    candidates: list[Candidate]
    labels: np.ndarray
    features: np.ndarray
    risk_pd: float
    # The labeling policy's OWN combined score for each candidate. Not a feature and
    # never used in training — carried only so P10 can measure the achievable ceiling.
    policy_raw_scores: np.ndarray


def _load_labels() -> dict[tuple[str, str], int]:
    """The labels AS WRITTEN, including the 5% noise applied at dataset build."""
    path = DATA_DIR / "relevance_dataset.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m training.build_dataset` first."
        )
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return {
        (row["user_id"], row["candidate_id"]): int(row["label"])
        for row in csv.DictReader(lines)
    }


def _load_splits() -> dict[str, str]:
    path = DATA_DIR / "relevance_groups.csv"
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return {row["user_id"]: row["split"] for row in csv.DictReader(lines)}


def build_personalization_contexts(user_ids: set[str]) -> dict[str, PersonalizationContext]:
    """
    Load the synthetic history through the REAL personalization layer.

    A throwaway database under the OS temp directory, never data/. Using
    get_personalization_context rather than re-deriving affinities keeps training and
    serving on one code path — the same rule as the feature module.
    """
    rows = load_history()
    if not rows:
        return {user_id: neutral_personalization_context() for user_id in user_ids}

    import time

    now = time.time()
    day = 86400.0

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "history.db"
        with PersonalizationStore(f"sqlite:///{database}") as store:
            for row in rows:
                at = now - float(row["days_ago"]) * day
                if row["record_type"] == "RECOMMENDATION":
                    store.record_recommendation(
                        user_id=row["user_id"],
                        purpose=LoanPurpose(row["purpose"]),
                        product_id=row["product_id"] or None,
                        amount=float(row["amount"]),
                        tenure=int(row["tenure"]) if row["tenure"] else None,
                        strategy=FinancingStrategy(row["strategy"]),
                        suitability=float(row["suitability"]) if row["suitability"] else None,
                        status=row["status"],
                        at=at,
                    )
                else:
                    store.record_feedback_event(
                        user_id=row["user_id"],
                        event_type=FeedbackEventType(row["event_type"]),
                        product_id=row["product_id"] or None,
                        at=at,
                    )
            return {
                user_id: get_personalization_context(user_id, store=store, now=now)
                for user_id in user_ids
            }


def _risk_probabilities(groups, model_path: Path) -> dict[str, float]:
    """
    PD per customer from the Phase 9 model.

    THE PD IS A PARAMETER OF THE FEATURE BUILDER, not something the recommender
    computes. It is predicted here and handed in as a number, which is what keeps the
    dependency acyclic and stops the secondary model from becoming a decision-maker.
    """
    import xgboost

    booster = xgboost.Booster()
    booster.load_model(str(model_path))

    rows = [
        build_risk_features(
            group.context.profile,
            group.context.financial,
            group.context.portfolio,
            group.context.requirement,
        )
        for group in groups
    ]
    matrix = xgboost.DMatrix(np.vstack(rows))
    predictions = booster.predict(matrix)
    return {
        group.user_id: float(probability)
        for group, probability in zip(groups, predictions)
    }


def load_pair_groups(risk_model_path: Path | None = None) -> list[PairGroup]:
    """
    Every labelled group, with its feature matrix built and its PD attached.

    Groups come back in a stable order (population order), and rows within a group are
    in candidate order — which is what XGBRanker's `group` array assumes.
    """
    products = load_products()
    set_lender_encoding(build_lender_encoding(products))
    products_by_id = {product.product_id: product for product in products}

    labels = _load_labels()
    splits = _load_splits()
    population = build_population()
    personalization = build_personalization_contexts(
        {group.user_id for group in population}
    )

    risk_path = risk_model_path or Path("models/risk_model.json")
    if not risk_path.exists():
        raise FileNotFoundError(
            f"{risk_path} not found. Run `python -m training.train_risk` first — the "
            "risk PD is a feature of the recommender."
        )
    risk_pd = _risk_probabilities(population, risk_path)

    groups: list[PairGroup] = []
    for group in population:
        candidates = [graded.candidate for graded in group.graded]
        row_labels = [
            labels.get((group.user_id, candidate.candidate_id))
            for candidate in candidates
        ]
        # A candidate with no label written to disk cannot be trained on. This should
        # never happen; if it does, the dataset and the population have diverged.
        if any(label is None for label in row_labels):
            missing = sum(1 for label in row_labels if label is None)
            raise RuntimeError(
                f"{group.user_id}: {missing} candidates have no label in "
                "relevance_dataset.csv — the dataset and the population disagree. "
                "Re-run `python -m training.build_dataset`."
            )

        groups.append(
            PairGroup(
                user_id=group.user_id,
                split=splits[group.user_id],
                context=group.context,
                personalization=personalization[group.user_id],
                candidates=candidates,
                labels=np.asarray(row_labels, dtype=np.int32),
                features=build_pair_feature_matrix(
                    group.context.profile,
                    group.context.financial,
                    group.context.portfolio,
                    personalization[group.user_id],
                    group.context.requirement,
                    candidates,
                    products_by_id,
                    risk_pd[group.user_id],
                ),
                risk_pd=risk_pd[group.user_id],
                policy_raw_scores=np.asarray(
                    [graded.raw_score for graded in group.graded], dtype=np.float64
                ),
            )
        )
    return groups


def stack(groups: list[PairGroup]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Concatenate groups into (X, y, group_sizes) as XGBRanker expects."""
    if not groups:
        return (
            np.empty((0, 0), dtype=np.float64),
            np.empty((0,), dtype=np.int32),
            [],
        )
    X = np.vstack([group.features for group in groups])
    y = np.concatenate([group.labels for group in groups])
    sizes = [len(group.labels) for group in groups]
    return X, y, sizes
