# IMPLEMENTATION_PLAN.md

Phased build plan for the **ML-first** Personalized Loan Recommendation System (architecture v2.0).

**How to use this file:** each phase has a ready-to-paste prompt. Give the agent exactly one phase prompt at a time. Do not paste the next phase until the current one reports `DONE` with verified exit criteria. Every prompt assumes the agent has read `CONTEXT.md` and `AGENTS.md`.

**This is a clean rebuild.** The v1.0 implementation is reference material only. Do not import from it, do not copy modules forward wholesale, and do not mark a phase `DONE` because the equivalent v1.0 phase was done. Where v1.0 logic is genuinely unchanged (financial ratios, the EMI formula, portfolio aggregation), you may consult it — but it is re-implemented against the v2.0 schemas and re-verified by v2.0 tests.

**Phase order is dependency-driven and must not be reordered.**

| Phase | Name | Depends on |
|---|---|---|
| **R** | **Risk-reduction spikes** (labeling invariants, grounding normalizer, memory budget) | — |
| P0 | Scaffold, schemas, config | R |
| P1 | Financial Intelligence | P0 |
| P2 | Portfolio Intelligence | P0 |
| P3 | Personalization store + context | P0 |
| P4 | Eligibility Engine | P0, P1 |
| P5 | Finance math + Candidate Generation Engine | P0, P1, P2 |
| P6 | Guardrail policy validator | P0, P1, P2, P5 |
| P7 | Synthetic data + relevance labeling policy | P1, P2, P5 |
| P8 | Shared feature engineering | P1, P2, P3, P5 |
| P9 | Risk model (secondary) training | P7, P8 |
| P10 | **Primary recommender training + calibration + evaluation** | P7, P8, P9 |
| P11 | ML inference layer + fallback | P9, P10 |
| P12 | Recommendation Orchestrator (validation walk, mismatch, coverage, trace) | P4, P5, P6, P11 |
| P13 | XAI + LLM explanation | P11, P12 |
| P14 | FastAPI surface | P1–P13 |
| P15 | Frontend | P14 |
| P16 | Demo hardening | all |
| P17 | Deployment (no Docker) | all |

**Critical scheduling note.** The end-to-end path must be walkable as early as possible. The minimum viable ML-first path is:

```
R -> P0 -> P1 -> P2 -> P4 -> P5 -> P6 -> P7 -> P8 -> P10 -> P11 -> P12 -> P14 -> P15
```

If time runs short, cut in this order: (1) personalization features (P3 — the recommender must run without them), (2) SHAP visuals (keep feature-importance fallback), (3) what-if scenarios, (4) the secondary risk model (P9 — impute PD at the training-set median and flag it). **Never cut:** candidate generation, the primary recommender, deterministic validation, guardrails, catalogue mismatch handling, or the `recommendation_source` flag. Cutting the recommender means there is no product.

**Mandatory workflow.** Every phase below, without exception, follows the seven steps in `AGENTS.md` §1: read the four authoritative files → confirm scope (including what must *not* be built) → implement only this phase → phase tests then full regression → verify every exit criterion by a command actually run → record the full result in `PHASE_STATUS.md` → **STOP**. Do not begin the next phase until told to.

---

## PHASE R — Risk-Reduction Spikes

**Why this phase exists.** Three parts of this build are disproportionately likely to fail, and all three are cheaper to settle now than to discover later: a flawed labeling policy silently teaches the model the wrong thing (P7/P10), a serving image that does not fit memory is found at deployment when six modules already assume pandas (P17), and a grounding guard with false positives gets switched off, leaving nothing protecting the user (P13). See `CONTEXT.md` §17 for the full analysis and the binding design decisions.

This phase produces **no production code**. Its outputs are validated parameters, an invariant suite, a labelled corpus and a measurement.

**Prompt:**

```
Read CONTEXT.md (especially section 17) and AGENTS.md (especially sections 1, 14, 15)
fully before starting.

You are executing PHASE R only: risk-reduction spikes. This phase produces NO
production code. Everything you write lives in spikes/ and nothing in app/ or
training/ may ever import it. Do not create app/, do not create schemas, do not start
Phase 0.

Build three independent spikes.

SPIKE 1 — Labeling invariants (de-risks P7)
  spikes/labeling/
  1. Write the INVARIANT SUITE FIRST, before any labeling logic. Property-based tests
     (hypothesis) over wide input ranges asserting the properties in CONTEXT.md 17.1:
       - dominance: a candidate dominated on every axis never outranks its dominator
       - single-axis monotonicity: lower rate / lower EMI / lower total interest /
         smaller liquidation share never lowers a label, all else equal
       - scale invariance: multiplying income, expenses, portfolio and every rupee
         amount by a constant leaves all labels unchanged
       - appetite ordering: a leverage-heavy candidate is never graded higher under
         CONSERVATIVE than under AGGRESSIVE
       - zero-portfolio consistency: no liquidation strategy appears with no holdings
       - non-degeneracy: all four grades appear; no grade, product, tenure or strategy
         exceeds a configured share of groups
  2. Then write a PROTOTYPE labeling policy in the decomposed four-stage shape
     (disqualifier mask -> independent normalized sub-scores -> documented combination
     -> stress demotion), with grades assigned by rank within each customer's own
     candidate group.
  3. Run the invariants against it on synthetic inputs generated inside the spike
     (do NOT call app/ — it does not exist yet; use plain dicts or dataclasses local
     to the spike).
  4. Measure the STRESS-SIMULATION LABEL-FLIP RATE: labels with the simulation on vs
     off. Target band 2%-30%. Tune the shock parameters until it lands in band, and
     record the chosen parameters.
  5. Produce spikes/labeling/FINDINGS.md: the validated sub-score definitions, the
     chosen stress parameters and measured flip rate, every invariant that passed,
     and any invariant you could NOT satisfy (that is a design finding, report it —
     do not weaken the invariant).

SPIKE 2 — Grounding normalizer + corpus (de-risks P13)
  spikes/grounding/
  1. Build tests/data/grounding_corpus.jsonl (write it under spikes/ for now; P13
     moves it into tests/). At least 60 labelled cases covering:
       - Indian numbering: 6,00,000 / 600000 / 6 lakh / 6L / ₹6L / 6 lakhs /
         ₹6,00,000 / 60 lakh / 1.2 crore
       - rate duals: 8% / 8.0% / 0.08 / 8 percent / 8.5% p.a.
       - tenure duals: 48 months / 4 years / 4 yrs / 48-month
       - structural non-financial numbers that must NOT be treated as figures:
         "3 alternatives", "1st", "Option 2", "top 3", dates, "Section 7"
       - genuinely UNGROUNDED cases: an invented EMI, an invented total interest, a
         rate that is not in the payload, a lender that is not in the payload
       - genuinely UNVERIFIED cases: an ambiguous or malformed token
     Label each GROUNDED / UNGROUNDED / UNVERIFIED.
  2. Build the normalizer and the three-outcome guard exactly as specified in
     AGENTS.md section 5: context-gated extraction, expanded accepted-set matching,
     and GROUNDED / UNVERIFIED / UNGROUNDED outcomes. Pure functions, no dependencies
     beyond the standard library and re.
  3. Run it against the corpus. REQUIRED RESULT: 100% of UNGROUNDED cases rejected,
     and ZERO false rejections of GROUNDED cases. Iterate the normalizer — never the
     corpus labels — until both hold.
  4. Also build the entity-grounding check (product/lender names) and corpus cases
     for it.
  5. Produce spikes/grounding/FINDINGS.md: the final rule set, the confusion matrix
     against the corpus, and any case class you could not handle.

SPIKE 3 — Serving memory budget (de-risks P17)
  spikes/memory/
  1. In a fresh virtualenv, measure resident memory (RSS) for the PROPOSED SERVING
     dependency set only: numpy + xgboost + fastapi + pydantic + uvicorn.
     Measure: after imports; after loading a dummy XGBoost booster saved as JSON;
     after one trivial prediction.
  2. For comparison, measure the same with pandas + scikit-learn + shap also imported,
     so the saving is a number and not an assertion.
  3. Verify the two mechanisms the budget depends on actually work:
       - an isotonic curve exported as (x, y) knots and applied with numpy.interp
         reproduces sklearn's IsotonicRegression.predict within tolerance
       - xgboost's predict(..., pred_contribs=True) returns per-feature contributions
         summing to the margin, so the shap package is not needed for TreeSHAP
  4. Produce spikes/memory/FINDINGS.md: the measured numbers, the recommended
     MEMORY_CEILING_MB for config, and confirmation (or refutation) of the two
     mechanisms above. If either mechanism does not work as expected, say so plainly —
     that changes the P0 dependency decision.

Exit criteria (verify each by running something):
- Spike 1: the invariant suite runs and reports pass/fail per invariant; the flip rate
  is measured and inside the target band; FINDINGS.md written.
- Spike 2: the guard scores 100% on UNGROUNDED and zero false rejections on GROUNDED
  against a corpus of at least 60 cases; FINDINGS.md written.
- Spike 3: memory numbers measured for both dependency sets; both mechanisms verified
  or refuted; FINDINGS.md written.
- Nothing exists under app/ or training/.

Report in the AGENTS.md format, adding a section RISKS RESOLVED / RISKS REMAINING that
states plainly which of the three bottlenecks is now closed and which is not.

Update PHASE_STATUS.md, then STOP. Do not begin Phase 0.
```

---

## PHASE 0 — Scaffold, Schemas, Config

**Goal:** every later phase has a place to put its code and a typed contract to work against, and the v2.0 vocabulary exists before anything uses it.

**Prompt:**

```
Read CONTEXT.md and AGENTS.md fully before starting. Phase R is complete — read
spikes/*/FINDINGS.md and adopt its validated outputs (the recommended
MEMORY_CEILING_MB, and its confirmation of the isotonic-knots and pred_contribs
mechanisms). If a Phase R finding contradicts anything below, stop and report it
rather than choosing silently.

You are executing PHASE 0 only: Scaffold, Schemas, Config. Do not implement any
business logic, any calculation, any model, or any endpoint behavior in this phase.
If you find yourself writing a formula, you have left the phase — stop.

Build:

1. Repository structure exactly as laid out in the AGENTS.md module map:
   app/{schemas,core,ml,personalization,explain,api}/, training/, tests/, data/, models/
   Each package gets an __init__.py. No Docker files.

   Dependency split (this is the memory budget — see CONTEXT.md 17.2, AGENTS.md 14):
   - requirements.txt        SERVING ONLY: numpy, xgboost, fastapi, pydantic,
                             uvicorn, and the LLM HTTP client. NOT pandas, NOT
                             scikit-learn, NOT shap, NOT matplotlib.
   - requirements-train.txt  offline: pandas, scikit-learn, shap, matplotlib,
                             hypothesis, plus the serving set.
   - Both fully pinned to exact versions (==), never ranges.
   - runtime.txt containing a single pinned Python version (e.g. python-3.11.9).
   - .gitignore covering .env, __pycache__, node_modules, *.pyc, *.db, spikes/ output.

   Add tests/test_serving_imports.py NOW, before any code can violate it: import the
   application package and assert that sys.modules contains no "pandas", "sklearn" or
   "shap". This test is what makes the memory budget real rather than aspirational.

2. app/schemas/enums.py with, at minimum:
     RiskAppetite         CONSERVATIVE | MODERATE | AGGRESSIVE
     FinancialHealth      (bands)
     RiskClass            (risk model output classes)
     FinancingStrategy    BORROW_100 | BORROW_80_LIQUIDATE_20 | ... | LIQUIDATE_100
     LoanPurpose          AssetType            EligibilityStatus
     RecommendationStatus RECOMMENDED | NO_ELIGIBLE_PRODUCTS | NO_FEASIBLE_CANDIDATES
                          | ALL_CANDIDATES_BLOCKED | NO_SUITABLE_LOAN
     RecommendationSource ML_RANKER | DETERMINISTIC_FALLBACK
     CandidateOutcome     RECOMMENDED | ELIGIBLE_UNSUITABLE | INELIGIBLE | INFEASIBLE
                          | GUARDRAIL_BLOCKED | DOMINATED
     MismatchReasonCode   the codes listed in CONTEXT.md section 7.2
   These are the only string constants in the system.

   RecommendationStatus and RecommendationSource are separate fields on separate axes.
   Do not add a fallback value to RecommendationStatus.

3. Pydantic models in app/schemas/ covering the full v2.0 pipeline contract:
   - CustomerProfile (income, expenses, existing EMI, credit score, employment, age,
     optional pseudonymous user_id)
   - Holding + Portfolio (list of holdings; must validate as empty/absent)
   - LoanRequirement (purpose, requested amount, preferred tenure, risk appetite)
   - LoanProduct (product id, lender, type, purpose, rate, min/max amount,
     min/max tenure, min credit score, min income, processing fee band)
   - FinancialMetrics, PortfolioMetrics, PersonalizationContext
   - EligibilityResult (per product, always present, with reason code when False)
   - Candidate — a FULLY SPECIFIED financing configuration: product id, lender,
     amount, tenure, strategy, EMI, total interest, total repayment, liquidation
     amount, remaining portfolio, resulting liquidity, resulting debt burden,
     affordability headroom, feasible flag, infeasibility reason
   - ScoredCandidate (candidate + raw_ranker_margin + suitability [0..1] + rank)
   - GuardrailResult (allowed, violated rule name, cap value, observed value)
   - ValidationResult (passed, failed check name, expected vs observed)
   - RiskPrediction (class, probability of default, model version, imputed flag)
   - MismatchReason (code, observed value, threshold, product/candidate reference)
   - CatalogueCoverage (counts at every funnel stage — see CONTEXT.md 7.3)
   - DecisionTrace (every element listed in AGENTS.md section 9)
   - Recommendation (status, source, selected candidate or None, ml_suitability
     or None, reasons, alternatives, ml_top_choice_blocked, mismatch_reasons,
     coverage, decision_trace)

   Recommendation must be constructible with NO selected candidate — the
   NO_SUITABLE_LOAN case is a first-class shape, not an error. Add a validator
   asserting that a RECOMMENDED status has a candidate and a non-RECOMMENDED
   status does not.

   Add field validators for the obvious invariants (non-negative money, credit
   score range, tenure > 0, suitability within 0..1). Decide money representation
   now (float rupees OR int paise), document the choice in a comment, and apply it
   consistently.

4. app/config.py: a single Pydantic Settings object loaded once.

   Split by type — this split is mandatory, complex structures in .env parse badly:
   - Read from .env (flat scalars only): model paths, LLM API key and endpoint,
     personalization database URL, CORS allowed origins, CONFIG_VERSION,
     FEATURE_VERSION, PROMPT_VERSION, LABELING_POLICY_VERSION, LOG_LEVEL,
     ENABLE_XAI_ENDPOINT.
   - Define as typed defaults directly in the Settings class (NOT in .env):
     SUITABILITY_ACCEPTANCE_THRESHOLD, guardrail caps per RiskAppetite, eligibility
     thresholds, candidate enumeration grids (amount steps, tenure options, strategy
     splits), per-product candidate caps, liquid asset types and haircuts,
     diagnostic utility weights w1..w5, MEMORY_CEILING_MB (value from the Phase R
     memory findings), grounding magnitude floor and cue-word list.
   Complex defaults may optionally be overridden by a JSON file path given in .env,
   but the class defaults must work with no file present.

   Everything above is still config: business logic may never hardcode these values.
   Commit .env.example with placeholders; gitignore .env.

5. PHASE_STATUS.md with all phases listed as NOT_STARTED except P0.

6. tests/test_schemas.py: valid payloads construct; invalid payloads raise; a
   Portfolio with zero holdings is valid; a Recommendation with NO_SUITABLE_LOAN and
   no candidate is valid; a RECOMMENDED Recommendation with no candidate raises.

7. tests/fixtures.py: shared in-memory mock objects used by ALL later phases —
   a mock loan catalogue (list[LoanProduct], ~6 products across purposes, lenders
   and credit tiers), a standard CustomerProfile, a mixed Portfolio, an empty
   Portfolio, a neutral PersonalizationContext, and a customer deliberately
   constructed to match NO product (for the mismatch path).
   No later phase may read a CSV in its tests; every phase imports from here.

Exit criteria (verify each by running a command, do not assume):
- `pytest` passes.
- `python -c "from app.config import settings; print(settings.CONFIG_VERSION)"` works.
- Settings loads successfully with NO .env file present (defaults only).
- Every schema imports cleanly.
- requirements.txt has zero unpinned dependencies.
- Zero business logic in the repo.

When done, update PHASE_STATUS.md and report in the AGENTS.md reporting format.
Then STOP. Do not begin Phase 1.
```

---

## PHASE 1 — Financial Intelligence

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phase 0 is complete; use its schemas as-is.

You are executing PHASE 1 only: Financial Intelligence. Deterministic calculations only.
No ML, no loan products, no eligibility decisions, no EMI for a specific loan.

Build app/core/financial.py exposing:
    analyze_financials(customer: CustomerProfile) -> FinancialMetrics

Compute: monthly income, monthly disposable income, expense ratio, existing debt
burden ratio, EMI affordability ceiling (max EMI the customer can sustain), income
stability indicator, and a financial health band (enum, thresholds from config only).

Rules:
- Every threshold comes from app/config.py. No magic numbers in this file.
- Pure function: no I/O, no global state, no model calls.
- Handle zero-income and zero-expense inputs without crashing.

These metrics feed the ML recommender's feature vector later. Do NOT build the
feature assembly module here — just return the metrics object.

Tests in tests/test_financial.py:
- A known worked example with hand-computed expected values (income 100000,
  expenses 35000, existing EMI 8000 -> disposable 57000, debt burden 8%).
- Boundary cases: zero income, expenses exceeding income, no existing EMI.
- Financial health band transitions at each threshold.

Exit criteria:
- `pytest tests/test_financial.py` passes.
- Full suite passes.
- No hardcoded thresholds (grep the file to confirm).

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 2 — Portfolio Intelligence

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-1 complete.

You are executing PHASE 2 only: Portfolio Intelligence. Deterministic only.
Do not recommend liquidation, do not compute EMI, do not call any model.

Build app/core/portfolio.py exposing:
    analyze_portfolio(portfolio: Portfolio | None) -> PortfolioMetrics

Compute: total value, asset allocation by AssetType, liquid assets, liquidity ratio,
equity exposure, debt exposure, crypto exposure, portfolio risk band,
concentration risk (largest single holding share), unrealized gain/loss.

CRITICAL: the no-portfolio case is a first-class path, not an error. A customer with
None or an empty holdings list must return a valid zero-value PortfolioMetrics that the
rest of the pipeline — including the ML feature vector — can consume without
special-casing. Test this explicitly.

Liquidity classification (which asset types count as liquid, and any haircut applied)
comes from config, not from inline logic.

Tests in tests/test_portfolio.py:
- Mixed portfolio with hand-computed expected allocation and liquidity ratio.
- Empty portfolio -> valid zero metrics, no exception.
- None portfolio -> valid zero metrics, no exception.
- Single-holding portfolio -> concentration risk at maximum.
- Crypto-heavy portfolio -> high risk band.

Exit criteria: phase tests pass, full suite passes, zero-portfolio path proven by test.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 3 — Personalization Store + Context

**Prompt:**

```
Read CONTEXT.md and AGENTS.md, especially the personalization section (CONTEXT.md 10).
Phases 0-2 complete.

You are executing PHASE 3 only: the personalization layer. This layer produces
FEATURES. It does not score, rank, recommend, or decide anything. If you write a
scoring function here, you have built a second recommender — stop.

Build:

1. app/personalization/store.py — persistence over SQLite (URL from config, so the
   same code works against Postgres later). Tables:
     users(user_id pseudonymous, created_at, last_seen_at)
     profile_snapshots(user_id, snapshot_at, financial summary fields)
     recommendation_history(user_id, at, product_id, purpose, amount, tenure,
                            strategy, suitability, status)
     feedback_events(user_id, at, product_id, event_type ACCEPTED|DECLINED|VIEWED)
   Plus: delete_user(user_id) removing every row for that user. This deletion path is
   part of the contract, not a later addition.

   Store ONLY pseudonymous ids and derived values. No names, contact details,
   identity numbers, or free text. Ever.

2. app/personalization/context.py exposing:
       get_personalization_context(user_id: str | None) -> PersonalizationContext
   Emits: purpose affinity, tenure-band affinity, financing-strategy affinity,
   session count, time-decayed engagement, prior decline count. Decay half-life and
   all weights come from config.

   COLD START IS A FIRST-CLASS PATH, exactly like the zero portfolio. user_id None,
   unknown, or with zero history returns a valid NEUTRAL PersonalizationContext with
   an is_cold_start flag set. The pipeline must run identically. Test this explicitly.

3. A seed script for demo/history data lives in training/, not in app/.

Tests in tests/test_personalization.py:
- Cold start (None user_id) returns a neutral context with is_cold_start True.
- Unknown user_id returns the same neutral context.
- A user with recorded history produces affinities that differ from neutral, with
  hand-computed expected values for a small fixture history.
- Time decay: an old event contributes less than a recent identical event.
- delete_user removes every row across all tables and returns the context to cold start.
- The store writes to a temp database, never to a path under data/.

Exit criteria: phase tests pass, full suite passes, cold-start path proven by test,
deletion path proven by test, no PII fields anywhere in the schema.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 4 — Eligibility Engine

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-3 complete.

You are executing PHASE 4 only: rule-based hard eligibility. No ML. No EMI.
No ranking. No scoring. No guardrails (those are Phase 6 and run much later in the
pipeline).

Build app/core/eligibility.py:
       check_eligibility(customer, financial_metrics, requirement, catalogue)
           -> list[EligibilityResult]

Hard constraints only: credit score >= product minimum, income >= product minimum,
requested amount within product limits, purpose matches product, preferred tenure
within product limits. Each result carries eligible True/False plus a machine-readable
MismatchReasonCode when False, with the observed value and the threshold it failed.

NEVER silently drop a product from the output. Every catalogue product appears in the
returned list with an outcome — the mismatch analyzer and the coverage funnel depend
on it, and a dropped product becomes an unexplainable gap in the trace.

This module runs BEFORE candidate generation and BEFORE the ML recommender. It is the
"can this be considered at all" gate. It is not the "is this right for you" question —
that is the recommender's job in Phase 10.

Tests in tests/test_eligibility.py:

IMPORTANT: the synthetic loan catalogue CSV is not generated until Phase 7. Do NOT
create it, do NOT read from data/, and do NOT skip ahead. Import the mock catalogue
from tests/fixtures.py for every test in this phase.

- Each eligibility rule fails in isolation and produces the right reason code,
  observed value and threshold.
- A fully-qualifying customer passes all products.
- Output length always equals catalogue length, including when everything fails.
- The fixtures' deliberately-unmatched customer produces all-False with populated
  reason codes.

Exit criteria: tests pass, full suite passes, all thresholds read from config,
no ML imported anywhere in this phase, output length invariant proven by test.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 5 — Finance Math + Candidate Generation Engine

**Prompt:**

```
Read CONTEXT.md and AGENTS.md, especially the Candidate Generation Engine section.
Phases 0-4 complete.

You are executing PHASE 5 only. Pure deterministic math and enumeration.
No ML calls, no LLM calls, NO RANKING BY PREFERENCE, no utility function.
This module generates the option space the ML recommender will later score. It must
not express any opinion about which option is better for the customer.

Build:

1. app/core/finance_math.py:
   emi(principal, annual_rate, tenure_months) -> float
   Use exactly: EMI = P*r*(1+r)^n / ((1+r)^n - 1), r = annual_rate/12/100.
   Handle r == 0 as P/n. Plus total_interest and total_repayment.
   This is the ONLY EMI implementation in the repository. Phase 12's validation
   module will import this same function to re-verify the ML's chosen candidate.

2. app/core/candidates.py:
       generate_candidates(requirement, financial_metrics, portfolio_metrics,
                           eligible_products) -> list[Candidate]
   Grid over: loan amounts (steps from config), tenures (options from config),
   financing strategies (100% borrow, 80/20, 60/40, 40/60, 20/80, 100% liquidate).
   For each candidate compute: loan amount, liquidation amount, EMI, total interest,
   total repayment, remaining portfolio value, resulting liquidity ratio, resulting
   debt burden, affordability headroom.
   This is bounded enumeration. Do not import scipy.optimize. Do not introduce a
   solver. Enumerate and return.

3. Feasibility: a candidate is MARKED infeasible (not deleted) when its EMI exceeds
   the affordability ceiling or it requires liquidating more than the portfolio holds.
   The infeasibility reason is a MismatchReasonCode.

4. Dominance pruning: among FEASIBLE candidates for the same product and same loan
   amount, drop candidate B when candidate A is better-or-equal on EVERY axis
   (EMI, total interest, portfolio impact) and strictly better on at least one.
   Record pruned counts for the coverage funnel. Dominance pruning removes
   objectively worse options and expresses NO preference — it is not ranking. Do not
   extend it into a scoring heuristic.

5. Enforce a configured per-product candidate cap AFTER pruning, and record how many
   were capped. The cap exists so the recommender scores a bounded set.

6. If the customer has no portfolio, only 100%-borrow strategies are generated.
   This must work without special-casing anywhere downstream.

Tests in tests/test_candidates.py:
- EMI against a hand-computed known value (assert to 2 decimal places).
- EMI with zero interest rate.
- Longer tenure -> lower EMI, higher total interest (monotonicity).
- Higher liquidation -> lower loan amount and lower EMI.
- No-portfolio input -> only borrow-100% candidates, all feasible ones valid.
- Infeasible candidates are returned marked, not dropped.
- Dominance pruning removes a constructed strictly-dominated candidate and keeps the
  dominating one.
- Dominance pruning does NOT remove a candidate that is worse on one axis and better
  on another (proving it is not ranking).
- Candidate count is bounded by the configured grid and per-product cap.

Exit criteria: tests pass, full suite passes, exactly one EMI implementation exists
in the repo (grep to confirm), no preference ordering anywhere in this module.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 6 — Guardrail Policy Validator

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-5 complete.

You are executing PHASE 6 only: the guardrail policy layer. Rule-based, deterministic,
pass/fail. No ML. No EMI computation (call finance_math if you need a figure). No
ranking, no reordering, no scoring, no filtering of lists.

Note the architectural change from v1.0: guardrails no longer pre-filter the option
space before ML. They VALIDATE the candidates the ML recommender has already ranked,
in rank order, in Phase 12. Build them as a pure pass/fail check over a single
candidate so that walk is possible.

Build app/core/guardrails.py:
       check_guardrails(risk_appetite, financial_metrics, portfolio_metrics, candidate)
           -> GuardrailResult

Policy caps per RiskAppetite, all loaded from config:
  - max debt-burden ratio after the new EMI
  - max share of portfolio permitted to be liquidated
  - whether volatile assets (crypto, equity) may be liquidated at all
  - max loan-to-income multiple

A violation returns allowed=False plus the violated rule name, the cap value, and the
observed value — enough for the trace and the UI to say exactly what blocked it.
Return the FIRST violation deterministically (fixed rule evaluation order from config)
so the same input always names the same rule.

IMPORTANT BEHAVIOR: guardrails never delete an option and never choose one. A blocked
candidate is returned flagged, with the reason, so Phase 12 can surface
"the model's best match for you was X, but rule R blocked it, so we recommend Y."

Tests in tests/test_guardrails.py (use tests/fixtures.py; do not read from data/):
- Each cap is violated in isolation and names the right rule, cap and observed value.
- Conservative appetite blocks a high-leverage candidate that Aggressive permits.
- Volatile-asset liquidation is blocked for Conservative and allowed for Aggressive.
- A no-portfolio borrow-only candidate is evaluated correctly (no liquidation caps
  can fire).
- Rule evaluation order is deterministic: the same input names the same rule twice.

Exit criteria: tests pass, full suite passes, all caps read from config, the function
is pure pass/fail over a single candidate, no list filtering in this module.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 7 — Synthetic Data + Relevance Labeling Policy

**Prompt:**

```
Read CONTEXT.md sections 6 and 11 and AGENTS.md section 6 before starting.
Phases 0-6 complete.

You are executing PHASE 7 only: datasets and the relevance labeling policy.
Nothing in this phase may be imported by anything under app/. Training code lives in
training/ and stays there. Do not train a model in this phase.

This phase is the foundation of the ML-first architecture: it defines what
"suitable for this customer" MEANS as a training target. Get it wrong and every
downstream metric is meaningless.

Build:

1. training/generate_data.py producing, into data/:
   - loan_products.csv    synthetic catalogue, 12-15 products across purposes,
                          lenders and credit tiers
   - customers.csv        synthetic customer financial profiles
   - portfolios.csv       synthetic holdings per customer (INCLUDING a meaningful
                          share of customers with NO portfolio)
   - history.csv          synthetic personalization seed history for a subset of
                          customers (the rest are cold-start)
   Every generated file carries a header comment AND a SYNTHETIC column.
   Fixed random seed, recorded in the manifest.

   For the customer financial dataset, use public lending/credit data if available in
   data/raw/; otherwise generate synthetic and label it as such. State clearly in your
   report which you used.

2. FIRST, port the Phase R invariant suite into tests/test_labeling_invariants.py,
   rewritten against the real schemas. Run it and watch it FAIL — there is no policy
   yet. Only then write the policy. Writing the policy first and the invariants
   afterwards produces invariants shaped to fit the policy's bugs, which is the exact
   failure this ordering prevents.

3. training/labeling.py — THE relevance labeling policy, in the DECOMPOSED four-stage
   shape validated in Phase R. For each customer, generate their candidate set by
   calling app/core/candidates.py (the SAME generator used at serving time — do not
   write a second enumerator), then:

     Stage A - disqualifier mask: hard, explicitly listed conditions that force
               grade 0. Nothing else in the pipeline may assign grade 0.
     Stage B - independent sub-scores, each normalized to [0,1], each owning exactly
               one concern and each separately unit-tested:
                 affordability (EMI vs disposable income headroom)
                 cost of credit (total interest / total repayment)
                 portfolio impact (liquidation share, post-strategy liquidity)
                 appetite alignment
               No sub-score may read another's inputs.
     Stage C - documented combination of the sub-scores into one value, then
               GRADES ASSIGNED BY RANK WITHIN THE CUSTOMER'S OWN CANDIDATE GROUP
               (within-group quantiles), NOT by absolute cutoffs. A ranker only
               consumes within-group order; quantile grading removes scale
               sensitivity and income-dependent threshold drift for free.
     Stage D - stress demotion: draw an income shock over the loan term (the
               parameters validated in Phase R) and demote candidates whose household
               does not stay solvent. This forward-looking component is deliberately
               not directly recoverable from the feature vector, so the model has
               something to learn beyond a formula. Apply it AFTER grading, as a
               demotion — never fold it into a sub-score.
     Then calibrated label noise.

   A single monolithic scoring function is forbidden. All coefficients live in a
   documented constants block with a comment explaining each. Write the policy ONCE;
   it is the only labeler. Stamp LABELING_POLICY_VERSION into every artifact it
   touches.

4. Measure and record the STRESS-SIMULATION LABEL-FLIP RATE (labels with Stage D on
   vs off). It must land in the 2%-30% band established in Phase R: below 2% the
   simulation is doing nothing and should be removed; above 30% it has swamped the
   other signals. Record the measured rate in the dataset manifest.

5. Write data/label_audit_sample.md on every dataset build: twenty customers with
   their top-labelled and bottom-labelled candidates rendered in plain language.
   Invariants catch logical flaws; only a human catches "self-consistent, but no
   person would call that the best option." Read it yourself before marking the phase
   done, and say in your report what you saw.

6. training/build_dataset.py producing data/relevance_dataset.csv:
   one row per (customer, candidate) with a customer-level group id, the label, and
   the identifiers needed to rebuild features in Phase 8. Include the group sizes
   file/column XGBRanker requires. Split by CUSTOMER, never by row — a customer's
   candidates must not appear in both train and test.

7. A manifest data/dataset_manifest.json recording: seed, row counts, group counts,
   label distribution, split sizes, LABELING_POLICY_VERSION, the measured stress
   label-flip rate, and an explicit "labels_are_synthetic": true.

Tests in tests/test_labeling_invariants.py (ported from Phase R) — ALL must pass:
- dominance, single-axis monotonicity, scale invariance, appetite ordering,
  zero-portfolio consistency, non-degeneracy. Property-based, over wide input ranges.
- If an invariant cannot be satisfied, that is a design finding: report it and set the
  phase BLOCKED. Do NOT weaken the invariant to match the policy.

Tests in tests/test_labeling.py:
- The labeler is deterministic under a fixed seed.
- Each Stage B sub-score is unit-tested in isolation, including its bounds.
- Stage C grading is by within-group rank: scaling one customer's whole candidate set
  leaves their grades unchanged.
- Stage D changes the label set (flip rate > 0) and stays within the configured band.
- Label distribution is not degenerate (every grade 0-3 is present, and no grade
  exceeds a configured share of the data).
- Every customer group contains at least one candidate with label >= 2 OR is
  explicitly recorded in the manifest as an intentional no-suitable-loan customer.
  The dataset MUST contain such customers — the model has to learn that some
  profiles have no good option.
- Train/test split shares no customer id.

In your report, state honestly: which datasets are synthetic, that the relevance
labels are produced by the policy in training/labeling.py, and that a model trained on
them partially reproduces that policy. Do not describe the labels as customer behavior.

Exit criteria:
- `python training/generate_data.py` runs and writes all files.
- `python training/build_dataset.py` runs and writes relevance_dataset.csv + manifest.
- Every invariant in tests/test_labeling_invariants.py passes.
- The stress label-flip rate is measured, inside the 2%-30% band, and in the manifest.
- data/label_audit_sample.md is written and you have actually read it.
- Tests pass; full suite passes.
- No file in app/ imports anything from training/.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 8 — Shared Feature Engineering

**Prompt:**

```
Read CONTEXT.md section 6.3 and AGENTS.md section 6 before starting.
Phases 0-7 complete.

You are executing PHASE 8 only: THE shared feature assembly module. No training,
no model, no inference. This module is imported by BOTH training and serving — if you
are tempted to write a second feature path in training/, that is exactly the defect
this rule exists to prevent.

Build app/ml/features.py exposing:

1. build_risk_features(financial_metrics, portfolio_metrics, requirement)
       -> np.ndarray, with RISK_FEATURE_COLUMNS defining column order.

2. build_pair_features(financial_metrics, portfolio_metrics, personalization_context,
                       requirement, product, candidate, risk_pd: float)
       -> np.ndarray, with PAIR_FEATURE_COLUMNS defining column order.

   NOTE ON risk_pd: it is a PARAMETER, not computed here. This module never calls a
   model. That keeps the dependency acyclic — Phase 9 trains the risk model, Phase 10
   feeds its PD in as a number.

3. build_pair_feature_matrix(...) -> matrix for a whole candidate list, so serving
   scores all candidates in one call rather than looping per candidate.

4. FEATURE_VERSION (from config) and a manifest helper that emits
   {feature_version, columns} for a training script to save alongside its model,
   plus assert_manifest_matches(manifest) used at model load time.

Feature groups (see CONTEXT.md 6.3 for the full list): customer financial, portfolio,
personalization, requirement, product, derived candidate, risk PD.

Rules:
- Categorical encoding (loan purpose, lender, employment type, strategy, bands) is
  defined here, once, and the encoder mapping is deterministic and saved with the
  manifest. Never fit an encoder at serving time.
- The zero-portfolio case and the cold-start personalization case must produce valid
  vectors of identical length with no NaN.
- No feature may be computed from a value the pipeline does not have at inference
  time. If you cannot produce a feature at serving, it is not a feature.

Tests in tests/test_features.py:
- Feature vector length equals len(PAIR_FEATURE_COLUMNS); same for risk features.
- Identical inputs produce byte-identical vectors on repeated calls.
- No-portfolio input produces a valid vector, correct length, no NaN.
- Cold-start personalization produces a valid vector, correct length, no NaN.
- Column order is stable across calls and matches the emitted manifest.
- assert_manifest_matches raises on a version mismatch and on a reordered column list.
- The matrix builder and the per-candidate builder produce identical rows.

Exit criteria: tests pass, full suite passes, exactly one feature-assembly path exists
in the repo (grep training/ to confirm it imports this module), no model imported here.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 9 — Risk Model (Secondary)

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-8 complete.

You are executing PHASE 9 only: the SECONDARY risk classifier. Offline training only.

Be clear about this model's role: its output is a FEATURE for the primary recommender
and a user-facing risk disclosure. It does not select a loan, does not veto a
candidate, and is not the recommendation. Do not build any selection logic here.

Build training/train_risk.py:
- XGBoost classifier over build_risk_features from app/ml/features.py.
- Customer-level train/test split (reuse the Phase 7 split so no customer leaks).
- Modest GridSearchCV over a small grid with cross-validation — keep the grid small
  enough to finish in minutes, and record the searched grid in the manifest.
- Report ROC-AUC, PR-AUC, precision, recall, F1, Brier score, and a reliability
  curve summary. Accuracy alone is not sufficient reporting.
- Save models/risk_model.json in XGBoost's native format (NOT pickle, NOT joblib),
  plus models/risk_model_manifest.json
  recording: feature column order, FEATURE_VERSION, training row count, split sizes,
  metrics, searched grid, best params, seed, model version, and whether the training
  labels are synthetic.

Tests in tests/test_risk_training.py (fast, no full retrain):
- The manifest column order equals RISK_FEATURE_COLUMNS.
- The saved artifact loads and produces a probability in [0,1] for a fixture input.
- The manifest records FEATURE_VERSION matching app/ml/features.py.
If a test needs a model and none is trained, it skips with a clear message and the
suite stays green — but the exit criteria below still require an actual trained model.

Exit criteria:
- `python training/train_risk.py` runs, prints all metrics, saves the model and manifest.
- Metrics recorded in the manifest and quoted in your report.
- Tests pass; full suite passes.
- Nothing under app/ imports training/.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 10 — Primary ML Recommender: Training, Calibration, Evaluation

**This is the phase the whole redesign exists for. Do not rush it.**

**Prompt:**

```
Read CONTEXT.md sections 2, 6 and 14, and AGENTS.md section 6, before writing any code.
Phases 0-9 complete.

You are executing PHASE 10 only: training the PRIMARY personalized recommendation
model. This model is the decision-making intelligence of the system. Offline training
only; no inference wrappers (Phase 11), no orchestration (Phase 12).

Build:

1. training/train_recommender.py
   - Model: XGBRanker (LambdaMART, rank:ndcg objective) over the Phase 7 relevance
     dataset, with customer-level groups.
   - Features: build_pair_features / build_pair_feature_matrix from app/ml/features.py
     ONLY. The risk PD fed in comes from the Phase 9 model applied to each customer.
   - Split by customer, reusing the Phase 7 split.
   - Small hyperparameter search with GROUP-AWARE cross-validation (never split a
     customer's candidates across folds). Record the grid.

2. Suitability calibration (required — the acceptance threshold depends on it):
   - Fit an isotonic regression on HELD-OUT groups mapping raw ranker margin ->
     P(relevance >= 2) -> suitability in [0,1].
   - EXPORT IT AS KNOTS: save the monotone (x, y) breakpoints, not the fitted
     scikit-learn object. Serving applies them with numpy.interp, so no scikit-learn
     is needed at inference (CONTEXT.md 17.2). Assert in this script that the knot
     interpolation reproduces the fitted estimator's predictions within tolerance.
   - It is a post-processing transform of this model's output, NOT a third model —
     do not register it as one.
   - Report calibration quality: reliability curve summary and Brier score.
   - RECOMMEND A VALUE for SUITABILITY_ACCEPTANCE_THRESHOLD from the calibrated score
     distribution on held-out groups, with the implied NO_SUITABLE_LOAN rate at that
     value. State it in your report as a recommendation for a human to set — do not
     silently change config.

3. models/loan_recommender.json (the booster, XGBoost native format — NOT pickle)
   plus models/loan_recommender_calibration.json (isotonic knots) plus
   models/loan_recommender_encoders.json (the categorical dict mapping) plus
   models/loan_recommender_manifest.json recording: PAIR_FEATURE_COLUMNS order,
   FEATURE_VERSION, group counts, row counts, split, all metrics below, searched grid,
   best params, seed, model version, calibration method, and
   "relevance_labels_are_synthetic": true.

4. Evaluation — ranking metrics, not classification metrics:
   - NDCG@1, NDCG@3, NDCG@5
   - Precision@1, Precision@3, Recall@5
   - MAP@5, MRR
   - Kendall's tau against label order
   - Calibration: reliability curve, Brier score
   Do NOT report accuracy for this model.

5. BASELINES (required, reported side by side in the same table):
   - random ordering
   - cheapest-EMI-first
   - the deterministic diagnostic utility ranking (implement the comparison here
     using the same weights config; do not build app/core/diagnostics.py in this
     phase beyond what the comparison needs)
   If the recommender does NOT beat the diagnostic utility baseline on held-out
   groups, report that plainly in your phase report. Do not tune until it wins and do
   not omit the baseline. A losing result is information the project needs.

6. State in your report, explicitly: the relevance labels are synthetic and generated
   by training/labeling.py, so these metrics measure agreement with that policy rather
   than real recommendation quality; and agreement between this model and the
   diagnostic utility baseline is not evidence either is correct, because they share
   ancestry through the labeling policy.

Tests in tests/test_recommender_training.py:
- The manifest column order equals PAIR_FEATURE_COLUMNS and FEATURE_VERSION matches.
- The saved bundle loads and produces one score per candidate for a fixture list.
- Calibrated suitability is within [0,1] for every fixture candidate.
- Calibration is monotone: a higher raw margin never yields a lower suitability.
- Scoring is deterministic: the same input scored twice gives identical values.
Tests skip cleanly with a clear message when no trained artifact is present.

Exit criteria:
- `python training/train_recommender.py` runs, prints the full metric table including
  all three baselines, and saves the bundle plus manifest.
- Calibration fitted, saved, and its quality reported.
- Tests pass; full suite passes.
- Exactly two model artifacts exist in models/.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 11 — ML Inference Layer + Fallback

**Prompt:**

```
Read CONTEXT.md sections 8 and 12, and AGENTS.md sections 6 and 7.
Phases 0-10 complete; trained artifacts exist in models/.

You are executing PHASE 11 only: inference wrappers. No training. No retraining at
runtime, ever. No orchestration logic (Phase 12).

Build:

1. app/ml/risk.py:
       predict_risk(financial_metrics, portfolio_metrics, requirement) -> RiskPrediction

2. app/ml/recommender.py:
       score_candidates(financial_metrics, portfolio_metrics, personalization_context,
                        requirement, products_by_id, candidates, risk_pd)
           -> list[ScoredCandidate]   # descending suitability, rank assigned
   It receives ONLY candidates that already passed eligibility and feasibility.
   It must NOT filter, reject, re-check eligibility, or compute any rupee figure.
   Given an empty list it returns an empty list.
   It applies the bundled calibrator, so every ScoredCandidate carries both the raw
   margin and the calibrated suitability.

   MODEL LOADING RULE (this overrides any other wording in this plan):
   Do NOT load models at module import. Module-import loading slows pytest collection,
   breaks CLI tools, and blocks startup. Instead provide, in each ML module:
       load_models() -> None    # explicit, called once by the API lifespan handler
       get_*_model()            # returns the loaded model, lazy-loads on first call
   Hold state in a module-level object or cached accessor. Tests must be able to
   import these modules without touching the filesystem.

   At load time, assert the artifact manifest matches app/ml/features.py
   (FEATURE_VERSION + column order). A mismatch is a hard, clearly-messaged failure —
   never a warning, never a silent reorder or truncation.

3. Fallback paths, both explicit and both flagged:
   - Recommender artifact missing/corrupt: log the path and exception, rank candidates
     with app/core/diagnostics.py's diagnostic_utility_score (build that module here:
     weights from config, normalization documented), and mark the result so the caller
     can set recommendation_source = DETERMINISTIC_FALLBACK. In this mode the
     calibrated suitability field is None — never a rescaled utility value.
   - Risk artifact missing/corrupt: impute PD at the manifest-recorded training median
     and set RiskPrediction.imputed = True.
   Never silent. Never a 500 on the primary path.

Tests in tests/test_ml_inference.py:
- Importing app.ml.recommender and app.ml.risk does NOT load a model file (assert the
  state object is empty immediately after import).
- score_candidates returns one ScoredCandidate per input candidate, in descending
  suitability order, with ranks 1..n.
- Empty candidate list -> empty list.
- Suitability values are within [0,1].
- Manifest mismatch (simulate a wrong FEATURE_VERSION) raises at load, with a message
  naming both versions.
- Recommender artifact missing -> diagnostic fallback activates, the fallback flag is
  set, suitability is None, and the ordering still has ranks 1..n.
- Risk artifact missing -> PD imputed, imputed flag True, pipeline continues.
- The recommender never mutates a candidate's financial fields (assert equality
  before and after scoring).

4. scripts/measure_memory.py — reports resident memory after import, after
   load_models(), and after one scoring call, against MEMORY_CEILING_MB from config.
   This is the FIRST of three memory checkpoints (P11, P13, P17). Run it and record
   the numbers in your phase report. Loading is from XGBoost JSON plus the isotonic
   knot table plus the encoder dict — no pickle, no joblib, no scikit-learn.

Exit criteria: tests pass, full suite passes, models load lazily and only once,
no training imports in app/, both fallbacks proven by test, the P0 serving-import
test still passes, memory measured and within the ceiling.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 12 — Recommendation Orchestrator, Validation Walk, Catalogue Mismatch

**Prompt:**

```
Read CONTEXT.md sections 3, 5, 7, 9 and AGENTS.md sections 2, 8, 9.
Phases 0-11 complete.

You are executing PHASE 12 only: the orchestrator. This module ASSEMBLES a
recommendation; it does not choose one. It contains NO scoring formula that can change
the ML ordering. If you write a weighted score here that reorders candidates, you have
rebuilt the v1.0 architecture this redesign removed — stop.

Build:

1. app/core/validation.py:
       validate_candidate(candidate, product, financial_metrics, portfolio_metrics)
           -> ValidationResult
   Independently re-verifies the ML's pick: recompute EMI via app/core/finance_math.py
   and assert it matches the candidate to the rupee; re-check product amount/tenure
   limits; re-check affordability; re-check that required liquidation does not exceed
   available holdings. A failure names the check, the expected and the observed value.
   It NEVER silently corrects a candidate — a mismatch here is a defect signal and
   must be logged as such.

2. app/core/mismatch.py:
       analyze_mismatch(eligibility_results, candidates, scored_candidates, walk_log)
           -> (list[MismatchReason], CatalogueCoverage)
   Builds structured reasons ONLY from rules that actually fired and scores that were
   actually computed, each with observed value, threshold and source product/candidate.
   Never invents a reason. Also builds the coverage funnel: total products -> eligible
   -> products with feasible candidates -> candidates generated (after pruning) ->
   candidates scored -> candidates at/above threshold -> candidates passing validation
   -> candidates passing guardrails.

3. app/core/diagnostics.py (finish it if Phase 11 built only what it needed):
   diagnostic_utility_score(...) with weights from config and documented 0-1
   normalization per component. Used for (a) fallback ranking and (b) recording the
   winner's advisory score in the trace. It may never reorder an ML result.

4. app/core/recommendation.py:
       recommend(customer, portfolio, requirement, catalogue, user_id=None)
           -> Recommendation

   Fixed orchestration order:
     financial -> portfolio -> personalization -> eligibility
       -> candidate generation -> risk -> ML scoring
       -> WALK the ML ranking in order:
            for each scored candidate, in descending suitability:
              if suitability < SUITABILITY_ACCEPTANCE_THRESHOLD: stop the walk
              validate -> if fail: record, continue
              guardrails -> if blocked: record, continue
              else: select and stop
       -> assemble result

   Status resolution:
     no product eligible                          -> NO_ELIGIBLE_PRODUCTS
     eligible but zero feasible candidates        -> NO_FEASIBLE_CANDIDATES
     feasible candidates, all guardrail-blocked   -> ALL_CANDIDATES_BLOCKED
     scored, none at/above threshold (or none
       surviving validation+guardrails above it)  -> NO_SUITABLE_LOAN
     otherwise                                    -> RECOMMENDED

   Set recommendation_source from whether the recommender or the diagnostic fallback
   produced the ordering. NEVER manufacture a recommendation to avoid NO_SUITABLE_LOAN.

   GUARDRAIL / VALIDATION SURFACING (required): if the model's top-ranked candidate was
   rejected by validation or a guardrail, the response must carry it as
   ml_top_choice_blocked with the candidate, its suitability, the exact rule that
   blocked it and the cap value, alongside the recommended safer option. This is a
   core product behavior, not a detail.

   Alternatives = the next ML-ranked candidates that also pass validation and
   guardrails (count from config), in ML order — never re-sorted by any other score.

   Populate the full DecisionTrace listed in AGENTS.md section 9, including the whole
   validation walk row by row and the winner's advisory diagnostic score.

Tests in tests/test_recommendation.py:
- End-to-end call returns a complete Recommendation for a normal customer, with
  status RECOMMENDED and source ML_RANKER.
- A customer with no portfolio gets a valid borrow-only recommendation.
- A cold-start customer (user_id None) gets a valid recommendation.
- ORDERING INTEGRITY: with a stubbed recommender returning a known scrambled ordering,
  the selected candidate is the highest-scoring one that passes validation and
  guardrails — proving nothing downstream re-sorts. Assert the alternatives order
  matches ML order exactly.
- A Conservative customer whose ML top choice violates a guardrail receives the safer
  option AND a populated ml_top_choice_blocked with the correct rule name and cap.
- A customer for whom every scored candidate falls below the threshold returns
  NO_SUITABLE_LOAN with a populated mismatch reason list and NO selected candidate.
- The four non-RECOMMENDED statuses are each produced by a constructed fixture and are
  distinguishable from one another.
- Coverage funnel counts are internally consistent (each stage <= the previous).
- Every mismatch reason references a rule that actually fired (assert the reason's
  observed value matches the fixture).
- With the recommender artifact absent, the result is still valid, source is
  DETERMINISTIC_FALLBACK, and ml_suitability is None.
- Determinism: the same customer run twice produces identical output.
- decision_trace is populated and includes at least one eligibility elimination reason
  and the full walk log.

Exit criteria: tests pass, full suite passes, no EMI recomputation outside
finance_math, no scoring formula in the orchestrator, ordering integrity proven by
test, all five statuses proven by test.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 13 — XAI + LLM Explanation

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-12 complete. Re-read the prompt string rule in
AGENTS.md section 5 before writing any code — it governs this entire phase.

You are executing PHASE 13 only: explanation. The LLM explains; it never decides and
never computes.

Build:

1. app/explain/xai.py:
       explain_recommendation_choice(scored_candidates, winner)
           -> per-feature signed contributions for the WINNING candidate, plus a
              contrast against the runner-up: which features pushed the winner above it
       explain_risk(features) -> feature contributions for the risk classifier
   The primary XAI target is the RECOMMENDER, not the risk model. Explaining only risk
   is a v1.0 behavior and is insufficient here.

   CONTRIBUTIONS COME FROM XGBOOST'S NATIVE TreeSHAP: predict(..., pred_contribs=True).
   Both models are tree ensembles, so this gives exact SHAP values with NO extra
   serving dependency. Do NOT import the shap package here — it is a training-only
   extra (AGENTS.md 14), and importing it in app/ breaks the memory budget and the
   serving-import test.
   Structured feature-contribution data only. No prose. If contribution computation
   fails, degrade to feature_importances_ (gain) and flag which was used.
   Gate the endpoint on ENABLE_XAI_ENDPOINT from config.

   Run scripts/measure_memory.py after this phase and record the numbers — this is
   the second of three memory checkpoints.

2. app/explain/prompts.py: every prompt string in the system, as named constants or
   builder functions, versioned with PROMPT_VERSION. Each prompt must explicitly
   instruct the model that it may not compute, estimate, or introduce any number not
   present in the supplied payload; may not name a product or lender not in the
   payload; and may not author or re-word a rejection or mismatch reason.
   Separate prompts for: a successful recommendation, a guardrail-blocked top choice,
   a NO_SUITABLE_LOAN outcome, and a what-if scenario comparison.

3. app/explain/llm.py:
       explain_recommendation(recommendation) -> str
       explain_mismatch(recommendation) -> str
       answer_question(question, recommendation, scenario_result) -> str
   Each builds a validated structured payload of already-computed values and passes it
   to a prompt from prompts.py. No inline prompt text. No PII in the payload.
   The payload for a fallback result must carry the fallback fact, and the prompt must
   require the explanation to say the recommendation came from the deterministic
   fallback rather than the model.

4. verify_numeric_grounding(response_text, payload) -> GroundingOutcome

   PORT THE PHASE R NORMALIZER AND ITS CORPUS. Move spikes/grounding's corpus to
   tests/data/grounding_corpus.jsonl and re-implement the guard properly against the
   real payload schema. Do not redesign it from scratch — Phase R already validated
   the rule set against the corpus; this phase productionizes it.

   THREE OUTCOMES, NOT A BOOLEAN (this is what stops the false-positive problem):
       GROUNDED    every extracted financial figure matched   -> accept
       UNVERIFIED  a token could not be confidently parsed    -> ACCEPT, flag, log
       UNGROUNDED  a token parsed confidently as a financial
                   figure with no payload match               -> reject, use template
   An unparseable token is a guard limitation, not evidence of a hallucination, and
   must not cost the user their explanation. Collapsing these back into a boolean is
   forbidden.

   - Extract only FINANCIAL FIGURES — amounts, EMIs, interest totals, rates, tenures,
     scores. A token counts as financial only IN FINANCIAL CONTEXT: adjacent to a
     currency symbol, a percent sign, or a cue word (EMI, interest, rate, tenure,
     months, years, score, lakh, crore, Rs), or above the configured magnitude floor.
   - Match against an EXPANDED ACCEPTED SET built from each payload figure — the
     value, its lakh/crore forms, sensible roundings, percent/decimal duals,
     month/year duals — rather than trying to parse every possible spelling:
       "6,00,000" / "600000" / "6 lakh" / "6L" / "₹6,00,000"  -> 600000
       "8%" / "0.08"                                          -> match either form
       "48 months" / "4 years"                                -> 48
     Compare with a small tolerance for rounding (within 1% or ±1 rupee).
   - IGNORE structurally: ordinals (1st, 2nd), list markers, "top 3"-style counts,
     dates, and any number inside a word.

5. Payload builders emit DISPLAY STRINGS alongside every figure ("₹6,00,000",
   "48 months", "8.0%"), and prompts instruct the model to reproduce them verbatim.
   Prevention is the primary mechanism; the guard is the safety net.

6. verify_entity_grounding(response_text, payload) -> GroundingOutcome
   Product names and lender names in the response must exist in the payload. An
   invented product is UNGROUNDED on the same path as an invented number.

   On UNGROUNDED from either guard: reject the LLM output, fall back to the
   deterministic template explainer, and log the rejection with the offending figure or
   entity. On UNVERIFIED: accept, set a flag on the response, and log the token so the
   normalizer can improve. These guards may not be bypassed or disabled, and their
   tolerance may not be widened to make a demo pass.

7. A deterministic template explainer as the fallback path, covering all five
   recommendation statuses, so the system produces a sensible explanation with the LLM
   unavailable.

Tests in tests/test_grounding.py — THE CORPUS IS THE TEST:
- Run the guard over every case in tests/data/grounding_corpus.jsonl (60+ cases).
  REQUIRED: 100% of UNGROUNDED cases rejected, and ZERO false rejections of GROUNDED
  cases. A single false rejection fails the phase.
- FALSE-POSITIVE SUITE (must be corpus cases): "₹6,00,000", "6 lakh", "8%" for a 0.08
  rate, "4 years" for 48 months, "here are your 3 alternatives", "Option 2",
  "1st recommendation". If any of these rejects, the normalizer is wrong — fix the
  normalizer, never the corpus label, never the tolerance.
- An ambiguous token returns UNVERIFIED and the response is ACCEPTED with a flag.
- verify_entity_grounding returns UNGROUNDED for a response naming a lender absent
  from the payload.

Tests in tests/test_explain.py:
- The fallback template produces a valid explanation for each of the five statuses
  with no LLM call.
- A DETERMINISTIC_FALLBACK recommendation's payload carries the fallback fact, and the
  template explanation states it.
- No prompt string exists outside prompts.py (grep-based test is acceptable).
- XAI returns one contribution per pair feature column for the winning candidate, and
  a non-empty contrast against the runner-up.

Exit criteria: tests pass, full suite passes, the grounding corpus scores 100% on
UNGROUNDED with zero false rejections, the three-outcome behaviour is proven by test,
LLM failure path proven by test, the shap package is NOT imported anywhere in app/
(the serving-import test from P0 must still pass), memory measured and recorded.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 14 — FastAPI Surface

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phases 0-13 complete.

You are executing PHASE 14 only: the API layer. Routes contain NO business logic —
they validate, call a core module, and return. If you write a calculation or a
selection rule in a route handler, you have violated the module map.

Build app/api/ with:
    POST /financial-health      -> financial metrics
    POST /portfolio-analysis    -> portfolio metrics
    GET  /loan-products         -> catalogue
    POST /eligibility           -> eligibility results (all products, with reasons)
    POST /risk-prediction       -> risk (clearly labelled a signal, not a decision)
    POST /candidates            -> generated candidates
    POST /recommend             -> full recommendation (THE primary endpoint)
    POST /scenario              -> what-if: re-run the FULL pipeline with modified inputs
    POST /explanation           -> XAI + LLM explanation
    GET  /coverage              -> catalogue coverage funnel for a given request
    GET  /health                -> liveness
    DELETE /personalization/{user_id} -> erase stored history for that user

Requirements:
- Models load once at application startup via a lifespan handler that calls
  load_models() from app/ml/. Never at module import, never per request.
- All request/response bodies are Pydantic schemas from app/schemas/.
- /recommend always returns recommendation_status, recommendation_source, the coverage
  funnel and the decision trace — including for every non-RECOMMENDED status. A
  NO_SUITABLE_LOAN result is a 200 with a complete body, NOT a 404 and NOT an error.
- /scenario must re-run the SAME trusted pipeline end to end: modified inputs ->
  financial/portfolio features -> candidates -> ML scoring -> validation -> guardrails.
  It may NOT adjust a previous recommendation arithmetically and may not shortcut to
  the LLM.
- CORS enabled for the local frontend origin (from config).
- Errors return structured JSON with a code and message; never leak a stack trace.

Tests in tests/test_api.py using TestClient:
- /recommend returns 200 with a complete recommendation for a valid payload, with
  source ML_RANKER.
- /recommend works for a customer with no portfolio.
- /recommend works for a cold-start customer with no user_id.
- /recommend returns 200 with status NO_SUITABLE_LOAN, populated mismatch reasons and
  a coverage funnel for the unmatched fixture customer.
- Invalid payloads return 422.
- /scenario with reduced income produces a different recommendation than baseline AND
  a different set of ML suitability scores (proving the pipeline re-ran, not arithmetic).
- With the recommender artifact absent, /recommend still returns 200 with source
  DETERMINISTIC_FALLBACK and null ml_suitability.
- DELETE /personalization/{user_id} removes history and a subsequent /recommend for
  that user reports cold start.
- /health returns 200.

Exit criteria: `uvicorn app.main:app` starts cleanly, /docs renders, all API tests
pass, full suite passes, no business logic in route handlers.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 15 — Frontend

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. Phase 14 complete; the API is running.

You are executing PHASE 15 only: the React + TypeScript frontend. No backend changes.
If you find a backend bug, report it — do not fix it in this phase.

Build a Vite + React + TypeScript + Tailwind app with Axios and Recharts:

Screens/flow:
1. Financial profile input form.
2. Portfolio input (add/remove holdings) with a clearly visible "Skip - I have no
   investments" path that must work end to end.
3. Loan requirement + risk appetite selector (Conservative / Moderate / Aggressive).
4. Results screen. It has TWO top-level shapes and both must be first-class:

   A) RECOMMENDED:
      - Headline: product, lender, amount, tenure, EMI, financing strategy
      - ML SUITABILITY SCORE, displayed as a model output with a plain-language
        caption ("how well this option fits your profile, scored by the model")
      - RECOMMENDATION SOURCE badge: "Recommended by the ML model" vs
        "Deterministic fallback — the recommendation model is unavailable".
        The fallback badge is visible, not a tooltip. Never show a fallback result
        without it.
      - "Why this loan" — driven by the recommender's XAI contributions: top positive
        and top negative factors, and what pushed it above the runner-up
      - BLOCKED-TOP-CHOICE CALLOUT: when ml_top_choice_blocked is present, display it
        prominently: "The model's best match for you was X, but it exceeds your
        <appetite> risk profile (<rule>: cap <cap>, this option <observed>), so we
        recommend Y instead." This is the product's signature moment — make it
        visible, not buried.
      - Alternatives: the next ML-ranked options, in ML order, each with its
        suitability score
      - Strategy comparison chart (borrow vs liquidate vs hybrid: EMI, total interest,
        remaining portfolio) via Recharts
      - CATALOGUE COVERAGE funnel, compact
      - ELIMINATED OPTIONS section (collapsible, collapsed by default): from the
        decision trace, which products were filtered out at eligibility and why, and
        which candidates were eligible but scored below the suitability threshold.
        KEEP THESE TWO GROUPS VISUALLY SEPARATE — "you don't qualify" and "you
        qualify but it isn't a good fit for you" are different statements.
        Phrase both as product-fit statements ("this product requires a credit score
        of 750"), never as a formal credit decision about the user.

   B) NO_SUITABLE_LOAN / NO_ELIGIBLE_PRODUCTS / NO_FEASIBLE_CANDIDATES /
      ALL_CANDIDATES_BLOCKED:
      A dedicated, well-designed screen — NOT a generic rejection and NOT an error
      state. Show:
      - A clear headline naming which of the four outcomes occurred
      - The coverage funnel, so the user sees how far their request got
      - The structured mismatch reasons, each as a concrete statement with the
        observed value and the threshold
      - What would change the outcome, derived ONLY from the reasons present
        (e.g. a shorter tenure, a smaller amount) — never invented advice
      Example framing:
        Why no loan was recommended
        ✓ Your requested amount is supported by 4 products
        ✗ Your preferred tenure of 96 months exceeds every product's limit (max 84)
        ✗ The remaining eligible options scored below the suitability threshold
          (best 0.34, threshold 0.55)
        ✗ Your conservative profile prevents the financing strategy they require

5. What-if panel calling /scenario, showing how suitability scores move, not just EMI.

Rules:
- All TypeScript interfaces mirror the backend Pydantic schemas exactly, including
  every enum value of RecommendationStatus and RecommendationSource. Define them once
  in src/types/ and import everywhere. Handle all five statuses exhaustively — a
  switch over status must not have a silent default.
- API base URL from a Vite env var (VITE_API_BASE_URL), never hardcoded. Vite bakes
  this in at BUILD time — the deployed build must be built with the deployed API URL.
  Commit .env.example for the frontend too.
- Loading and error states on every API call.
- A visible label wherever synthetic data is surfaced.
- A visible non-advice line in the footer of the results screen, on both shapes.

Exit criteria: `npm run build` succeeds with zero TypeScript errors, no eslint errors
introduced, and the full flow works against the live API including the no-portfolio
path, the blocked-top-choice callout, the NO_SUITABLE_LOAN screen, and the fallback
badge (test it by renaming the model artifact).

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 16 — Demo Hardening

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. All prior phases complete.

You are executing PHASE 16 only: hardening and demo readiness. Do not add features.
Do not refactor working code. Do not add a third ML model. If you are tempted to build
something new, stop and report it as future work instead.

Do:
1. Create 5 seeded demo customers in data/demo_customers.json, each proving one
   behavior:
   - Conservative investor with a substantial portfolio whose ML top choice is
     guardrail-blocked (the headline demo: model chose X, rule blocked it, we
     recommend Y)
   - Customer with no portfolio at all (proves the optional-portfolio path)
   - Aggressive investor where a hybrid strategy wins on ML suitability
   - Customer for whom NO catalogue product is suitable (proves NO_SUITABLE_LOAN with
     structured reasons and the coverage funnel)
   - Returning customer with history whose personalization features visibly shift the
     ranking versus the same profile cold-start
   Verify each runs end to end through the UI and produces the intended result.

   If a demo customer does not produce the intended outcome, fix the FIXTURE, not the
   thresholds. Lowering SUITABILITY_ACCEPTANCE_THRESHOLD or widening a guardrail cap to
   force a demo result is falsifying the product and is forbidden.

2. Write README.md: what the system is, the v2.0 architecture diagram from CONTEXT.md,
   the ML-first decision flow, setup instructions (venv, install, generate data, build
   dataset, train both models, run API, run frontend — no Docker), API summary, and an
   explicit "Synthetic Data" section naming exactly which data is synthetic and
   stating that relevance labels come from training/labeling.py.

3. Write LIMITATIONS.md, stated plainly, not defensively:
   - The primary recommender is trained on synthetic relevance labels and partially
     reproduces the labeling policy; reported NDCG measures agreement with that
     policy, not real recommendation quality
   - Agreement between the ML recommendation and the diagnostic utility baseline is
     not validation — they share ancestry
   - Risk model probabilities are uncalibrated beyond the reported Brier/reliability
   - Suitability calibration is fitted on synthetic labels and inherits their bias
   - Portfolio and personalization features carry no learned default signal
   - No fairness audit performed
   - Yield/liquidation comparison is simplified: ignores capital gains tax, exit loads,
     and FD break penalties
   - Decision-support only; not financial advice; no custody or execution

4. Update PRODUCTION_ROADMAP.md if this phase surfaced anything new.

5. Run the full test suite, fix any regression, confirm no lint errors.

6. MODEL ARTIFACT DECISION (needed by P17): check the total size of models/.
   - If under ~50 MB total: commit them and remove models/ from .gitignore. Safest
     for deployment — the host does not need to run training.
   - If larger: keep them out of git and document that P17 must run the training
     scripts as part of the build step, or fetch artifacts from storage.
   State clearly in your report which path you took and the actual file sizes.

7. Verify every non-negotiable in CONTEXT.md section 14 holds. Report on each one
   individually with a yes/no and evidence. Pay particular attention to #1 (no
   deterministic score reorders the ML ranking) and #9 (the system can return
   NO_SUITABLE_LOAN) — those are the two the redesign exists to guarantee.

Exit criteria: all five demo customers run clean end to end and produce their intended
distinct outcomes, full suite green, docs written, non-negotiables audited item by item.

Update PHASE_STATUS.md, report, then STOP.
```

---

## PHASE 17 — Deployment (no Docker)

**Goal:** a live, shareable URL. Two supported targets — pick ONE in step 0 and do not build both.

**Prompt:**

```
Read CONTEXT.md and AGENTS.md. All prior phases complete and green.

You are executing PHASE 17 only: deployment. NO DOCKER, no Dockerfile, no
docker-compose, no container registry — the stack is deployed with a plain runtime and
a process manager. Do not add features. Do not refactor working code. If something
fails to deploy because of a code bug, fix the minimum needed and report it.

STEP 0 - Choose ONE target and state your choice before doing anything:
  (A) Managed PaaS  - backend on Render/Railway (native Python runtime, NOT their
      Docker path), frontend on Vercel/Netlify, managed Postgres or SQLite for the
      personalization store. Fastest to a public URL. Default unless told otherwise.
  (B) Single VM     - gunicorn with uvicorn workers, managed by systemd, behind nginx
      as reverse proxy with TLS; frontend built to static files served by nginx.

COMMON WORK (both targets):

1. Verify a clean-machine install works. In a fresh virtualenv:
       pip install -r requirements.txt
   Every dependency must be pinned. Confirm the pinned Python in runtime.txt matches
   what you test.

2. Startup path must not require training. The app must boot with the committed
   committed model artifacts (per the P16 decision). If models are absent at boot, the P11 fallback
   must engage and /recommend must still serve — verify by temporarily renaming the
   models directory and hitting the endpoint, and confirm the response carries
   recommendation_source = DETERMINISTIC_FALLBACK.

3. Environment variables. Produce a complete deployment env list from app/config.py:
   LLM API key, model paths, personalization database URL, CORS_ALLOWED_ORIGINS,
   CONFIG_VERSION, FEATURE_VERSION, PROMPT_VERSION, LOG_LEVEL. Every one documented.
   No secret is ever committed.

4. Personalization store. Confirm the database URL resolves on the target and the
   schema is created at startup. On a PaaS free tier with an ephemeral filesystem,
   SQLite does NOT persist across restarts — either use the managed Postgres or state
   plainly in DEPLOY.md that personalization resets on restart. Do not pretend it
   persists.

5. CORS. CORS_ALLOWED_ORIGINS must include the deployed frontend origin. A wildcard is
   acceptable only for the demo and must be noted in the README as demo-only.

6. Frontend build. VITE_API_BASE_URL is baked in at build time, so the production build
   must be built against the deployed backend URL. Verify by inspecting the built
   bundle for the correct URL before shipping.

7. MEMORY VERIFICATION - historically the most common deployment failure for this
   stack, and the reason the serving dependency boundary was set at P0 rather than
   discovered here. The mitigations are already in place: pandas, scikit-learn and the
   shap package are training-only; the calibrator is knots + numpy.interp;
   contributions come from XGBoost's pred_contribs; models load from JSON.
   This step VERIFIES that budget on the real target, it does not invent it.
     - Run scripts/measure_memory.py on the deployed instance: after startup, and
       after one /recommend call. This is the third checkpoint (P11, P13, P17) —
       compare against the P11 and P13 numbers and explain any large jump.
     - Confirm the P0 serving-import test passes in the deployed environment.
     - Use ONE worker by default; each gunicorn/uvicorn worker loads its own copy of
       both models, so worker count is a memory decision, not a throughput one.
   If it still exceeds the target's limit, the only permitted lever is disabling the
   XAI endpoint via ENABLE_XAI_ENDPOINT and documenting it.
   Do NOT solve this by removing the fallback path, the grounding guards, the
   calibrator, or the primary recommender.

8. Cold start. Note first-request latency after idle (free tiers sleep). Confirm the
   lazy loader from P11 means the app answers /health before models finish loading.

TARGET A ONLY (PaaS):
  - Backend start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  - Build command: pip install -r requirements.txt
  - Configure the frontend project with VITE_API_BASE_URL pointing at the backend URL.
  - Set all env vars in the platform dashboard, not in a committed file.

TARGET B ONLY (VM):
  - gunicorn -k uvicorn.workers.UvicornWorker -w 2 app.main:app bound to a local port.
  - A systemd unit (deploy/plrs.service) with Restart=always, an EnvironmentFile
    pointing at a root-owned env file with 600 permissions, correct WorkingDirectory.
  - An nginx site config (deploy/nginx.conf) reverse-proxying to the app port and
    serving the built frontend as static files.
  - Document the deploy sequence: pull, install, restart unit, reload nginx.

9. DEPLOY.md documenting the chosen target: exact steps to deploy from scratch, the
   full env var table, how to roll back (including rolling back a model artifact
   independently of code), and known limitations (cold starts, memory ceiling,
   personalization persistence, demo-only CORS if applicable).

Exit criteria (verify each against the LIVE deployment, not localhost):
- Public URL loads the frontend.
- The full flow completes end to end against the deployed API.
- The no-portfolio path works live.
- The Conservative blocked-top-choice demo customer works live.
- The NO_SUITABLE_LOAN demo customer works live and shows structured reasons.
- The fallback badge appears when the recommender artifact is unavailable.
- /health returns 200; /docs renders.
- Measured memory is within the target's limit.
- No secrets in the repo (grep the history for the API key before finishing).

Update PHASE_STATUS.md, report, then STOP.
```

---

## Per-phase reminder to append to any prompt if the agent drifts

```
You are still in PHASE <n>. Re-read CONTEXT.md section 14 and AGENTS.md sections 0 and 6.
The ML recommender chooses; deterministic code validates. Do not write a score that
reorders the ML ranking. Do not let ML produce a rupee figure. Do not start the next
phase. Do not add features not named in this phase. Do not weaken a test, a guardrail
cap, or the suitability threshold to make something pass. If you are blocked, set
BLOCKED in PHASE_STATUS.md, state the specific blocker, and stop.
```

---

## Appendix — what changed from the v1.0 plan

For anyone who worked on the previous plan. This is orientation, not instruction; the phase prompts above are authoritative.

| v1.0 | v2.0 | Why |
|---|---|---|
| P4 generated ranker training data as an afterthought | P7 designs the relevance labeling policy as a first-class phase | The training target defines what "suitable" means; it is the core of an ML-first system |
| Optimization ran after ML, feeding a deterministic chooser | Candidate generation (P5) runs **before** ML, feeding the recommender | So the model chooses amount, tenure and strategy — not just the product |
| Guardrails pre-filtered the option space | Guardrails validate the ML ranking after scoring (P6 builds, P12 walks) | So the model's genuine top choice is knowable and surfaceable when blocked |
| Recommendation Engine fused signals with a weighted utility function and decided | Orchestrator (P12) assembles; the utility function survives as `diagnostic_utility_score` for fallback and audit only | The decision moves to the model |
| Ranker was cuttable, with the utility function as the fallback product | The recommender is the product; the utility function is a flagged degradation | Cutting it would remove the system's intelligence |
| No concept of "no suitable loan" | Five recommendation statuses, structured mismatch reasons, coverage funnel (P12, P15) | The system must be able to say "nothing here fits you, and here is exactly why" |
| XAI explained the risk model | XAI explains the recommender's choice, with runner-up contrast (P13) | The recommender is what makes the decision now |
| Metrics: accuracy and NDCG in passing | Ranking metrics with three mandatory baselines (P10) | A recommender that cannot beat cheapest-EMI-first is not a recommender |
| Personalization absent | Personalization store and features as a phase (P3), feeding the recommender | Personalization belongs in the model's inputs, not in a parallel scorer |
| Risky components discovered mid-build | **Phase R** validates the labeling invariants, the grounding normalizer and the memory budget before P0 | All three are cheap now and expensive later — see CONTEXT.md 17 |
| pandas / sklearn / shap assumed everywhere | Serving import boundary fixed at P0 and enforced by a test | A memory ceiling found at P17 is a rewrite; declared at P0 it is a one-line decision |
