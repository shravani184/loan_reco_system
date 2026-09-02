# SPIKE 3 — Serving memory budget: FINDINGS

**Risk addressed:** CONTEXT.md §17.2 — pandas + scikit-learn + shap + XGBoost +
FastAPI loaded together approach a 512 MB free-tier ceiling before a model is loaded,
and discovering it at deployment means rewriting modules that already assume DataFrames.

**Status: RESOLVED.** The proposed serving set measures **186 MB**, both substitution
mechanisms are verified, and the recommended ceiling is **290 MB**.

Verified by:

```
python3 spikes/memory/measure.py    ->  measurements.json
```

Environment: Linux container, Python 3.11.15, numpy 2.4.4, xgboost 3.2.0,
scikit-learn 1.8.0, shap 0.51.0, pandas 3.0.2.

---

## 1. Measured resident memory

| Stage | Serving set | Full / naive set | Saving |
|---|---:|---:|---:|
| Interpreter baseline | 12.0 MB | 12.1 MB | 0.1 MB |
| After imports | 177.9 MB | 302.6 MB | **124.7 MB** |
| After model load | 186.2 MB | 310.6 MB | 124.4 MB |
| After one prediction | 186.3 MB | 310.7 MB | 124.4 MB |
| Peak RSS | 189.2 MB | 313.5 MB | 124.3 MB |

- **Serving set:** numpy, xgboost, fastapi, pydantic, uvicorn
- **Full set:** the above plus pandas, scikit-learn, shap

**Dropping pandas, scikit-learn and shap from the serving image saves 124 MB — about
40% of the naive footprint, and roughly a quarter of a 512 MB tier.**

Loading a 200-tree booster from JSON cost only **8.3 MB**, so v2.0's two artifacts add
roughly 17 MB, not the tens of MB that would make this tight.

## 2. Both mechanisms verified

The small serving set is only possible because two substitutions work. Both were
tested rather than assumed.

**Mechanism 1 — isotonic calibrator as knots + `numpy.interp` (removes scikit-learn):**

```json
{"knots": 32, "max_abs_diff": 0.0, "monotone": true, "in_unit_interval": true}
```

`numpy.interp` over the exported `(x, y)` breakpoints reproduces
`IsotonicRegression.predict` **exactly** — maximum absolute difference 0.0 across 500
probe points, including outside the training range where `out_of_bounds="clip"`
applies. The result stays monotone and inside `[0, 1]`. **VERIFIED.**

A useful side effect: 32 knots is a small, human-readable, diffable artifact. A
calibration change between model versions can be reviewed as a table rather than as an
opaque pickle.

**Mechanism 2 — XGBoost native TreeSHAP (removes the `shap` package):**

```json
{"shape": [50, 13], "features_plus_bias": 13,
 "max_abs_reconstruction_error": 2.9e-06, "shap_package_needed": false}
```

`booster.predict(dmatrix, pred_contribs=True)` returns one contribution per feature
plus a bias term, and they sum to the model margin to within 2.9e-06 — exact SHAP
values for tree ensembles, with no extra dependency. **VERIFIED.**

## 3. Recommended configuration

```
MEMORY_CEILING_MB = 290
```

Measured serving footprint of 186 MB plus 60% headroom for concurrent request
handling, allocator fragmentation and the second model artifact. This leaves
comfortable margin against a 512 MB tier.

**Worker count is a memory decision, not a throughput one.** Each gunicorn/uvicorn
worker loads its own copy of both models, so 2 workers ≈ 372 MB and 3 would exceed the
tier. Default to **one worker** on a 512 MB target.

## 4. What Phase 0 must adopt

| Decision | Consequence if skipped |
|---|---|
| `requirements.txt` (serving) excludes pandas, scikit-learn, shap, matplotlib | +124 MB |
| `app/ml/features.py` returns NumPy arrays; catalogue loads via stdlib `csv` | pandas becomes unremovable |
| Calibrator exported as knots, applied with `numpy.interp` | scikit-learn becomes unremovable |
| Categorical encoding as a saved dict, not a pickled `LabelEncoder` | scikit-learn becomes unremovable |
| Contributions via `pred_contribs=True` | shap becomes unremovable |
| Models saved as XGBoost JSON, not pickle | joblib + pickle-version fragility |
| `tests/test_serving_imports.py` asserting no pandas/sklearn/shap in `sys.modules` | the boundary erodes silently |

The last row is what makes the rest durable. Every other decision is one careless
import away from being undone.

## 5. Risks remaining

- Measured on this Linux container, not on the actual PaaS target. Absolute numbers
  will shift with the platform's Python build and allocator; the **124 MB saving** and
  the mechanism verifications are the transferable results. P17 re-measures on the
  live instance — that is the third checkpoint.
- The probe loads one booster. Two models plus a calibrator were extrapolated at
  ~17 MB from the measured 8.3 MB single-model cost, not measured together. P11
  measures the real pair.
- `numpy` 2.x was used. A pinned older numpy could differ; the pin is set in P0 and
  the measurement should be re-run if it changes.
- Memory under concurrent load was not measured — only single-request steady state.
  The 60% headroom is a judgement, not a measurement, and P17 should verify it under
  at least a few concurrent requests.
