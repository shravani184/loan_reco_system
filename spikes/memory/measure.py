"""
SPIKE 3 — serving memory budget, and verification of the two mechanisms it depends on.

Measures resident memory for the PROPOSED serving dependency set against the full set
that a naive build would install, then checks that the two substitutions which make
the small set possible actually work:

  1. an isotonic curve exported as (x, y) knots and applied with numpy.interp
     reproduces sklearn's IsotonicRegression.predict
  2. xgboost's predict(..., pred_contribs=True) gives per-feature contributions that
     sum to the margin, so the shap package is not needed for TreeSHAP

Each measurement runs in its own subprocess, because imports cannot be undone.

SPIKE ONLY.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

SERVING = ["numpy", "xgboost", "fastapi", "pydantic", "uvicorn"]
FULL = SERVING + ["pandas", "sklearn", "shap"]

PROBE = textwrap.dedent(
    """
    import json, os, resource, sys
    import psutil

    proc = psutil.Process(os.getpid())
    baseline = proc.memory_info().rss

    mods = json.loads(sys.argv[1])
    for m in mods:
        __import__(m)
    after_import = proc.memory_info().rss

    after_model = after_import
    after_predict = after_import
    if "xgboost" in mods:
        import numpy as np
        import xgboost as xgb
        rng = np.random.default_rng(0)
        X = rng.normal(size=(400, 40)).astype("float32")
        y = (X[:, 0] + rng.normal(scale=0.3, size=400) > 0).astype(int)
        booster = xgb.train(
            {"max_depth": 6, "objective": "binary:logistic", "verbosity": 0},
            xgb.DMatrix(X, label=y), num_boost_round=200,
        )
        booster.save_model("/tmp/spike_model.json")
        del booster
        loaded = xgb.Booster()
        loaded.load_model("/tmp/spike_model.json")
        after_model = proc.memory_info().rss
        loaded.predict(xgb.DMatrix(X[:1]))
        after_predict = proc.memory_info().rss

    print(json.dumps({
        "baseline_mb": round(baseline / 1024**2, 1),
        "after_import_mb": round(after_import / 1024**2, 1),
        "after_model_load_mb": round(after_model / 1024**2, 1),
        "after_predict_mb": round(after_predict / 1024**2, 1),
        "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }))
    """
)


def probe(mods: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", PROBE, json.dumps(mods)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def verify_isotonic_knots() -> dict:
    """Knots + numpy.interp must reproduce sklearn's isotonic predictions."""
    code = textwrap.dedent(
        """
        import json
        import numpy as np
        from sklearn.isotonic import IsotonicRegression

        rng = np.random.default_rng(7)
        margins = np.sort(rng.normal(size=600) * 3)
        labels = (margins + rng.normal(scale=1.2, size=600) > 0).astype(float)

        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(margins, labels)

        # export: the knots sklearn itself exposes
        knots_x = iso.f_.x.tolist()
        knots_y = iso.f_.y.tolist()

        probe_points = np.linspace(margins.min() - 2, margins.max() + 2, 500)
        sk = iso.predict(probe_points)
        np_side = np.interp(probe_points, knots_x, knots_y)

        monotone = bool(np.all(np.diff(np_side) >= -1e-12))
        print(json.dumps({
            "knots": len(knots_x),
            "max_abs_diff": float(np.max(np.abs(sk - np_side))),
            "monotone": monotone,
            "in_unit_interval": bool(np_side.min() >= 0.0 and np_side.max() <= 1.0),
        }))
        """
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def verify_pred_contribs() -> dict:
    """XGBoost's native TreeSHAP must sum to the margin, removing the shap package."""
    code = textwrap.dedent(
        """
        import json
        import numpy as np
        import xgboost as xgb

        rng = np.random.default_rng(11)
        X = rng.normal(size=(300, 12)).astype("float32")
        y = (X[:, 0] * 2 + X[:, 3] - rng.normal(size=300) > 0).astype(int)
        booster = xgb.train(
            {"max_depth": 4, "objective": "binary:logistic", "verbosity": 0},
            xgb.DMatrix(X, label=y), num_boost_round=60,
        )
        d = xgb.DMatrix(X[:50])
        contribs = booster.predict(d, pred_contribs=True)   # (rows, features + bias)
        margins = booster.predict(d, output_margin=True)

        print(json.dumps({
            "shape": list(contribs.shape),
            "features_plus_bias": int(contribs.shape[1]),
            "max_abs_reconstruction_error": float(np.max(np.abs(contribs.sum(axis=1) - margins))),
            "shap_package_needed": False,
        }))
        """
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> None:
    print("measuring serving dependency set:", ", ".join(SERVING))
    serving = probe(SERVING)
    print("measuring full/naive dependency set:", ", ".join(FULL))
    full = probe(FULL)

    saving = full["after_predict_mb"] - serving["after_predict_mb"]
    print()
    print("=" * 72)
    print("RESIDENT MEMORY (MB)")
    print("=" * 72)
    print(f"{'stage':<26}{'serving set':>14}{'full set':>14}{'saving':>12}")
    for key, label in [
        ("baseline_mb", "interpreter baseline"),
        ("after_import_mb", "after imports"),
        ("after_model_load_mb", "after model load"),
        ("after_predict_mb", "after one prediction"),
        ("peak_mb", "peak RSS"),
    ]:
        print(f"{label:<26}{serving[key]:>14.1f}{full[key]:>14.1f}{full[key] - serving[key]:>12.1f}")

    print()
    print(f"saving at steady state: {saving:.1f} MB")

    print()
    print("=" * 72)
    print("MECHANISM 1 — isotonic knots + numpy.interp (removes scikit-learn)")
    print("=" * 72)
    iso = verify_isotonic_knots()
    print(json.dumps(iso, indent=2))
    iso_ok = iso["max_abs_diff"] < 1e-9 and iso["monotone"] and iso["in_unit_interval"]
    print("VERIFIED" if iso_ok else "REFUTED")

    print()
    print("=" * 72)
    print("MECHANISM 2 — xgboost pred_contribs (removes the shap package)")
    print("=" * 72)
    contribs = verify_pred_contribs()
    print(json.dumps(contribs, indent=2))
    contribs_ok = contribs["max_abs_reconstruction_error"] < 1e-4
    print("VERIFIED" if contribs_ok else "REFUTED")

    ceiling = int((serving["after_predict_mb"] * 1.6) // 10 * 10)
    print()
    print("=" * 72)
    print(f"RECOMMENDED MEMORY_CEILING_MB = {ceiling}")
    print(f"  (measured serving footprint {serving['after_predict_mb']:.0f} MB "
          f"+ 60% headroom for request handling and fragmentation)")
    print("=" * 72)

    out = {
        "serving": serving, "full": full, "saving_mb": saving,
        "isotonic": iso, "isotonic_verified": iso_ok,
        "pred_contribs": contribs, "pred_contribs_verified": contribs_ok,
        "recommended_ceiling_mb": ceiling,
    }
    with open("measurements.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote measurements.json")


if __name__ == "__main__":
    main()
