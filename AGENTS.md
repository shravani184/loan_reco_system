# AGENTS.md

Operating rules for any AI agent working in this repository.
**Read CONTEXT.md first, then this file, before every task.**

**Architecture version: 2.0 (ML-first).** The primary ML recommender chooses the recommendation; deterministic code decides feasibility, computes every rupee, and enforces policy. If any instruction you receive implies a deterministic score picks the final loan, it is v1.0 language — stop and report the conflict.

---

## 0. Prime directives

1. **Stay in your phase.** Work only on the phase named in the current prompt. Do not start the next phase, do not "prepare" for it, do not stub out its files.
2. **Do not assume — surface.** If a requirement is ambiguous, stop and name the ambiguity. Do not silently pick an interpretation.
3. **Minimum code that solves the problem.** No speculative abstractions, no unrequested configurability, no error handling for impossible scenarios. If 200 lines could be 50, write 50.
4. **Surgical changes.** Touch only what the task requires. Don't reformat, refactor, or "improve" adjacent code. Match existing style even if you'd write it differently. If you notice unrelated dead code, mention it — don't delete it.
5. **Never violate a CONTEXT.md non-negotiable**, even if it would make a task easier. If a task appears to require violating one, stop and report the conflict.
6. **Never quietly move authority.** Any change that lets deterministic code reorder, veto or adjust the ML ranking, or that lets ML compute a rupee figure or skip a hard rule, is an architectural violation regardless of how well it performs. Report it instead of writing it.

---

## 1. Phased development — the mandatory workflow

**This project is built strictly one phase at a time.** It is never built as one large implementation. Every architectural component is independently implemented, tested, verified and recorded before the project moves forward.

### 1.1 The documentation is the source of truth

`CONTEXT.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` and `PHASE_STATUS.md` are authoritative. Before starting **any** development phase:

1. Read `CONTEXT.md` completely.
2. Read `IMPLEMENTATION_PLAN.md` far enough to understand the active phase and its dependencies.
3. Read this file for the rules and constraints.
4. Read `PHASE_STATUS.md` to determine the current project state.
5. Confirm which phase is active.
6. Implement **only that phase**.

Never rely on assumptions from a previous conversation, a previous implementation, or recalled context when the requirement is documented in these files. If your recollection and the files disagree, the files win.

### 1.2 The seven steps, every phase, in order

```
Step 1  READ          CONTEXT.md, IMPLEMENTATION_PLAN.md, AGENTS.md, PHASE_STATUS.md
Step 2  CONFIRM SCOPE state the phase, objective, what must be built, what must NOT
                      be built, dependencies, and exit criteria — before writing code
Step 3  IMPLEMENT     only this phase; minimal, focused changes
Step 4  TEST          phase tests, then fix root causes, then the FULL suite
Step 5  VERIFY        every exit criterion, by a command actually run
Step 6  RECORD        update PHASE_STATUS.md with the full record (1.4)
Step 7  STOP          do not begin the next phase; wait to be told to proceed
```

Step 2 is not ceremony. Writing down what must *not* be built is what keeps a phase from quietly absorbing the next one.

### 1.3 Do not, under any circumstances

- Start the next phase early, or "prepare" for it.
- Create placeholder or stub implementations for future phases.
- Build a component that belongs to a later phase. If you need one to understand the current phase, use its **documented interface, schema or contract** from `CONTEXT.md` / the phase prompt — do not implement it.
- Introduce speculative features, or refactor unrelated code.
- Skip a test because the implementation looks correct.
- Mark a phase complete on expectation rather than verification.
- Start a phase whose dependency is `NOT_STARTED`, `IN_PROGRESS` or `BLOCKED`, unless the plan explicitly marks that dependency optional.
- Reorder phases because a later one looks easier. The order is dependency-driven.

A phase is **not** complete because the code is written, the app starts, one test passes, the output looks right, or it "should work". Completion means verified.

### 1.4 `PHASE_STATUS.md` is mandatory and is the record

It is the single source of truth for implementation progress and is maintained throughout. Status values: `NOT_STARTED` | `IN_PROGRESS` | `BLOCKED` | `DONE`.

- Set your phase to `IN_PROGRESS` before writing code.
- Set `DONE` **only** when every exit criterion is verified by an actual command you ran (tests passing, endpoint returning, script executing, metric printed). Never on the belief that it should work.
- Never edit another phase's row. Never mark `DONE` with any test failing anywhere in the repo, including tests from earlier phases.

On completing a phase, append its record beneath the table containing: phase name; status; whether exit criteria were met; what was implemented; the exact commands used to verify and their results; important implementation decisions; limitations and unresolved issues; and what the next phase needs to know.

If a genuine blocker stops you: set `BLOCKED`, write the exact blocker in the record, and **stop**. Do not work around it by violating the architecture or silently weakening a requirement. A blocked phase is an acceptable outcome; a falsely green one is not.

### 1.5 Documentation and implementation must not drift

If implementation reveals that a requirement, schema, interface or phase definition is wrong or ambiguous:

1. Do not silently change the architecture.
2. Name the conflict explicitly.
3. Decide whether the documentation needs to change.
4. Update the appropriate specification only when justified.
5. Record the change in `PHASE_STATUS.md`.
6. Re-check that `CONTEXT.md` and `IMPLEMENTATION_PLAN.md` remain consistent with each other and with the code.

At all times: **the code implements the documented architecture, and the documentation describes the implemented architecture.**

### 1.6 Tracker format

The repo contains `PHASE_STATUS.md`. It is the single source of truth for progress.

**Format — one row per phase, agent updates only its own row:**

```
| Phase | Name | Status | Exit criteria met | Notes |
|-------|------|--------|-------------------|-------|
| P0 | Scaffold, Schemas, Config | DONE | yes | - |
| P1 | Financial Intelligence | IN_PROGRESS | no | - |
```

Status values: `NOT_STARTED` | `IN_PROGRESS` | `BLOCKED` | `DONE`

The table gives the at-a-glance state; the per-phase record beneath it (§1.4) gives the detail. Both are updated at Step 6, together.

---

## 2. Module responsibility map

One module, one responsibility. Cross-module calls follow the pipeline direction only — never backwards, never sideways.

| Module | Path | Owns | Must not |
|---|---|---|---|
| Schemas | `app/schemas/` | All Pydantic models and enums | Contain business logic |
| Config | `app/config.py` | All settings, weights, thresholds, caps, grids | Be bypassed by direct env reads |
| Financial Intelligence | `app/core/financial.py` | Financial metrics + features | Call models, touch loans, score |
| Portfolio Intelligence | `app/core/portfolio.py` | Portfolio metrics + features | Recommend liquidation, compute EMI, score |
| Personalization store | `app/personalization/store.py` | Persistence of pseudonymous history | Score, rank, store raw PII |
| Personalization context | `app/personalization/context.py` | History-derived feature block | Decide anything; be a second recommender |
| Eligibility | `app/core/eligibility.py` | Hard eligibility rules, reason codes | Score, rank, compute EMI, drop products |
| Finance math | `app/core/finance_math.py` | **The only EMI/interest implementation** | Enumerate, rank, decide |
| Candidate generation | `app/core/candidates.py` | Candidate enumeration, feasibility, dominance pruning | Rank by preference, call any model |
| Guardrails | `app/core/guardrails.py` | Risk-appetite policy caps, pass/fail | Compute EMI, rank, reorder, delete options |
| Validation | `app/core/validation.py` | Deterministic re-verification of the ML pick | Re-rank, silently correct a candidate |
| Diagnostics | `app/core/diagnostics.py` | `diagnostic_utility_score` (fallback + audit only) | Override ML during normal operation |
| Mismatch analysis | `app/core/mismatch.py` | Structured no-suitable-loan reasons, coverage funnel | Invent a reason not produced by a rule/model |
| Orchestrator | `app/core/recommendation.py` | Pipeline order, validation walk, trace assembly | Contain any formula that reorders candidates |
| Features | `app/ml/features.py` | Feature assembly (shared train+serve), column contract | Duplicate logic elsewhere |
| Risk model | `app/ml/risk.py` | Risk inference (a feature source) | Decide eligibility, select, or block |
| **Primary recommender** | `app/ml/recommender.py` | **Candidate scoring, suitability calibration, ranking** | Filter, re-check eligibility, compute money |
| XAI | `app/explain/xai.py` | Feature contributions via XGBoost native TreeSHAP | Produce prose; import the `shap` package |
| Prompts | `app/explain/prompts.py` | Every prompt string in the system | Contain logic or computed values |
| LLM | `app/explain/llm.py` | Natural-language explanation | Compute, decide, or invent numbers |
| API | `app/api/` | Routing, request/response | Contain business logic |
| Training | `training/` | Offline data generation, labeling, training | Be imported by anything under `app/` |

**Rule:** if you need a value another module owns, call that module. Never recompute it locally. Two implementations of EMI in this repo is a defect regardless of whether they agree.

**Authority rule (the v2.0 rule):**
- Only `app/ml/recommender.py` may produce the ordering of candidates during normal operation.
- Only `app/core/eligibility.py`, `app/core/candidates.py`, `app/core/validation.py` and `app/core/guardrails.py` may exclude a candidate, and only by a documented pass/fail rule — never by a score.
- `app/core/diagnostics.py` may produce an ordering **only** when the recommender is unavailable, and only with `recommendation_source = DETERMINISTIC_FALLBACK` set.
- `app/core/recommendation.py` may reorder nothing. It walks the ranking it is given.

**Model loading rule:** ML models are never loaded at module import. Each ML module exposes an explicit `load_models()` plus a lazy accessor. The API lifespan handler calls `load_models()` once at startup. Importing an ML module must never touch the filesystem — this keeps test collection fast and deployment startup predictable.

**Feature contract rule:** every model artifact ships a manifest containing `FEATURE_VERSION` and the exact feature column order. At load time the serving code asserts the manifest matches `app/ml/features.py`. A mismatch is a startup failure with a clear message — never a warning, never a silent reorder, never a truncation to the shorter list.

**Test data rule:** tests never read from `data/` and never require a trained model. All test inputs come from `tests/fixtures.py`. Any phase needing a loan catalogue before the data-generation phase uses the in-memory mock catalogue there — it does not generate a CSV early and does not skip ahead. Tests that need model behaviour use a stub scorer injected through the documented accessor, not a real `.pkl`.

**Dependency rule:** every dependency is pinned to an exact version in `requirements.txt` at the time it is introduced. Adding an unpinned dependency breaks the deployment phase and is a defect.

---

## 3. Datatype ownership rule

**Every data structure crossing a module boundary is a Pydantic model defined in `app/schemas/`. Nothing crosses a boundary as a raw dict.**

- Each schema has exactly one owning module (the one that produces it). Only the owner may change its shape.
- To add a field: add it to the schema in `app/schemas/`, then update the owning producer, then consumers. Never attach an undeclared field to an object in passing.
- Money is `float` in rupees, or `int` in paise if precision is needed — pick one in P0 and never mix.
- Enums are defined once in `app/schemas/enums.py` and imported everywhere. **Never compare against raw strings.** The v2.0 enum set is at minimum:
  `RiskAppetite`, `FinancialHealth`, `RiskClass`, `FinancingStrategy`, `LoanPurpose`, `AssetType`,
  `EligibilityStatus`, `RecommendationStatus`, `RecommendationSource`, `CandidateOutcome`, `MismatchReasonCode`.
- `RecommendationStatus` and `RecommendationSource` are **separate fields on separate axes**. Status says what happened; source says who decided. Never encode a fallback as a status value, and never encode a status as a source value.
- The ML layer converts schemas to feature vectors in exactly one place: `app/ml/features.py`. Column order is defined there and is the contract for both training and serving.
- A `Candidate` is a fully-specified financing configuration (product, amount, tenure, strategy, plus every computed financial field). The recommender scores candidates, not products. A schema change that reduces a candidate to a product id is an architectural regression.

---

## 4. Config loading rule

**One config module. One load. No exceptions.**

- All settings live in `app/config.py` as a Pydantic `Settings` object loaded once at import.
- **Flat scalars** (paths, keys, URLs, versions, log level) come from environment variables sourced from `.env`.
- **Complex structures** (guardrail caps, enumeration grids, asset-type maps, diagnostic weights, thresholds) are typed defaults defined in the `Settings` class itself, not in `.env` — env files parse nested structures badly. They may optionally be overridden by a JSON file whose path comes from `.env`, but class defaults must work with no file present.
- Both halves are equally config: business logic may never hardcode either.
- **Never call `os.getenv` outside `app/config.py`.**
- **Never hardcode** a threshold, weight, interest rate, file path, model path, API key, cap, grid step, or acceptance threshold inline in business logic. If you catch yourself typing a magic number, it belongs in config.
- Config values that shape a decision — guardrail caps, eligibility thresholds, `SUITABILITY_ACCEPTANCE_THRESHOLD`, diagnostic weights, candidate grids — are stamped with `CONFIG_VERSION` into every decision trace.
- Version strings that must appear in every trace: `CONFIG_VERSION`, `FEATURE_VERSION`, `PROMPT_VERSION`, and both model versions.
- Secrets never enter the repo. `.env` is gitignored; `.env.example` is committed with placeholder values.

---

## 5. Prompt string rule

**All LLM prompt text lives in `app/explain/prompts.py`. Nowhere else.**

- No prompt string is ever written inline in business logic, in an f-string at a call site, or in a route handler.
- Prompts are named constants or functions returning a string, versioned via `PROMPT_VERSION`.
- Prompts receive **only** a validated structured payload of already-computed values. Never pass raw customer PII, raw dataframes, or unvalidated user text into a prompt.
- Every prompt must include an explicit instruction that the model may not compute, estimate, or introduce any number not present in the payload, may not name a loan product that is not in the payload, and may not author a reason for a rejection or mismatch.
- **Payloads carry display strings.** Every figure enters a prompt both as a number and as a pre-formatted string (`"₹6,00,000"`, `"48 months"`, `"8.0%"`), and the prompt instructs the model to reproduce them verbatim. Prevention is the primary mechanism; the guard is the safety net.
- **Numeric-grounding guard (mandatory):** after every LLM response, run `verify_numeric_grounding(response, payload)`. It extracts **financial figures** from the response, normalizes formats (`6,00,000` / `6 lakh` / `₹6L` → `600000`; `8%` ↔ `0.08`; `4 years` → `48` months), ignores ordinals, list markers, dates and numbers inside words, and treats a token as financial only when it sits in a financial context (currency symbol, percent sign, or a cue word such as EMI / interest / rate / tenure / months / years / score / lakh / crore) or exceeds a magnitude floor.
- **The guard returns one of three outcomes, not a boolean:**

  | Outcome | Meaning | Action |
  |---|---|---|
  | `GROUNDED` | every extracted financial figure matched the payload | accept |
  | `UNVERIFIED` | a token could not be confidently parsed or classified | **accept**, flag on the response, log the token |
  | `UNGROUNDED` | a token parsed confidently as a financial figure with no payload match | reject, fall back to the template explainer, log the figure |

  An unparseable token is a limitation of the guard, not evidence of a hallucination — it must not cost the user their explanation. Only a confident parse with no match rejects. Collapsing these three back into a boolean is the change that makes the guard untrustworthy, and is forbidden.
- Matching is done against a **generously expanded accepted set** built from each payload figure (lakh/crore forms, sensible roundings, percent/decimal duals, month/year duals), not by attempting to parse every possible spelling in the response.
- **The guard is locked in by `tests/data/grounding_corpus.jsonl`.** It must reject 100% of the labelled `UNGROUNDED` cases and falsely reject **zero** labelled `GROUNDED` cases. When a false positive appears, fix the normalizer and add a corpus case. Never widen a tolerance, never disable the guard, never delete a corpus case.
- The guard may not be disabled or bypassed to make a demo pass. If it produces false positives, the normalizer is the bug.
- **Entity-grounding guard (v2.0 addition):** the same check applies to named entities. A product name or lender name in the response that is not in the payload is a rejection, on the same path as an ungrounded number. The LLM may not invent a catalogue product, and may not soften or re-author a `MismatchReasonCode` into a different reason.
- The LLM is never in the path that produces a value or selects an option — only in the path that describes one.

---

## 6. ML rules

These rules exist because "ML is the primary decision maker" is easy to claim and easy to quietly undo.

1. **The recommender ranks; nothing downstream reorders.** Deterministic code may mark a candidate as failed and move to the next one. It may not change relative order, apply a bonus, blend scores, or "adjust" a suitability value.
2. **The recommender never filters.** It receives eligible, feasible candidates and scores all of them. If handed an empty list, it returns an empty list. It never re-checks eligibility, and it never computes a rupee figure.
3. **Risk PD is a feature.** `app/ml/risk.py` output enters the recommender's feature vector and the user-facing risk disclosure. It may not gate, veto, or select.
4. **One feature path.** Training and serving import the same function from `app/ml/features.py`. Writing a second feature-assembly path in `training/` is the specific defect this rule exists to prevent.
5. **Suitability is calibrated before it is thresholded.** Raw ranker margins are never compared against `SUITABILITY_ACCEPTANCE_THRESHOLD`; only the calibrated `[0,1]` value is. The calibrator ships inside the recommender artifact bundle and is applied at inference, not re-fitted at runtime.
6. **Two models, and no more.** The calibrator, the personalization feature block, the mismatch analyzer and the diagnostic score are not models and may not become models. Adding a third model requires an explicit, approved architectural decision recorded in CONTEXT.md.
7. **The ranker is evaluated as a ranker.** Report NDCG@k, Precision@k, MAP, MRR and calibration quality. Do not report classification accuracy for the recommender. Report the random / cheapest-EMI / diagnostic-utility baselines alongside it, including when the model loses to one.
8. **Never train at runtime.** No retraining, no incremental fitting, no `partial_fit` inside `app/`. Training code lives in `training/` and is never imported by `app/`.
9. **Synthetic labels are declared.** Any manifest, README section or report describing model quality states that relevance labels are synthetic and that metrics measure agreement with the labeling policy. Reporting NDCG without that sentence is incomplete reporting.
10. **Agreement is not validation.** The ML recommendation agreeing with the diagnostic utility score proves nothing — they share ancestry through the labeling policy. Never cite that agreement as evidence the model works.
11. **The labeling policy is built to be falsifiable.** It is decomposed into a disqualifier mask, independent normalized sub-scores, a documented combination and a stress demotion — never one monolithic scoring function. Grades are assigned by rank within the customer's own candidate group, not by absolute cutoffs. Its invariants (CONTEXT.md 17.1) are written **before** the policy and tested with property-based generation. It carries `LABELING_POLICY_VERSION`, stamped into the dataset manifest and both model manifests.
12. **Feature builders return NumPy arrays.** No DataFrame crosses into `app/`. The same functions serve training, which may hold pandas on its own side of the boundary but never passes one across it.

---

## 7. Fallback rules

1. Every path that can degrade must set an explicit flag that reaches the API response: `recommendation_source`, plus per-signal flags (e.g. risk PD imputed, SHAP degraded to feature importances, LLM explanation degraded to template).
2. A missing or corrupt model artifact is logged with the path and the exception, then handled — never swallowed and never allowed to 500 the primary endpoint.
3. In `DETERMINISTIC_FALLBACK` mode the ML suitability field is `null`. Never emit a rescaled diagnostic score in a field named for ML suitability.
4. The UI and the LLM explanation must both reflect the fallback. A fallback result described to the user as an ML recommendation is a correctness defect, not a cosmetic one.
5. Fallback code paths are tested by test, not by hope: a test must delete/rename the artifact path and assert the flag, the ordering source, and a still-valid response.

---

## 8. Catalogue mismatch rules

1. **Never manufacture a recommendation.** If no candidate clears the suitability threshold, validation and guardrails, return `NO_SUITABLE_LOAN`. Returning the best of a bad set because a score exists is a defect.
2. **Never invent a reason.** Every `MismatchReasonCode` must be traceable to a rule evaluation that actually fired or a score that was actually computed, and must carry the observed value and the threshold it failed.
3. **Distinguish the four stop points.** `NO_ELIGIBLE_PRODUCTS`, `NO_FEASIBLE_CANDIDATES`, `ALL_CANDIDATES_BLOCKED` and `NO_SUITABLE_LOAN` are different answers to "how far did my request get". Collapsing them into one status is a defect.
4. **Always emit the coverage funnel**, on success and on failure alike.
5. **Blocked is not hidden.** When the ML top choice fails validation or a guardrail, it is recorded in the trace as `ml_top_choice_blocked` with the rule name and cap value, and surfaced in the response.
6. Mismatch reasons are phrased as product-fit statements, never as a formal credit decision about the person.

---

## 9. Decision trace rules

A response without a complete trace is incomplete, and a phase that ships one is not `DONE`. The trace must contain, at minimum:

- every catalogue product with its eligibility outcome and reason code
- candidate counts: generated, infeasible, dominance-pruned, scored
- risk class, PD, and risk model version
- the full ML-ranked candidate list with calibrated suitability scores
- the validation walk in ML rank order, one row per candidate attempted, with validation and guardrail results
- `ml_top_choice_blocked` when applicable, with the exact rule and cap
- the selected candidate and why the walk stopped there
- the winner's diagnostic utility score, labelled advisory
- the catalogue coverage funnel
- `recommendation_status`, `recommendation_source`
- `CONFIG_VERSION`, `FEATURE_VERSION`, `PROMPT_VERSION`, both model versions

Traces contain no raw PII. Identify a customer by pseudonymous id, never by name, contact details or identity numbers.

---

## 10. Handling test failures

**A failing test is information. Never make it disappear.**

Procedure, in order:

1. **Read the actual error.** Do not guess from the test name.
2. **Reproduce it in isolation** — run that single test.
3. **Decide which is wrong: the code or the test.** State your conclusion explicitly before changing anything.
4. **Fix the root cause.** If the code is wrong, fix the code. If the test genuinely encodes a wrong expectation, fix the test **and say clearly in your report that you changed a test and why.**
5. **Re-run the full suite**, not just the one test — confirm you broke nothing else.

**Forbidden:**
- Deleting, skipping, `xfail`-ing, or commenting out a failing test to get green.
- Loosening an assertion (widening a tolerance, changing `==` to `>=`, asserting `is not None` instead of the value) to make it pass.
- Wrapping failing code in try/except to swallow the error.
- Marking a phase `DONE` with any test failing.
- **Lowering `SUITABILITY_ACCEPTANCE_THRESHOLD`, widening a guardrail cap, or relaxing an eligibility rule so a demo customer produces a recommendation.** If a demo customer legitimately has no suitable loan, that is a correct result and the demo shows the mismatch explanation. Tuning policy to force a recommendation is falsifying the product.

If a test cannot be fixed within the phase, set the phase `BLOCKED` and report it. A blocked phase is an acceptable outcome; a falsely green suite is not.

**Tests must verify behaviour, not existence.** `assert result is not None` is not a test. Assert the value, the enum, the ordering, the flag, the reason code, the count. A test that would still pass if the function returned a constant is not a test.

---

## 11. Handling lint / ActionLint / CI errors

**Fix your own mess. Don't clean up the neighborhood.**

- Fix every lint error **introduced by your change** before marking a phase done.
- Do not fix pre-existing lint errors in files you didn't touch — report them instead.
- Do not add blanket `# noqa`, `# type: ignore`, or eslint-disable to silence an error. If a suppression is genuinely warranted, scope it to the single line and add a comment explaining why.
- Do not change lint configuration (`.flake8`, `ruff.toml`, `.eslintrc`) to make an error go away. Configuration changes require explicit approval.
- **ActionLint / GitHub Actions:** workflow YAML errors are fixed by correcting the workflow, never by disabling the check or removing the job. Common causes: wrong indentation, undefined `secrets.*` reference, invalid `runs-on`, missing `steps:` key, shell quoting in `run:` blocks. Read the actionlint line/column output — it is precise.
- Never commit with a failing CI job and a note to fix it later.

---

## 12. Definition of Done (applies to every phase)

A phase is `DONE` only when **all** of the following are true and verified by commands actually executed:

- [ ] Every exit criterion in the phase prompt is met.
- [ ] Tests for this phase exist, assert real values, and pass.
- [ ] The full test suite passes (no regressions).
- [ ] No lint errors introduced.
- [ ] No `os.getenv` outside config; no inline prompt strings; no hardcoded thresholds, caps or grid values.
- [ ] No raw dicts crossing module boundaries; no raw-string enum comparisons.
- [ ] Any new dependency is pinned in `requirements.txt`.
- [ ] No ML model loaded at module import; no training code imported by `app/`.
- [ ] Serving import graph clean: after importing the application, `sys.modules` contains no `pandas`, `sklearn` or `shap`.
- [ ] Memory measured and within the configured ceiling, for the phases that require it (P11, P13, P17).
- [ ] No deterministic score reorders the ML ranking; no ML output produces a rupee figure.
- [ ] Every degradation path sets a visible flag.
- [ ] No CONTEXT.md non-negotiable violated.
- [ ] `PHASE_STATUS.md` updated.
- [ ] A short report written: what was built, what was assumed, what was left out, what the next phase should know.

---

## 13. Reporting format (end of every phase)

```
PHASE: Px - <name>
STATUS: DONE | BLOCKED
BUILT: <what now exists and works>
VERIFIED BY: <exact commands run and their result>
METRICS: <for ML phases: the ranking/classification metrics actually printed, with baselines>
ASSUMPTIONS: <anything you decided that wasn't specified>
NOT DONE: <anything deliberately deferred, and to which phase>
ARCHITECTURAL NOTES: <anything that touched the ML/deterministic authority boundary>
NEXT PHASE NEEDS TO KNOW: <interfaces, gotchas, data shapes, feature/column contracts>
```

Never report success you have not verified by running something. Never report a metric you did not print.

---

## 14. Serving dependency and memory budget

The deployed service must fit a small memory ceiling. That is achieved by keeping the serving import graph small from the first phase, not by trimming at deployment. See CONTEXT.md §13 and §17.2.

**Rules:**

1. **`app/` may not import `pandas`, `sklearn`, `shap`, `matplotlib`, or anything under `training/`.** Enforced by a test that imports the application and inspects `sys.modules`. This is not stylistic — it is the memory budget.
2. Two requirement files: `requirements.txt` (serving) and `requirements-train.txt` (offline). Both fully pinned. Add a dependency to the correct one; adding a training tool to the serving file is a defect.
3. Feature assembly returns NumPy arrays. The catalogue loads via the stdlib `csv` module into Pydantic models.
4. The calibrator is stored as isotonic knots and applied with `numpy.interp`. Never a pickled scikit-learn object.
5. Categorical encoding is a saved dict mapping, not a pickled encoder. An unseen category is a handled case with a documented default, never an exception.
6. Feature contributions come from XGBoost's `pred_contribs=True`. The `shap` package is for offline analysis only, and if it is ever used in `app/` it is imported lazily inside a function — never at module top level.
7. Models persist as XGBoost JSON, not pickle.
8. `scripts/measure_memory.py` reports resident memory after import, after `load_models()`, and after one `/recommend` call, against `MEMORY_CEILING_MB` in config. It is run and its numbers recorded at P11, P13 and P17.
9. If a target cannot fit, the only permitted lever is disabling the XAI endpoint by config flag. Never the fallback path, the grounding guards, the calibrator, or the primary recommender.

---

## 15. Spikes and risk-reduction work

Phase R produces **spikes**: throwaway prototypes that validate a design decision before the phase that depends on it is built.

- Spikes live in `spikes/`, never in `app/` or `training/`.
- Nothing in `app/` or `training/` may import from `spikes/`.
- A spike's job is to produce **validated parameters, invariant suites, corpora and measurements** — not production code. The owning phase re-implements the logic properly against the real schemas.
- A spike's **test artefacts do carry forward**: the labeling invariant suite and the grounding corpus are moved into `tests/` by their owning phases and become permanent. That is the point of building them early.
- A spike is never a reason to skip or shorten its owning phase, and a spike passing does not advance any phase's status.
- Delete a spike once its owning phase is `DONE`, or mark it clearly as superseded.
