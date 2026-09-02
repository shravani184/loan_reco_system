"""
Train the SECONDARY risk classifier (P9). Offline only.

WHAT THIS MODEL IS. Its output is a FEATURE for the primary recommender and a
user-facing risk disclosure. It does not select a loan, does not veto a candidate, and
is not the recommendation (CONTEXT.md non-negotiable 3). There is no selection logic in
this file and none may be added.

THE TRAINING LABELS ARE SYNTHETIC. They are drawn by
training/generate_risk_outcomes.py from a documented latent-risk model, because this
project has no observed repayment data. The classifier therefore partially recovers
that generative model, and reported ROC-AUC measures agreement with it — not real
credit risk. That sentence belongs in every report of these numbers.

FEATURES COME FROM app/ml/features.py. There is no feature assembly here; a second
path is the specific defect the shared-module rule prevents (AGENTS.md section 6
rule 4).

Persisted as XGBoost JSON, never pickle, so artifacts survive library upgrades and
load without a pickle-compatible environment (CONTEXT.md 17.2).

Run:

    python -m training.train_risk
"""

import csv
import json
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from xgboost import XGBClassifier

from app.config import settings
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.ml.features import (
    RISK_FEATURE_COLUMNS,
    build_lender_encoding,
    build_risk_features,
    feature_manifest,
    set_lender_encoding,
)
from training.datasets import load_customers, load_portfolios, load_products

DATA_DIR = Path("data")
MODEL_DIR = Path("models")
TRAINING_SEED = 20260906

# Deliberately small so the search finishes in minutes. Recorded in the manifest.
PARAM_GRID = {
    "max_depth": [2, 3, 4],
    "learning_rate": [0.05, 0.10],
    "n_estimators": [150, 300],
    "min_child_weight": [1, 5],
}
CV_FOLDS = 5

# Reliability curve resolution. Ten equal-width probability bins.
RELIABILITY_BINS = 10


def _load_split() -> dict[str, str]:
    """
    Reuse the Phase 7 customer-level split so no customer leaks between train and test.

    P7 only split the 170 customers who produced a usable candidate group; the risk
    model trains on all 400, since risk does not need candidates. Customers P7 did not
    cover are assigned here by the SAME seed and test share, so the two splits agree
    wherever they overlap and never contradict each other.
    """
    from training.build_dataset import SPLIT_SEED, TEST_SHARE

    path = DATA_DIR / "relevance_groups.csv"
    known: dict[str, str] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            lines = [line for line in handle if not line.startswith("#")]
        known = {row["user_id"]: row["split"] for row in csv.DictReader(lines)}

    all_ids = sorted(profile.user_id for profile, _ in load_customers())
    remaining = sorted(user_id for user_id in all_ids if user_id not in known)
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(remaining)
    cut = int(len(remaining) * (1.0 - TEST_SHARE))
    for index, user_id in enumerate(remaining):
        known[user_id] = "train" if index < cut else "test"
    return known


def _load_outcomes() -> dict[str, int]:
    path = DATA_DIR / "risk_outcomes.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m training.generate_risk_outcomes` first "
            "— the risk target is synthetic and must be generated before training."
        )
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return {row["user_id"]: int(row["defaulted"]) for row in csv.DictReader(lines)}


def build_training_matrix():
    """
    Assemble X, y and the split mask using the SHARED feature builder.

    Returns (X, y, splits, user_ids) with rows aligned across all four.
    """
    set_lender_encoding(build_lender_encoding(load_products()))

    outcomes = _load_outcomes()
    splits = _load_split()
    portfolios = load_portfolios()

    rows, labels, row_splits, user_ids = [], [], [], []
    for profile, requirement in load_customers():
        if profile.user_id not in outcomes:
            continue
        financial = analyze_financials(profile)
        portfolio = analyze_portfolio(portfolios.get(profile.user_id))
        rows.append(build_risk_features(profile, financial, portfolio, requirement))
        labels.append(outcomes[profile.user_id])
        row_splits.append(splits[profile.user_id])
        user_ids.append(profile.user_id)

    return (
        np.vstack(rows),
        np.asarray(labels, dtype=np.int32),
        np.asarray(row_splits),
        user_ids,
    )


def reliability_curve(y_true: np.ndarray, probabilities: np.ndarray) -> list[dict]:
    """
    Predicted-vs-observed frequency in equal-width probability bins.

    Reported rather than a single number because a Brier score can look acceptable
    while the model is systematically over- or under-confident in one region.
    """
    edges = np.linspace(0.0, 1.0, RELIABILITY_BINS + 1)
    curve = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (probabilities >= low) & (
            probabilities < high if high < 1.0 else probabilities <= high
        )
        count = int(mask.sum())
        curve.append(
            {
                "bin_low": round(float(low), 3),
                "bin_high": round(float(high), 3),
                "count": count,
                "mean_predicted": round(float(probabilities[mask].mean()), 4)
                if count
                else None,
                "observed_rate": round(float(y_true[mask].mean()), 4) if count else None,
            }
        )
    return curve


def evaluate(y_true: np.ndarray, probabilities: np.ndarray) -> dict:
    """
    Classifier metrics. Accuracy alone is not sufficient reporting for an imbalanced
    target, so it is reported alongside the rest and never on its own.
    """
    predicted = (probabilities >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 4),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 4),
        "brier_score": round(float(brier_score_loss(y_true, probabilities)), 4),
        "accuracy": round(float((predicted == y_true).mean()), 4),
        "positive_rate_actual": round(float(y_true.mean()), 4),
        "positive_rate_predicted": round(float(predicted.mean()), 4),
        "reliability_curve": reliability_curve(y_true, probabilities),
    }


def achievable_ceiling() -> dict:
    """
    The honest upper bound on this metric.

    A ROC-AUC means nothing without knowing what was achievable. The synthetic outcome
    is drawn from a latent-risk model containing a shock term that is DELIBERATELY not
    a feature, so no model reading RISK_FEATURE_COLUMNS can recover the label exactly.
    Two reference points are computed over the whole population:

      oracle   AUC of the true drawn probability, shock included — an upper bound
               nothing observable can reach.
      ceiling  AUC of the same latent model with the shock set to zero, i.e. the best
               any model using only the features could do.

    Reporting the model's AUC beside the ceiling is what distinguishes "the model
    learned most of what is learnable" from "the metric looks low".
    """
    import math

    from training.generate_risk_outcomes import default_log_odds

    outcomes = _load_outcomes()
    portfolios = load_portfolios()

    y, oracle, observable = [], [], []
    with (DATA_DIR / "risk_outcomes.csv").open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    drawn = {
        row["user_id"]: float(row["latent_default_probability"])
        for row in csv.DictReader(lines)
    }

    for profile, requirement in load_customers():
        if profile.user_id not in outcomes:
            continue
        financial = analyze_financials(profile)
        portfolio = analyze_portfolio(portfolios.get(profile.user_id))
        y.append(outcomes[profile.user_id])
        oracle.append(drawn[profile.user_id])
        log_odds = default_log_odds(profile, financial, portfolio, requirement, 0.0)
        observable.append(1.0 / (1.0 + math.exp(-log_odds)))

    return {
        "oracle_roc_auc": round(float(roc_auc_score(y, oracle)), 4),
        "feature_ceiling_roc_auc": round(float(roc_auc_score(y, observable)), 4),
        "note": (
            "oracle knows the drawn probability including the unobserved shock; "
            "feature_ceiling is the best achievable from RISK_FEATURE_COLUMNS alone."
        ),
    }


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    X, y, splits, _ = build_training_matrix()
    train_mask = splits == "train"
    test_mask = ~train_mask
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"features        {X.shape[1]} columns")
    print(f"train / test    {len(y_train)} / {len(y_test)} customers")
    print(f"default rate    train {y_train.mean():.4f} | test {y_test.mean():.4f}")

    search = GridSearchCV(
        XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            random_state=TRAINING_SEED,
            n_jobs=1,
        ),
        param_grid=PARAM_GRID,
        scoring="roc_auc",
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=TRAINING_SEED),
        n_jobs=-1,
        refit=True,
    )
    search.fit(X_train, y_train)
    model = search.best_estimator_

    test_probabilities = model.predict_proba(X_test)[:, 1]
    train_probabilities = model.predict_proba(X_train)[:, 1]
    test_metrics = evaluate(y_test, test_probabilities)
    train_metrics = evaluate(y_train, train_probabilities)

    print(f"\nbest params     {search.best_params_}")
    print(f"cv roc_auc      {search.best_score_:.4f}")
    print("\nTEST METRICS (labels are SYNTHETIC)")
    for key in ("roc_auc", "pr_auc", "precision", "recall", "f1", "brier_score", "accuracy"):
        print(f"  {key:12} {test_metrics[key]}")
    print("\nreliability curve (predicted vs observed, test):")
    for row in test_metrics["reliability_curve"]:
        if row["count"]:
            print(
                f"  [{row['bin_low']:.1f},{row['bin_high']:.1f})  n={row['count']:3}  "
                f"predicted {row['mean_predicted']:.3f}  observed {row['observed_rate']:.3f}"
            )

    ceiling = achievable_ceiling()
    print("\nACHIEVABLE CEILING (a ROC-AUC means nothing without one)")
    print(f"  oracle, incl. unobserved shock  {ceiling['oracle_roc_auc']}")
    print(f"  best possible from features     {ceiling['feature_ceiling_roc_auc']}")
    print(f"  this model, test set            {test_metrics['roc_auc']}")

    model_path = MODEL_DIR / Path(settings.RISK_MODEL_PATH).name
    model.get_booster().save_model(str(model_path))

    # The median PD over the TRAINING set. P11 imputes with this when the artifact
    # cannot be loaded, and flags the imputation (CONTEXT.md section 8).
    training_pd_median = float(np.median(train_probabilities))

    manifest = {
        "model_version": settings.RISK_MODEL_VERSION,
        "model_role": (
            "SECONDARY. Output is a feature for the primary recommender and a "
            "user-facing risk disclosure. It never selects, gates or vetoes."
        ),
        "training_labels_are_synthetic": True,
        "training_label_source": "training/generate_risk_outcomes.py",
        "training_label_note": (
            "Repayment outcomes are drawn from a documented latent-risk model, not "
            "observed. ROC-AUC measures agreement with that generative process, not "
            "real credit risk."
        ),
        "feature_version": settings.FEATURE_VERSION,
        "config_version": settings.CONFIG_VERSION,
        "feature_columns": list(RISK_FEATURE_COLUMNS),
        "feature_manifest": feature_manifest(),
        "seed": TRAINING_SEED,
        "training_rows": int(train_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "split_source": "phase-7 customer split, extended by the same seed",
        "searched_grid": PARAM_GRID,
        "cv_folds": CV_FOLDS,
        "cv_scoring": "roc_auc",
        "cv_best_score": round(float(search.best_score_), 4),
        "best_params": search.best_params_,
        "training_pd_median": round(training_pd_median, 6),
        "test_metrics": test_metrics,
        "train_metrics": train_metrics,
        "achievable_ceiling": ceiling,
    }
    manifest_path = MODEL_DIR / "risk_model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nsaved {model_path}")
    print(f"saved {manifest_path}")
    print("TRAINING LABELS ARE SYNTHETIC — see training/generate_risk_outcomes.py")


if __name__ == "__main__":
    main()
