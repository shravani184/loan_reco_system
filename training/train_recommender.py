"""
Train the PRIMARY recommender (P10). Offline only.

THIS MODEL IS THE DECISION-MAKING INTELLIGENCE OF THE SYSTEM. It scores fully-specified
financing configurations and its ordering IS the recommendation. Nothing downstream
reorders it (CONTEXT.md section 2).

THE RELEVANCE LABELS ARE SYNTHETIC, produced by training/labeling.py. Every metric
below therefore measures AGREEMENT WITH THAT POLICY, not real recommendation quality.
And agreement between this model and the diagnostic-utility baseline is NOT evidence
that either is correct — they share ancestry through the labeling policy
(AGENTS.md section 6 rules 9 and 10).

Run:

    python -m training.train_recommender
"""

import json
import random
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBRanker

from app.config import settings
from app.ml.features import PAIR_FEATURE_COLUMNS, feature_manifest, get_lender_encoding
from training.pair_dataset import load_pair_groups, stack
from training.ranking_metrics import (
    RELEVANT_THRESHOLD,
    cheapest_emi_scores,
    diagnostic_utility_scores,
    evaluate_ranking,
    random_scores,
)

MODEL_DIR = Path("models")
TRAINING_SEED = 20260907

# Small and group-aware. Recorded in the manifest.
PARAM_GRID = [
    {"max_depth": depth, "learning_rate": rate, "n_estimators": trees}
    for depth in (3, 4, 6)
    for rate in (0.05, 0.10)
    for trees in (200, 400)
]
CV_FOLDS = 4

# Share of the TRAINING customers held out to fit the calibrator. They are excluded
# from the final fit, so the isotonic map is fitted on margins the ranker has never
# seen — calibrating on training margins produces a confident, wrong curve.
CALIBRATION_SHARE = 0.25

RELIABILITY_BINS = 10


def _group_folds(n_groups: int, folds: int, seed: int) -> list[np.ndarray]:
    """
    Fold assignment BY GROUP, never by row. Splitting a customer's candidates across
    folds leaks part of a group into the fold it is evaluated on, and a ranker trained
    that way looks far better than it is.
    """
    indices = np.arange(n_groups)
    rng = np.random.default_rng(seed)
    rng.shuffle(indices)
    return [indices[fold::folds] for fold in range(folds)]


def _fit_ranker(groups, params: dict) -> XGBRanker:
    X, y, sizes = stack(groups)
    model = XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@5",
        tree_method="hist",
        random_state=TRAINING_SEED,
        n_jobs=-1,
        **params,
    )
    model.fit(X, y, group=sizes, verbose=False)
    return model


def _score_groups(model: XGBRanker, groups) -> list[np.ndarray]:
    return [model.predict(group.features) for group in groups]


def group_aware_search(train_groups) -> tuple[dict, float, list[dict]]:
    """
    Hyperparameter search with GROUP-AWARE cross-validation.

    sklearn's GridSearchCV cannot do this for a ranker: it has no way to carry the
    per-fold `group` array, and would silently split customers across folds. So the
    search is explicit.
    """
    folds = _group_folds(len(train_groups), CV_FOLDS, TRAINING_SEED)
    results = []

    for params in PARAM_GRID:
        fold_scores = []
        for held_out in folds:
            held_out_set = set(held_out.tolist())
            fit_groups = [
                group for index, group in enumerate(train_groups) if index not in held_out_set
            ]
            eval_groups = [train_groups[index] for index in held_out]
            if not fit_groups or not eval_groups:
                continue
            model = _fit_ranker(fit_groups, params)
            scores = _score_groups(model, eval_groups)
            metrics = evaluate_ranking(
                [group.labels for group in eval_groups], scores
            )
            if metrics["ndcg@5"] is not None:
                fold_scores.append(metrics["ndcg@5"])
        mean = float(np.mean(fold_scores)) if fold_scores else 0.0
        results.append({"params": params, "cv_ndcg@5": round(mean, 4)})
        print(f"  {params}  cv ndcg@5 {mean:.4f}")

    best = max(results, key=lambda row: row["cv_ndcg@5"])
    return best["params"], best["cv_ndcg@5"], results


def fit_calibration(margins: np.ndarray, labels: np.ndarray) -> dict:
    """
    Map raw ranker margin -> P(relevance >= 2) -> suitability in [0,1].

    An XGBRanker emits an unbounded RELATIVE margin, which cannot support an absolute
    acceptance threshold — and an absolute threshold is exactly what NO_SUITABLE_LOAN
    requires (CONTEXT.md 6.4).

    EXPORTED AS KNOTS, not as a pickled estimator: serving applies them with
    numpy.interp, so scikit-learn never enters the serving dependency set. This
    function asserts the knots reproduce the fitted estimator before returning them —
    an exported calibration that does not match what was fitted is worse than none.
    """
    target = (labels >= RELEVANT_THRESHOLD).astype(np.float64)
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    isotonic.fit(margins, target)

    knots_x = np.asarray(isotonic.X_thresholds_, dtype=np.float64)
    knots_y = np.asarray(isotonic.y_thresholds_, dtype=np.float64)

    fitted = isotonic.predict(margins)
    interpolated = np.interp(margins, knots_x, knots_y)
    max_difference = float(np.max(np.abs(fitted - interpolated)))
    if max_difference > 1e-9:
        raise RuntimeError(
            "exported isotonic knots do not reproduce the fitted estimator "
            f"(max difference {max_difference:.3e}). Serving would disagree with "
            "training about every suitability score."
        )

    return {
        "method": "isotonic regression on held-out groups, exported as monotone knots",
        "applied_with": "numpy.interp",
        "target": "P(relevance >= 2)",
        "knots_x": [round(float(value), 6) for value in knots_x],
        "knots_y": [round(float(value), 6) for value in knots_y],
        "knot_count": int(len(knots_x)),
        "knot_reproduction_max_diff": max_difference,
    }


def apply_calibration(margins: np.ndarray, calibration: dict) -> np.ndarray:
    """Exactly what serving will do: numpy.interp over the exported knots."""
    return np.interp(
        margins,
        np.asarray(calibration["knots_x"], dtype=np.float64),
        np.asarray(calibration["knots_y"], dtype=np.float64),
    )


def calibration_quality(suitability: np.ndarray, labels: np.ndarray) -> dict:
    target = (labels >= RELEVANT_THRESHOLD).astype(int)
    edges = np.linspace(0.0, 1.0, RELIABILITY_BINS + 1)
    curve = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (suitability >= low) & (
            suitability < high if high < 1.0 else suitability <= high
        )
        count = int(mask.sum())
        curve.append(
            {
                "bin_low": round(float(low), 2),
                "bin_high": round(float(high), 2),
                "count": count,
                "mean_predicted": round(float(suitability[mask].mean()), 4) if count else None,
                "observed_rate": round(float(target[mask].mean()), 4) if count else None,
            }
        )
    return {
        "brier_score": round(float(brier_score_loss(target, suitability)), 4),
        "reliability_curve": curve,
    }


def recommend_threshold(groups, suitability_by_group) -> dict:
    """
    Suggest a value for SUITABILITY_ACCEPTANCE_THRESHOLD from the held-out calibrated
    distribution, with the NO_SUITABLE_LOAN rate each candidate value implies.

    A RECOMMENDATION FOR A HUMAN TO SET. This script does not change config: the
    threshold is the sole definition of "suitable enough to recommend", and moving it
    silently would be the single easiest way to falsify the product.
    """
    truly_without = sum(
        1 for group in groups if not np.any(group.labels >= RELEVANT_THRESHOLD)
    )
    options = []
    for value in [round(0.30 + 0.05 * step, 2) for step in range(13)]:
        blocked = sum(
            1
            for scores in suitability_by_group
            if not np.any(np.asarray(scores) >= value)
        )
        options.append(
            {
                "threshold": value,
                "no_suitable_loan_groups": blocked,
                "no_suitable_loan_rate": round(blocked / len(groups), 4),
            }
        )

    target_rate = truly_without / len(groups)
    best = min(options, key=lambda row: abs(row["no_suitable_loan_rate"] - target_rate))
    return {
        "recommended_threshold": best["threshold"],
        "implied_no_suitable_loan_rate": best["no_suitable_loan_rate"],
        "label_based_no_good_option_rate": round(target_rate, 4),
        "rationale": (
            "the value whose implied NO_SUITABLE_LOAN rate on held-out groups is "
            "closest to the share of groups whose labels contain no candidate at "
            "relevance >= 2"
        ),
        "sweep": options,
        "current_config_value": settings.SUITABILITY_ACCEPTANCE_THRESHOLD,
        "note": "RECOMMENDATION ONLY — a human sets this in app/config.py.",
    }


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("loading groups (rebuilding candidates and features)...")
    groups = load_pair_groups()
    train_all = [group for group in groups if group.split == "train"]
    test_groups = [group for group in groups if group.split == "test"]

    # Carve the calibration hold-out out of TRAIN, by customer.
    rng = random.Random(TRAINING_SEED)
    shuffled = list(train_all)
    rng.shuffle(shuffled)
    cut = int(len(shuffled) * CALIBRATION_SHARE)
    calibration_groups = shuffled[:cut]
    fit_groups = shuffled[cut:]

    print(
        f"groups: {len(groups)} total | fit {len(fit_groups)} | "
        f"calibration {len(calibration_groups)} | test {len(test_groups)}"
    )
    rows = sum(len(group.labels) for group in groups)
    print(f"rows:   {rows} | features {len(PAIR_FEATURE_COLUMNS)}")

    print("\ngroup-aware cross-validation:")
    best_params, best_cv, search_results = group_aware_search(fit_groups)
    print(f"\nbest params  {best_params}  (cv ndcg@5 {best_cv:.4f})")

    model = _fit_ranker(fit_groups, best_params)

    # --- calibration, on groups the ranker never trained on ---
    calibration_margins = np.concatenate(_score_groups(model, calibration_groups))
    calibration_labels = np.concatenate([g.labels for g in calibration_groups])
    calibration = fit_calibration(calibration_margins, calibration_labels)
    print(
        f"\ncalibration: {calibration['knot_count']} knots, "
        f"knot-vs-fitted max diff {calibration['knot_reproduction_max_diff']:.2e}"
    )

    # --- evaluation on the held-out test groups ---
    test_scores = _score_groups(model, test_groups)
    test_labels = [group.labels for group in test_groups]
    model_metrics = evaluate_ranking(test_labels, test_scores)

    baseline_rng = np.random.default_rng(TRAINING_SEED)
    baselines = {
        "random": evaluate_ranking(
            test_labels, [random_scores(g, baseline_rng) for g in test_groups]
        ),
        "cheapest_emi": evaluate_ranking(
            test_labels, [cheapest_emi_scores(g) for g in test_groups]
        ),
        "diagnostic_utility": evaluate_ranking(
            test_labels, [diagnostic_utility_scores(g) for g in test_groups]
        ),
    }

    # THE CEILING. A ranking metric is uninterpretable without one: these labels come
    # from a policy whose inputs are all features, so most of it IS recoverable and a
    # high NDCG is expected. What matters is the distance to the oracle.
    oracle_metrics = evaluate_ranking(
        test_labels, [group.policy_raw_scores for group in test_groups]
    )

    print("\nRANKING METRICS ON HELD-OUT GROUPS (labels are SYNTHETIC)")
    columns = [
        "ndcg@1",
        "ndcg@3",
        "ndcg@5",
        "precision@1",
        "precision@3",
        "recall@5",
        "map@5",
        "mrr",
        "kendall_tau",
    ]
    header = f"{'model':<20}" + "".join(f"{c:>13}" for c in columns)
    print(header)
    print("-" * len(header))

    def _row(name, metrics):
        cells = "".join(
            f"{metrics[c]:>13.4f}" if metrics[c] is not None else f"{'n/a':>13}"
            for c in columns
        )
        print(f"{name:<20}{cells}")

    _row("ML RECOMMENDER", model_metrics)
    for name, metrics in baselines.items():
        _row(name, metrics)
    print("-" * len(header))
    _row("POLICY ORACLE*", oracle_metrics)
    print(
        "  * NOT a baseline to beat: the labeling policy's own score, i.e. the best a"
    )
    print(
        "    model could do by recovering the policy perfectly. The gap to it is what"
    )
    print("    5% label noise and imperfect recovery cost. A model ABOVE it would")
    print("    signal leakage.")

    beat_diagnostic = (
        model_metrics["ndcg@5"] is not None
        and baselines["diagnostic_utility"]["ndcg@5"] is not None
        and model_metrics["ndcg@5"] > baselines["diagnostic_utility"]["ndcg@5"]
    )
    print(
        "\nvs diagnostic-utility baseline on ndcg@5: "
        + ("MODEL WINS" if beat_diagnostic else "MODEL DOES NOT WIN")
    )

    # --- calibration quality and threshold recommendation, on TEST ---
    test_suitability = [apply_calibration(scores, calibration) for scores in test_scores]
    quality = calibration_quality(
        np.concatenate(test_suitability), np.concatenate(test_labels)
    )
    calibration["quality_on_test"] = quality
    print(f"\ncalibration Brier score (test): {quality['brier_score']}")
    print("reliability (calibrated suitability vs observed P(relevance >= 2)):")
    for row in quality["reliability_curve"]:
        if row["count"]:
            print(
                f"  [{row['bin_low']:.1f},{row['bin_high']:.1f})  n={row['count']:4}  "
                f"predicted {row['mean_predicted']:.3f}  observed {row['observed_rate']:.3f}"
            )

    threshold = recommend_threshold(test_groups, test_suitability)
    print(
        f"\nRECOMMENDED SUITABILITY_ACCEPTANCE_THRESHOLD: "
        f"{threshold['recommended_threshold']}"
    )
    print(
        f"  implied NO_SUITABLE_LOAN rate {threshold['implied_no_suitable_loan_rate']} "
        f"vs label-based no-good-option rate {threshold['label_based_no_good_option_rate']}"
    )
    print(f"  current config value {threshold['current_config_value']} (UNCHANGED)")

    # --- artifacts ---
    model_path = MODEL_DIR / Path(settings.RECOMMENDER_MODEL_PATH).name
    model.get_booster().save_model(str(model_path))
    (MODEL_DIR / "loan_recommender_calibration.json").write_text(
        json.dumps(calibration, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "loan_recommender_encoders.json").write_text(
        json.dumps(
            {
                "lender_encoding": get_lender_encoding(),
                "enum_encodings": feature_manifest()["enum_encodings"],
                "unseen_category": feature_manifest()["unseen_category"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest = {
        "model_version": settings.RECOMMENDER_MODEL_VERSION,
        "model_role": (
            "PRIMARY. Its ordering IS the recommendation. Nothing downstream reorders "
            "it; deterministic code may only mark a candidate failed and move on."
        ),
        "relevance_labels_are_synthetic": True,
        "relevance_label_source": "training/labeling.py",
        "reporting_note": (
            "These metrics measure agreement with the synthetic labeling policy, not "
            "real recommendation quality. Agreement between this model and the "
            "diagnostic-utility baseline is not evidence either is correct: they "
            "share ancestry through the labeling policy."
        ),
        "objective": "rank:ndcg",
        "feature_version": settings.FEATURE_VERSION,
        "config_version": settings.CONFIG_VERSION,
        "labeling_policy_version": settings.LABELING_POLICY_VERSION,
        "risk_model_version": settings.RISK_MODEL_VERSION,
        "feature_columns": list(PAIR_FEATURE_COLUMNS),
        "feature_manifest": feature_manifest(),
        "seed": TRAINING_SEED,
        "fit_groups": len(fit_groups),
        "calibration_groups": len(calibration_groups),
        "test_groups": len(test_groups),
        "total_rows": rows,
        "split_source": "phase-7 customer split; calibration carved from train by customer",
        "searched_grid": PARAM_GRID,
        "cv_folds": CV_FOLDS,
        "cv_group_aware": True,
        "cv_results": search_results,
        "cv_best_ndcg@5": best_cv,
        "best_params": best_params,
        "test_metrics": model_metrics,
        "baselines": baselines,
        "policy_oracle_ceiling": oracle_metrics,
        "policy_oracle_note": (
            "The labeling policy's own combined score, evaluated against the noised "
            "labels. It is the ceiling a model recovering the policy perfectly would "
            "reach, not a baseline to beat. A model above it would indicate leakage."
        ),
        "beats_diagnostic_utility_on_ndcg@5": bool(beat_diagnostic),
        "calibration": {
            key: value for key, value in calibration.items() if key != "quality_on_test"
        },
        "calibration_quality": quality,
        "threshold_recommendation": threshold,
    }
    (MODEL_DIR / "loan_recommender_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"\nsaved {model_path}")
    print(f"saved {MODEL_DIR / 'loan_recommender_calibration.json'}")
    print(f"saved {MODEL_DIR / 'loan_recommender_encoders.json'}")
    print(f"saved {MODEL_DIR / 'loan_recommender_manifest.json'}")
    print("\nRELEVANCE LABELS ARE SYNTHETIC — metrics measure agreement with")
    print("training/labeling.py, not real recommendation quality.")


if __name__ == "__main__":
    main()
