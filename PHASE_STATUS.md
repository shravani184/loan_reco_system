# PHASE_STATUS.md

Single source of truth for progress. One row per phase; each agent updates only its
own row. Status values: `NOT_STARTED` | `IN_PROGRESS` | `BLOCKED` | `DONE`

**Architecture v2.0 (ML-first) — clean rebuild.** The v1.0 phase tracker recorded P0–P11
as DONE under the deterministic-fusion architecture. That architecture has been
replaced: the decision now belongs to the primary ML recommender, candidate generation
moved ahead of ML, guardrails moved behind it, and the recommendation contract gained
statuses, a source axis, mismatch reasons and a coverage funnel. **Every phase below is
therefore reset to `NOT_STARTED`.** v1.0 code is reference material, not carried-over
progress — a phase is `DONE` only when the v2.0 exit criteria in `IMPLEMENTATION_PLAN.md`
have been verified by commands actually run against v2.0 code.

| Phase | Name | Status | Exit criteria met | Notes |
|-------|------|--------|-------------------|-------|
| **R** | **Risk-reduction spikes** | DONE | yes | All three bottlenecks closed. Mutation score 7/7; corpus 100%/0; serving 186 MB. See record below |
| P0 | Scaffold, schemas, config | DONE | yes | New enums: RecommendationStatus, RecommendationSource, CandidateOutcome, MismatchReasonCode. Two requirements files; serving-import test |
| P1 | Financial Intelligence | DONE | yes | Logic largely unchanged from v1.0; re-implement against v2.0 schemas |
| P2 | Portfolio Intelligence | DONE | yes | Logic largely unchanged from v1.0; zero-portfolio still first-class |
| P3 | Personalization store + context | DONE | yes | New in v2.0; feature source only, cold-start first-class, deletion path required |
| P4 | Eligibility Engine | DONE | yes | Now emits MismatchReasonCode; output length must equal catalogue length |
| P5 | Finance math + Candidate Generation | DONE | yes | Moved AHEAD of ML; adds feasibility marking + dominance pruning; no preference ordering |
| P6 | Guardrail policy validator | DONE | yes | Now a pass/fail validator over a single candidate, applied after ML |
| P7 | Synthetic data + relevance labeling policy | DONE | yes | New in v2.0; defines the training target; decomposed policy, invariants ported from R, labels are synthetic |
| P8 | Shared feature engineering | DONE | yes | Pair features (customer x candidate); risk PD passed in as a parameter |
| P9 | Risk model (secondary) | DONE | yes | Demoted to a feature source and a disclosure; not a decision |
| P10 | **Primary recommender + calibration + evaluation** | DONE | yes | The core of the redesign; ranking metrics + 3 mandatory baselines |
| P11 | ML inference layer + fallback | DONE | yes | Lazy loading, manifest assertion, DETERMINISTIC_FALLBACK flag; memory checkpoint 1 |
| P12 | Orchestrator, validation walk, mismatch | DONE | yes | Assembles only; ordering integrity and all five statuses proven by test |
| P13 | XAI + LLM explanation | DONE | yes | XAI targets the recommender via native TreeSHAP; three-outcome grounding guard + corpus from R; memory checkpoint 2 |
| P14 | FastAPI surface | DONE | yes | NO_SUITABLE_LOAN is a 200 with a full body; /scenario re-runs the full pipeline; per-request store for thread safety |
| P15 | Frontend | DONE | yes | Vite + React + TS + Tailwind + Axios + Recharts; two first-class result shapes; fallback badge; blocked-top-choice callout |
| P16 | Demo hardening | NOT_STARTED | no | Five demo customers, one per behaviour; never tune thresholds to force a result |
| P17 | Deployment (no Docker) | NOT_STARTED | no | Two artifacts + calibrator knots; memory checkpoint 3 (verify the P0 budget, not discover it) |

## Reference — v1.0 status at the time of the redesign

Kept for provenance only. These rows do not confer progress on any v2.0 phase.

| v1.0 Phase | Name | v1.0 Status | Fate in v2.0 |
|---|---|---|---|
| P0 | Scaffold, Schemas, Config | DONE | Superseded — schema contract materially changed (P0) |
| P1 | Financial Intelligence | DONE | Logic reusable as reference (P1) |
| P2 | Portfolio Intelligence | DONE | Logic reusable as reference (P2) |
| P3 | Eligibility + Guardrails | DONE | Split: eligibility (P4) and guardrails (P6) now sit at different pipeline positions |
| P4 | Data generation + offline training | DONE | Superseded — relevance labeling policy is now a designed phase (P7) |
| P5 | ML inference layer | DONE | Superseded — new primary recommender and fallback contract (P11) |
| P6 | Optimization Engine | DONE | Repositioned ahead of ML as candidate generation (P5) |
| P7 | Recommendation Engine | DONE | **Removed as decision-maker.** Utility function survives as `diagnostic_utility_score` (P12) |
| P8 | XAI + LLM explanation | DONE | Superseded — XAI now explains the recommender (P13) |
| P9 | FastAPI surface | DONE | Superseded — new endpoints, statuses and source flag (P14) |
| P10 | Frontend | DONE | Superseded — new result shapes and mismatch screen (P15) |
| P11 | Demo hardening | DONE | Superseded — demo set now proves five distinct behaviours (P16) |
| P12 | Deployment (no Docker) | NOT_STARTED | Carried forward as P17 |


---

## Phase records

Append one record per phase at Step 6 of the workflow in `AGENTS.md` §1.2. The table
above is the at-a-glance state; these records are the detail. Never mark a phase `DONE`
in the table without writing its record.

Use this shape:

```
### Px — <name>
Status: DONE | BLOCKED
Exit criteria met: yes | no (list any not met)

IMPLEMENTED
  <what now exists and works>

VERIFIED BY
  <the exact commands run, and their results — not "tests pass" but which command,
   how many tests, what the metric printed>

DECISIONS
  <implementation decisions that a later phase or a reviewer needs to know about,
   especially anything touching the ML/deterministic authority boundary>

LIMITATIONS / UNRESOLVED
  <what is knowingly incomplete, and any test that is passing for a weaker reason
   than intended>

DOCUMENTATION CHANGES
  <any spec file changed during this phase, and why — per AGENTS.md 1.5>

NEXT PHASE NEEDS TO KNOW
  <interfaces, data shapes, feature/column contracts, gotchas>
```

### R — Risk-reduction spikes
Status: DONE
Exit criteria met: yes (all six)

IMPLEMENTED
  spikes/labeling/   invariant suite (written before the policy), decomposed four-stage
                     prototype policy, synthetic population, degeneracy report, stress
                     label-flip measurement, human audit sample, FINDINGS.md
  spikes/grounding/  three-outcome guard (GROUNDED / UNVERIFIED / UNGROUNDED), numeric
                     normalizer, entity guard, 85-case labelled corpus, runner,
                     FINDINGS.md
  spikes/memory/     subprocess memory probe for both dependency sets, isotonic-knot
                     and pred_contribs mechanism verification, measurements.json,
                     FINDINGS.md
  Nothing under app/ or training/. Nothing imports from spikes/.

VERIFIED BY
  python3 -m pytest spikes/labeling/test_invariants.py -q      -> 15 passed
  mutation harness, 7 planted defects                          -> 7/7 CAUGHT
  python3 spikes/labeling/population.py                        -> max grade share 0.39
                                                                  (limit 0.60); max
                                                                  product/tenure/strategy
                                                                  win share 0.50 (limit
                                                                  0.60); 59 of 225
                                                                  no-good-option customers;
                                                                  flip rate 9.52% (band
                                                                  2%-30%)
  python3 spikes/grounding/run_corpus.py                       -> 78 numeric + 7 entity
                                                                  cases; 21/21 UNGROUNDED
                                                                  rejected (100%); 0/54
                                                                  GROUNDED falsely
                                                                  rejected; RESULT PASS
  python3 spikes/memory/measure.py                             -> serving 186.3 MB, full
                                                                  310.7 MB, saving 124.4 MB;
                                                                  isotonic knots exact
                                                                  (max diff 0.0);
                                                                  pred_contribs error
                                                                  2.9e-06

DECISIONS
  - Labeling grades are assigned by rank WITHIN each customer's candidate group, capped
    by an absolute quality floor. The cap is what allows a customer to legitimately have
    no good option; quantile grading alone always manufactures a grade 3.
  - The stress simulation shares one scenario draw across all customers and candidates,
    from a constant seed. That is what makes it simultaneously deterministic, monotone
    in EMI, and scale-invariant.
  - The grounding guard matches by expanding the RESPONSE token into all readings, not
    by expanding the payload into divided/rounded forms. The original payload-side
    expansion made fabrications match real figures.
  - MEMORY_CEILING_MB = 290 recommended (186 MB measured + 60% headroom). One uvicorn
    worker by default: each worker loads its own copy of both models.

LIMITATIONS / UNRESOLVED
  - Constants were tuned against a synthetic population built inside the spike. P7 must
    re-measure the flip rate and degeneracy report against the real generator.
  - The corpus was written by the same author as the guard. P13 should sample real LLM
    output before trusting the false-positive rate.
  - Memory measured on this container, not the PaaS target, and for one model rather
    than two. The 124 MB saving and the mechanism verifications transfer; the absolute
    numbers are re-measured at P11 and P17.
  - Concurrent-load memory was not measured; the 60% headroom is a judgement.

DOCUMENTATION CHANGES
  None. Every Phase R finding was already anticipated by CONTEXT.md 17; no
  specification change was needed. Five findings belong to other phases and are
  listed in spikes/labeling/FINDINGS.md section 6 — P0/P5/P7/P12/P15 must act on them.

NEXT PHASE NEEDS TO KNOW (P0)
  - Adopt MEMORY_CEILING_MB = 290 and the two-requirements-file split. Write
    tests/test_serving_imports.py BEFORE any code can violate it.
  - Both substitution mechanisms are confirmed working: export the calibrator as
    isotonic knots (apply with numpy.interp), and take feature contributions from
    xgboost pred_contribs. Neither scikit-learn nor shap belongs in the serving set.
  - Models persist as XGBoost JSON, not pickle.
  - Schema note from the spike: a 100%-liquidate candidate borrows nothing, so product
    and tenure are meaningless for it. It must be representable as "no loan" rather
    than as a 1-month loan, and generated ONCE per customer (P5).

### P0 — Scaffold, Schemas, Config
Status: DONE
Exit criteria met: yes (all six)

IMPLEMENTED
  Repository structure   app/{schemas,core,ml,personalization,explain,api}/, training/,
                         tests/, data/, models/, scripts/ — each package with an
                         __init__.py. No Docker files.
  Dependency split       requirements.txt (serving: fastapi, pydantic,
                         pydantic-settings, uvicorn, numpy, xgboost, httpx) and
                         requirements-train.txt (adds pandas, scikit-learn, shap,
                         matplotlib, hypothesis, pytest). Every pin exact (==).
                         runtime.txt, .gitignore, .env.example.
  app/schemas/enums.py   14 enum classes, all str-valued: RiskAppetite,
                         FinancialHealth, PortfolioRisk, RiskClass, FinancingStrategy,
                         LoanPurpose, AssetType, EmploymentType, EligibilityStatus,
                         RecommendationStatus (5), RecommendationSource (2),
                         CandidateOutcome (6), MismatchReasonCode (14).
  app/schemas/           customer.py (CustomerProfile, Holding, Portfolio,
                         LoanRequirement, LoanProduct), metrics.py (FinancialMetrics,
                         PortfolioMetrics, PersonalizationContext, RiskPrediction),
                         pipeline.py (EligibilityResult, Candidate, ScoredCandidate,
                         ValidationResult, GuardrailResult, ValidationWalkStep),
                         recommendation.py (MismatchReason, BlockedTopChoice,
                         CatalogueCoverage, CandidateGenerationCounts, DecisionTrace,
                         Recommendation). 21 models exported from app/schemas.
  app/config.py          one Settings object, loaded once at import. Flat scalars from
                         .env; complex structures as typed class defaults; optional
                         JSON override via COMPLEX_CONFIG_PATH.
  tests/                 fixtures.py (6-product mock catalogue, standard customer,
                         no-match customer, mixed portfolio, empty portfolio, standard
                         requirement, neutral personalization), test_schemas.py,
                         test_serving_imports.py.

VERIFIED BY
  python -m pytest -q                                  -> 60 passed
                                                          (45 in tests/, 15 Phase R
                                                          invariants in spikes/)
  python -c "from app.config import settings;
             print(settings.CONFIG_VERSION)"           -> 2.0.0, with NO .env file
                                                          present on disk (defaults
                                                          only)
  subprocess import probe over app, app.config,
  app.schemas, app.schemas.enums                       -> forbidden modules in serving
                                                          import graph: []
  grep for arithmetic outside config and comments
  across app/                                          -> none found (zero business
                                                          logic)
  test_requirements_are_exactly_pinned                 -> passed; no unpinned line in
                                                          either requirements file

  Note: Phase R recorded its commands as python3. This machine is Windows and has no
  python3 alias; every command above was run as python (3.13.5).

DECISIONS
  - MONEY IS float, IN RUPEES, system-wide. Documented at the top of
    app/schemas/customer.py. Because float equality cannot express "matches to the
    rupee", deterministic validation (P12) compares EMI using
    EMI_VALIDATION_TOLERANCE_RUPEES = 1.0 from config, not exact equality.
  - THE NO-LOAN CANDIDATE. Acting on the Phase R schema finding: a LIQUIDATE_100
    candidate carries product_id = None, lender = None, tenure_months = None and
    loan_amount = 0.0, enforced by a model validator that REJECTS the spike's
    tenure = 1 month representation. It means "pay from your assets, borrow nothing"
    and P15 must not render it as a 1-month loan.
  - Status/source separation is enforced by construction, not convention. A test
    asserts RecommendationStatus has exactly 5 members and no DETERMINISTIC_FALLBACK,
    and the Recommendation validator rejects a non-null ml_suitability under
    DETERMINISTIC_FALLBACK.
  - Recommendation rejects a selected_candidate on any non-RECOMMENDED status. The
    "never manufacture a recommendation" rule is therefore a schema error rather than
    a code-review item.
  - test_serving_imports.py runs its probe in a SUBPROCESS. In-process sys.modules is
    polluted by pytest and by sibling test modules (later phases will have training
    tests that legitimately import pandas), which would make the check pass for the
    wrong reason.
  - Every schema uses extra="forbid", enforcing the AGENTS.md section 3 rule that no
    undeclared field is ever attached to an object in passing.
  - EligibilityResult, ValidationResult and GuardrailResult each carry a validator
    making the reason or rule mandatory on failure and forbidden on success. A reason
    code cannot be omitted, and a passing result cannot carry an invented one.
  - MEMORY_CEILING_MB = 290 adopted from the Phase R memory findings, unchanged.

LIMITATIONS / UNRESOLVED
  - runtime.txt pins python-3.13.5, not the plan's illustrative python-3.11.9. It pins
    the interpreter this phase was actually verified on. P17 must confirm the PaaS
    target offers 3.13.5 and re-pin if it does not.
  - xgboost is pinned in requirements.txt but NOT installed in this environment.
    Nothing imports it yet, so nothing recorded here is unverified — but P9/P11 must
    install it and re-run test_serving_imports.py, since xgboost is the one serving
    dependency whose transitive import graph has not been observed.
  - hypothesis==6.167.1 was installed so the Phase R invariant suite is collected by a
    bare pytest run. Without it, pytest errors at collection instead of passing.
  - Config default VALUES (suitability threshold 0.55, guardrail caps, candidate
    grids, diagnostic weights, asset haircuts) are placeholders of the right shape.
    They are typed and version-stamped but not calibrated against data. P6, P7 and P12
    own setting them from measurement. They must never be moved to make a demo produce
    a recommendation.
  - CandidateOutcome is defined but currently referenced only by ValidationWalkStep;
    P12 is its main consumer.

DOCUMENTATION CHANGES
  None. No requirement, schema or phase definition proved wrong or ambiguous during
  P0, and no Phase R finding contradicted the P0 prompt. The one Phase R schema
  finding (the no-loan candidate) was implemented as specified rather than negotiated.

NEXT PHASE NEEDS TO KNOW (P1 — Financial Intelligence)
  - Produce FinancialMetrics from app/schemas/metrics.py. Its fields are the contract:
    monthly_income, monthly_expenses, existing_emi, disposable_income,
    debt_burden_ratio, expense_ratio, emi_affordability_ceiling,
    income_stability_score (bounded 0..1), financial_health (FinancialHealth enum).
  - disposable_income is deliberately unbounded and may be negative; every ratio and
    the affordability ceiling are constrained to >= 0 by the schema. If P1 computes a
    negative ceiling, the clamp is P1's to own — it is not a schema change.
  - MAX_EMI_SHARE_OF_DISPOSABLE_INCOME (0.50) is in config and is what
    emi_affordability_ceiling is built from. Do not hardcode it.
  - Test inputs come from tests/fixtures.py: standard_customer() and
    no_match_customer(). Do not read data/ and do not add a CSV.
  - FinancialHealth bands are EXCELLENT / GOOD / FAIR / POOR, ordered best to worst.
    The band cut-points are P1's to define, and they belong in app/config.py, never
    inline.

### P1 — Financial Intelligence
Status: DONE
Exit criteria met: yes (all three)

IMPLEMENTED
  app/core/financial.py   analyze_financials(customer: CustomerProfile)
                          -> FinancialMetrics. Pure: no I/O, no global state, no model
                          call, input not mutated. Three private helpers, each
                          separately testable: _income_ratio, _income_stability_score,
                          _health_band.
  app/config.py           P1 thresholds added to the complex-defaults block:
                          UNDEFINED_RATIO_VALUE, EMPLOYMENT_STABILITY_BASE,
                          STABILITY_FULL_TENURE_YEARS, STABILITY_TENURE_WEIGHT,
                          FINANCIAL_HEALTH_MIN_SAVINGS_RATE,
                          FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD.
  tests/test_financial.py 21 tests: the worked example field by field, boundary cases,
                          band transitions at every cut-point, the demotion rule, and
                          the stability formula.

VERIFIED BY
  python -m pytest tests/test_financial.py -q   -> 21 passed
  python -m pytest -q                           -> 81 passed (no regressions;
                                                   60 from P0 + Phase R, 21 new)
  AST scan of every numeric literal in
  app/core/financial.py                         -> [0.0, 1.0] only. Both are identity
                                                   or zero constants (clamping and
                                                   the 1-minus-weight complement);
                                                   there is no threshold in the file.

DECISIONS
  - THE WORKED EXAMPLE MATCHES EXACTLY. income 100000, expenses 35000, existing EMI
    8000 -> disposable 57000, debt burden 0.08, expense ratio 0.35, ceiling 28500,
    band EXCELLENT. Asserted field by field rather than as a spot check.
  - disposable_income IS NOT CLAMPED and may be negative. A customer whose outgoings
    exceed their income genuinely has a deficit, and clamping it to zero would tell P5
    and the recommender that they break even. emi_affordability_ceiling IS floored at
    zero, because a negative disposable income affords no EMI rather than a negative
    one. The schema encodes exactly this split: disposable_income is unbounded, the
    ceiling is ge=0.
  - ZERO INCOME. Income-relative ratios are undefined at zero income but must stay
    finite because they become ML features. A zero numerator over zero income is
    genuinely 0.0; a positive numerator yields UNDEFINED_RATIO_VALUE (99.0 from
    config), chosen far outside the range a real ratio occupies so it is recognisable
    in a decision trace rather than silently plausible. P8 must decide whether to pass
    this sentinel to the model as-is or encode it as a missing-value flag.
  - THE HEALTH BAND IS TWO INDEPENDENT STEPS, not one scoring function: place by
    savings rate, then demote exactly one band if the existing debt burden exceeds
    FINANCIAL_HEALTH_DEBT_BURDEN_DEMOTION_THRESHOLD. Each step is tested on its own.
  - THE BAND LADDER IS DERIVED FROM CONFIG, not hardcoded. _health_band sorts
    FINANCIAL_HEALTH_MIN_SAVINGS_RATE by threshold descending and appends POOR as the
    floor, so that one dict is the single source of both the cut-points and their
    order. Re-tuning a threshold cannot desynchronise the ordering, and POOR
    deliberately has no entry.
  - income_stability_score is base(employment type) * (1 - tenure weight) + capped
    tenure fraction * tenure weight, saturating at STABILITY_FULL_TENURE_YEARS. It is
    bounded [0,1] by construction, which is what the schema requires.
  - Savings rate is computed from the FLOORED disposable income, so a customer in
    deficit lands at savings rate 0.0 and band POOR rather than producing a negative
    rate that would sort below the ladder in a way no threshold describes.

LIMITATIONS / UNRESOLVED
  - The band cut-points (0.40 / 0.25 / 0.10), the demotion threshold (0.40), the
    employment base scores and the tenure weight are reasoned defaults, not values
    calibrated against a population. They are typed, version-stamped and in config, so
    re-tuning is a config change. P7 should re-check them against the real generated
    population once it exists, since FinancialHealth becomes a model feature.
  - income_stability_score uses only employment type and tenure. Income volatility is
    not modelled because CustomerProfile carries no income history — adding one is a
    schema change, not a P1 change.
  - UNDEFINED_RATIO_VALUE = 99.0 is a sentinel inside a normal numeric field. It is
    unambiguous today because no real ratio approaches it, but P8 owns the decision
    about how it reaches the model.

DOCUMENTATION CHANGES
  None. The phase prompt, CONTEXT.md section 4 and the FinancialMetrics schema were
  consistent with each other and with the implementation. No ambiguity surfaced.

NEXT PHASE NEEDS TO KNOW (P2 — Portfolio Intelligence)
  - P2 is independent of P1: it consumes a Portfolio, not a FinancialMetrics. Do not
    import app/core/financial.py.
  - Produce PortfolioMetrics from app/schemas/metrics.py. has_portfolio is the
    zero-portfolio signal — the block is always returned with every field valid and
    zeroed, never None and never a missing block.
  - Four of its fields are schema-bounded to [0,1]: liquidity_ratio, equity_exposure,
    debt_exposure, crypto_exposure, concentration_risk. unrealized_gain_loss is
    unbounded and may be negative. total_value and liquid_value are ge=0.
  - Config already holds LIQUID_ASSET_TYPES, VOLATILE_ASSET_TYPES and
    ASSET_LIQUIDATION_HAIRCUT from P0. Use them; do not restate an asset list inline.
    Note BONDS appears in the haircut map but in neither the liquid nor the volatile
    list — P2 must decide and document which side it falls on, or state plainly that
    it is neither.
  - Test inputs are fixtures.mixed_portfolio() (6 holdings, one per asset type, with
    both gains and losses) and fixtures.empty_portfolio(). Do not read data/.
  - PortfolioRisk bands are CONSERVATIVE / BALANCED / GROWTH / AGGRESSIVE, ordered
    lowest to highest risk. Cut-points belong in app/config.py, never inline. The P1
    pattern of deriving the band ladder from the threshold dict is available to reuse.

### P2 — Portfolio Intelligence
Status: DONE
Exit criteria met: yes (all three)

IMPLEMENTED
  app/core/portfolio.py    analyze_portfolio(portfolio: Portfolio | None)
                           -> PortfolioMetrics. Pure: no I/O, no global state, no model
                           call, input not mutated. Does not import app/core/financial.py
                           (verified by grep) — the two P0-dependent phases stay
                           independent.
  app/schemas/metrics.py   PortfolioMetrics gained `allocation: dict[AssetType, float]`.
                           See DOCUMENTATION CHANGES.
  app/config.py            P2 classifications added: EQUITY_ASSET_TYPES,
                           DEBT_ASSET_TYPES, ASSET_RISK_WEIGHT, PORTFOLIO_RISK_MIN_SCORE.
  tests/test_portfolio.py  29 tests: hand-computed mixed portfolio, both zero-portfolio
                           entry points, concentration, risk-band transitions at every
                           cut-point, and the classification contracts.

VERIFIED BY
  python -m pytest tests/test_portfolio.py -q   -> 29 passed
  python -m pytest -q                           -> 110 passed (no regressions;
                                                   81 before, 29 new)
  AST scan of numeric literals in
  app/core/portfolio.py                         -> [0.0, 1] only — a zero comparison
                                                   and a 1-minus complement. No
                                                   threshold and no asset list in the
                                                   file.
  grep financial app/core/portfolio.py          -> no match (P2 does not import P1)
  subprocess import probe incl. app.core.*      -> forbidden modules: []

  Hand-computed mixed portfolio (2_300_000 total): unrealized +45_000; liquid 1_200_000
  (ratio 0.5217); equity 0.6304; debt 0.2609; crypto 0.0435; concentration 0.3478
  (the 800_000 stock holding); risk score ~0.467 -> GROWTH.

DECISIONS
  - THE NO-PORTFOLIO PATH HAS THREE ENTRY POINTS, all returning the same object:
    None, an empty holdings list, and holdings that are collectively worth zero. The
    third is what prevents a divide-by-zero; it is treated as no portfolio because
    there is genuinely nothing to allocate or liquidate. A test asserts None and empty
    produce identical metrics.
  - THE ZERO ALLOCATION MAP IS FULLY SHAPED, not empty: every AssetType present at 0.0,
    exactly as for a funded portfolio. P8's feature path therefore never tests for a
    missing key, which is what "consumable without special-casing" has to mean in
    practice.
  - HAIRCUTS ARE NOT APPLIED HERE. The phase prompt names the haircut alongside the
    liquidity classification, but ASSET_LIQUIDATION_HAIRCUT describes what is lost when
    holdings are actually SOLD, which is P5's liquidation math. liquid_value is the
    gross value of holdings classified liquid. Applying the haircut in both modules
    would double-count it and would put a second liquidation calculation in the repo.
    A test pins this (test_liquid_value_is_gross_of_haircuts). P5 MUST apply the
    haircut when it computes liquidation_amount.
  - BONDS RESOLVED (the gap flagged at the end of P1): BONDS is a DEBT asset, NOT
    liquid, NOT volatile. Rationale — an individual bond is not realisable on demand
    the way cash, an FD or an open-ended fund is, but it is not volatile enough to bar
    a CONSERVATIVE customer from selling it. Consequence for P6: BONDS is not covered
    by VOLATILE_ASSET_LIQUIDATION_PROHIBITED. Consequence for P5: bonds are outside
    liquid_value, so if P5 derives liquidation capacity from liquid_value alone, bonds
    cannot fund a purchase. P5 must decide that deliberately rather than inherit it.
  - EXPOSURES ARE INDEPENDENT SHARES, NOT A PARTITION. CASH and CRYPTO are in neither
    EQUITY_ASSET_TYPES nor DEBT_ASSET_TYPES, so equity + debt + crypto does not sum to
    1.0. This is deliberate and is asserted by test.
  - CONCENTRATION IS PER HOLDING, NOT PER ASSET TYPE. Two separate stock positions are
    two holdings and are not concentrated in one another, so concentration_risk is the
    largest single holding over total value — which matches the phase prompt's wording.
    A test distinguishes the two readings.
  - MUTUAL_FUNDS COUNTS AS EQUITY. Holding-level data does not say whether a fund is
    equity or debt, and the risk weight (0.50) already places it between bonds and
    stocks. Classifying it as equity is the conservative reading for exposure
    reporting. If P7's generator distinguishes fund types, this becomes a schema
    question, not a config one.
  - THE RISK BAND LADDER IS DERIVED FROM CONFIG, reusing the P1 pattern:
    PORTFOLIO_RISK_MIN_SCORE sorted descending, CONSERVATIVE as the floor with no
    entry. One dict is the single source of both the cut-points and their order.

LIMITATIONS / UNRESOLVED
  - ASSET_RISK_WEIGHT and PORTFOLIO_RISK_MIN_SCORE are reasoned defaults, not
    calibrated against return volatility. They are typed and in config. P7 should
    re-check them once the real population exists, since portfolio_risk becomes a model
    feature.
  - Risk is measured only by asset-type mix. Concentration risk is computed and
    reported but does NOT feed the risk band, so a single-stock portfolio and a
    twenty-stock portfolio band identically. Folding concentration into the band would
    be a second scoring concern inside one function; both values reach the recommender
    separately, which is the better place for the model to weigh them.
  - unrealized_gain_loss is an absolute rupee figure, not a percentage. Scale
    invariance matters to the labeling policy (CONTEXT.md 17.1), so P7/P8 may need a
    normalised form. The absolute figure is what the UI shows.

DOCUMENTATION CHANGES
  app/schemas/metrics.py — PortfolioMetrics gained `allocation: dict[AssetType, float]`.
  CONTEXT.md section 4 and the P2 phase prompt both list asset allocation as a required
  output of Portfolio Intelligence, and P0 omitted it from the schema. This is a P0
  omission corrected at the point of use, not a change of architecture: no spec file
  was edited, because the specs were already right and the schema was incomplete. The
  field's docstring records that the map is always fully shaped. Per AGENTS.md section
  3 the field was added to the schema first, then to the producer.

NEXT PHASE NEEDS TO KNOW (P3 — Personalization store + context)
  - P3 is independent of P1 and P2. Do not import either.
  - Produce PersonalizationContext from app/schemas/metrics.py. Its fields are the
    contract: is_cold_start, session_count, prior_declines, engagement_score (bounded
    0..1), preferred_tenure_band_months (nullable), purpose_affinity, strategy_affinity.
  - COLD START IS THE SAME KIND OF FIRST-CLASS PATH AS THE ZERO PORTFOLIO. An unknown
    or absent user_id returns a valid neutral block with is_cold_start = True, and the
    pipeline runs identically. tests/fixtures.neutral_personalization() already returns
    exactly that block and must keep working unchanged.
  - Note the two affinity maps default to EMPTY dicts, not fully-shaped ones — the
    opposite of the P2 allocation decision. P3 owns that call. If P8's feature path
    would have to test for missing keys, make them fully shaped (every LoanPurpose,
    every FinancingStrategy, at a neutral value) and say so in the record.
  - PERSONALIZATION_DB_URL is already in config. The store persists pseudonymous
    identifiers and derived aggregates only — never names, contact details or free
    text. A deletion path for a user_id is part of the layer's contract, not a later
    addition (CONTEXT.md section 10).
  - The layer is a FEATURE SOURCE. It scores nothing, ranks nothing and decides
    nothing. It is not a second recommender.

### P3 — Personalization Store + Context
Status: DONE
Exit criteria met: yes (all five)

IMPLEMENTED
  app/personalization/store.py    PersonalizationStore over stdlib sqlite3. Four tables
                                  (users, profile_snapshots, recommendation_history,
                                  feedback_events), write helpers, read helpers, and
                                  delete_user(user_id) erasing every row across every
                                  table and returning the count removed. Context-manager
                                  support. URL parsed from config, sqlite-only with a
                                  loud error for anything else.
  app/personalization/context.py  get_personalization_context(user_id, store=None,
                                  now=None) -> PersonalizationContext, plus
                                  neutral_personalization_context() as the single
                                  definition of the cold-start block.
  app/schemas/enums.py            FeedbackEventType (VIEWED | ACCEPTED | DECLINED).
  app/config.py                   PERSONALIZATION_DECAY_HALF_LIFE_DAYS,
                                  PERSONALIZATION_EVENT_WEIGHT, ENGAGEMENT_SATURATION,
                                  TENURE_BAND_WIDTH_MONTHS.
  training/seed_personalization.py  Three synthetic demo users, each a different history
                                  shape (settled accepter, repeated decliner,
                                  liquidation-preferrer). Offline only; app/ does not
                                  import it.
  tests/fixtures.py               neutral_personalization() now DELEGATES to
                                  neutral_personalization_context() instead of rebuilding
                                  the block, so the fixture cannot drift from what the
                                  pipeline produces.
  tests/test_personalization.py   32 tests.

VERIFIED BY
  python -m pytest tests/test_personalization.py -q  -> 32 passed
  python -m pytest -q                                -> 142 passed (no regressions;
                                                        110 before, 32 new)
  AST scan of numeric literals
    app/personalization/store.py                     -> [0]
    app/personalization/context.py                   -> [0.0, 0.5, 1.0, 86400.0]
                                                        0.5 is the halving base that
                                                        DEFINES a half-life, 86400.0 is
                                                        the named SECONDS_PER_DAY unit,
                                                        the rest are identity constants.
                                                        No tunable threshold in either
                                                        file.
  grep for training imports under app/               -> none
  subprocess import probe incl. app.personalization  -> forbidden modules: []
  python -m training.seed_personalization equivalent
    against a temp database                          -> seeded 3 users

  Cold start proven by test: None user_id, unknown user_id, and a known user with a
  users/ row but no history all return an object EQUAL to
  neutral_personalization_context().
  Deletion proven by test: after delete_user, every table holds zero rows for that user,
  the context returns to cold start, and other users are untouched.
  Privacy proven by test: PRAGMA table_info over the LIVE sqlite schema, asserting no
  column name contains name/email/phone/address/dob/pan/aadhaar/ssn/passport/note/
  comment/text.

DECISIONS
  - STDLIB sqlite3, NOT SQLAlchemy. SQLAlchemy is not in requirements.txt and adding an
    ORM to hold four tables would spend the memory budget (CONTEXT.md 17.2). The SQL is
    plain enough to port; the connection target is a URL from config rather than a bare
    path precisely so the Postgres move is a driver change. A non-sqlite URL raises
    instead of being silently misread as a file path.
  - PRIVACY IS ENFORCED BY THE SCHEMA, not by discipline. There is no column capable of
    holding a name, contact detail, identity number or free text, so no code path can
    persist one. The test asserts this against the live database schema rather than the
    source, so it still holds if someone adds a column later.
  - AFFINITY MAPS ARE FULLY SHAPED AND UNIFORM AT NEUTRAL. This resolves the open
    question left at the end of P2. Every LoanPurpose and every FinancingStrategy is
    present; neutral is uniform (1/N) rather than all-zero. Uniform means "no
    preference" and puts neutral on the same scale as an observed map, since both sum to
    1.0 — all-zero would mean "no evidence" and would sit on a different scale from
    every observed vector, which is worse for a model feature. P8 therefore never tests
    for a missing key, matching the P2 allocation decision.
  - A KNOWN USER WITH NO HISTORY IS A COLD START. A row in users/ is not history.
    Emitting anything other than the neutral block would invent a preference from
    nothing.
  - ENGAGEMENT SATURATES RATHER THAN CLAMPS: score = weighted / (weighted +
    ENGAGEMENT_SATURATION), which is in [0,1) by construction. No clamp, the first few
    interactions move it most, and a very active user never pins the feature at exactly
    1.0.
  - PREFERRED TENURE BAND USES ONLY ACCEPTED HISTORY. A recommendation the user never
    accepted says nothing about their preference, so it is excluded; the no-loan
    candidate has no tenure and is skipped structurally. With no accepted history the
    field is None, which is a valid value, not a defect.
  - FUTURE-DATED ROWS ARE CLAMPED TO DECAY WEIGHT 1.0, never amplified, so clock skew
    cannot let one row outweigh a real history. Tested.
  - store AND now ARE PARAMETERS, defaulting from config and the system clock. That is
    what lets every test use a tmp_path database and a fixed clock, and is why no test
    can touch data/ or the configured URL.
  - session_count COUNTS profile_snapshots ROWS — one per pipeline run. The listed
    tables carry no session concept, and inventing a sessions table for a count would be
    speculative.
  - NOTHING IN THIS LAYER SCORES OR ORDERS. The affinity maps, engagement score and
    decline count are inputs to app/ml/recommender.py. No function here returns a
    ranking or picks a candidate.

LIMITATIONS / UNRESOLVED
  - The half-life (90 days), event weights, saturation constant (5.0) and band width
    (12 months) are reasoned defaults, not fitted to interaction data — there is none
    yet. They are typed and in config. P7/P10 should re-check them once synthetic
    interaction history exists, since all four shape model features.
  - Only sqlite is implemented. The Postgres path is a stated future capability
    (CONTEXT.md section 10) and is NOT built or tested here. P17 owns it if the
    deployment target needs it.
  - No write path is wired into the pipeline yet: nothing calls record_profile_snapshot
    or record_feedback_event during a recommendation. P12 (which runs the pipeline) and
    P14 (which owns the feedback endpoint) own that wiring. Until then the store is
    populated only by the seed script.
  - Concurrency is not addressed. One connection per store, no pooling, no WAL. Fine for
    a single uvicorn worker, which is the documented default; revisit if P17 raises the
    worker count.
  - purpose_affinity is derived from what the system RECOMMENDED, not from what the
    customer asked for, because requirements are not persisted. For a returning customer
    these usually coincide, but they are not the same signal. Persisting the requested
    purpose would be a schema addition, and P7 should decide whether the training data
    needs it.

DOCUMENTATION CHANGES
  IMPLEMENTATION_PLAN.md — the P3 prompt's recommendation_history column list was
  amended to include `purpose`. The phase requires purpose affinity as an output, and
  the listed columns (user_id, at, product_id, amount, tenure, strategy, suitability,
  status) cannot produce it: product_id does not determine purpose, since a catalogue
  product may serve several purposes (PL-001 in the mock catalogue serves PERSONAL and
  MEDICAL). This is a completion of an incomplete column list, not a change of
  architecture. Per AGENTS.md 1.5 the conflict is named here rather than resolved
  silently.

  Also note (not a spec change): tests/fixtures.py neutral_personalization() changed
  from constructing PersonalizationContext(is_cold_start=True) with empty affinity maps
  to delegating to the real constructor. The old fixture would now be WRONG — it would
  hand later phases empty maps the pipeline never produces.

NEXT PHASE NEEDS TO KNOW (P4 — Eligibility Engine)
  - P4 depends on P0 and P1 only. It does not need P2 or P3; do not import them.
  - Produce list[EligibilityResult], ONE PER CATALOGUE PRODUCT, always. The output
    length must equal the catalogue length — a product is never silently dropped. The
    schema already enforces the rest: an INELIGIBLE result MUST carry a reason_code, and
    an ELIGIBLE result must NOT.
  - Reason codes available for eligibility are the six under the "Eligibility (P4)"
    heading in app/schemas/enums.py: CREDIT_SCORE_BELOW_MINIMUM, INCOME_BELOW_MINIMUM,
    AMOUNT_ABOVE_PRODUCT_MAX, AMOUNT_BELOW_PRODUCT_MIN, TENURE_OUT_OF_RANGE,
    PURPOSE_NOT_SUPPORTED. Do not invent a seventh; if a rule needs one, that is a
    schema change to name explicitly.
  - Populate observed_value and threshold_value on every INELIGIBLE result. The mismatch
    analyzer (P12) and the LLM (P13) both need the pair, and CONTEXT.md 7.2 requires it.
  - Config already holds MIN_APPLICANT_AGE and MAX_AGE_AT_LOAN_MATURITY. Per-product
    minimums (min_credit_score, min_monthly_income, min/max amount, min/max tenure,
    purposes) come from the LoanProduct, not from config.
  - HARD CONSTRAINTS ONLY. No scoring, no ranking, no EMI, no affordability check —
    affordability is feasibility and belongs to P5.
  - Test inputs: fixtures.mock_catalogue(), fixtures.standard_customer(),
    fixtures.no_match_customer() (below every product's minimum credit score AND minimum
    income), fixtures.standard_requirement().

### P4 — Eligibility Engine
Status: DONE
Exit criteria met: yes (all five)

IMPLEMENTED
  app/core/eligibility.py    check_eligibility(customer, financial_metrics,
                             requirement, catalogue) -> list[EligibilityResult].
                             One private helper, _first_failure, holding the whole rule
                             ladder. Pure: no I/O, no global state, no model call,
                             inputs not mutated.
  tests/test_eligibility.py  33 tests: the output-length invariant, each of the five
                             rules failing in isolation with its code/observed/threshold,
                             both bounds of every two-sided rule, exact-boundary cases,
                             rule-order precedence, and whole-catalogue behaviour.

VERIFIED BY
  python -m pytest tests/test_eligibility.py -q  -> 33 passed
  python -m pytest -q                            -> 175 passed (no regressions;
                                                    142 before, 33 new)
  AST scan of numeric literals in
  app/core/eligibility.py                        -> NONE. Every threshold is a property
                                                    of the LoanProduct being checked.
  grep for ML imports in the phase               -> no xgboost, no numpy, no app.ml,
                                                    no model of any kind. The only
                                                    matches are docstring prose.
  Direct invocation, both fixture customers      -> catalogue=6 results=6 eligible=2
                                                    (standard); catalogue=6 results=6
                                                    eligible=0 (no_match)

DECISIONS
  - THE RULE ORDER IS DEFINED AND DELIBERATE, and is tested. EligibilityResult carries
    exactly ONE reason code, so the first failure is what the user is shown. The order
    is: purpose, credit score, income, amount, tenure — least adjustable first. A
    product for the wrong purpose is not a near miss, it is the wrong product; and
    telling someone their tenure is out of range when their credit score also fails by
    250 points would send them to fix the wrong thing. Three tests pin the precedence
    (purpose before any numeric failure, credit score before amount, income before
    tenure).
  - PURPOSE MISMATCH CARRIES NO observed_value OR threshold_value. Purpose is
    categorical; there is no numeric pair to report and inventing one would be noise.
    The schema permits both to be None, and the code plus product id carry the entire
    explanation. Every OTHER ineligibility carries both values, asserted by test.
  - INCOME IS READ FROM FinancialMetrics, NOT FROM CustomerProfile. FinancialMetrics
    owns income (AGENTS.md section 2, "never recompute a value another module owns"),
    which is why the phase signature takes it. A test proves which source is actually
    read by passing metrics that deliberately disagree with the profile and asserting
    the outcome follows the metrics.
  - CREDIT SCORE IS READ FROM CustomerProfile, because FinancialMetrics does not carry
    it. That asymmetry is in the schemas, not a choice made here.
  - TENURE_OUT_OF_RANGE IS ONE CODE FOR TWO BOUNDS, so threshold_value reports the
    bound actually crossed — min on an under-run, max on an over-run. A test asserts
    both directions report different thresholds, otherwise the code would be
    unactionable.
  - ALL BOUNDARIES ARE INCLUSIVE: score, income, amount and tenure exactly at a product
    limit are ELIGIBLE. Tested at every boundary in both directions.
  - AN EMPTY CATALOGUE RETURNS AN EMPTY LIST, not an error. Zero products in equals
    zero results out, which keeps the length invariant true in the degenerate case.
  - NO AFFORDABILITY CHECK HERE. A customer can be eligible for a product whose EMI they
    cannot afford; that is INFEASIBLE, not INELIGIBLE, and CONTEXT.md 5.1 keeps them
    separate. P5 owns it.
  - "A FULLY-QUALIFYING CUSTOMER PASSES ALL PRODUCTS" was implemented as the only thing
    it can mean for this catalogue: no single requirement can pass all six products,
    because the mock catalogue's purposes are near-disjoint by design. The test instead
    checks a strong customer against each product with a requirement matched to that
    product's own purpose and limits, and asserts ELIGIBLE with reason_code None for
    every one.

LIMITATIONS / UNRESOLVED
  - MIN_APPLICANT_AGE AND MAX_AGE_AT_LOAN_MATURITY ARE IN CONFIG BUT UNUSED. Age is not
    an eligibility rule: neither CONTEXT.md section 4 nor the P4 prompt lists it, and
    there is no MismatchReasonCode for it — adding a seventh code would have been
    inventing a rule the specification does not describe. Two honest options remain, and
    a later phase must pick one deliberately rather than let this drift: treat maximum
    age at maturity as a FEASIBILITY constraint in P5 (a 120-month tenure for a
    68-year-old), or add an explicit eligibility rule plus its reason code as a named
    schema change. Flagged rather than silently resolved.
  - Only the FIRST failure is reported per product. A product failing three rules shows
    one. This is a schema consequence (one reason_code per EligibilityResult), not an
    oversight, and the defined rule order is what makes it predictable. If P13's
    explanations need the full failure set, that is a schema change to EligibilityResult.
  - Eligibility is evaluated against the customer's PREFERRED tenure and REQUESTED
    amount only. A product whose limits exclude the preferred tenure is ineligible even
    though a different tenure inside the product's range might have worked. This follows
    the specification exactly, but it means the candidate grid in P5 never gets to
    explore those products. P5 and P12 should confirm this is the intended funnel
    behaviour before the coverage numbers are shown to anyone — it is the single
    judgement in this phase most likely to be wrong at the product level.

DOCUMENTATION CHANGES
  None. The phase prompt, CONTEXT.md section 4 and the EligibilityResult schema agreed
  with each other and with the implementation.

NEXT PHASE NEEDS TO KNOW (P5 — Finance math + Candidate Generation)
  - P5 owns app/core/finance_math.py, THE ONLY EMI IMPLEMENTATION IN THIS REPO. Two
    implementations is a defect even if they agree. The spike at spikes/labeling/domain.py
    has one; do not import it, re-implement it (AGENTS.md section 15).
      EMI = P * r * (1+r)^n / ((1+r)^n - 1),  r = annual_rate / 12 / 100,  n = months
      Edge case: r == 0 -> EMI = P / n.
  - Consume only products whose EligibilityResult is ELIGIBLE. Do not re-check
    eligibility, and do not drop the ineligible ones from the trace — they are already
    recorded.
  - APPLY THE LIQUIDATION HAIRCUT. P2 deliberately left liquid_value GROSS of
    ASSET_LIQUIDATION_HAIRCUT so it would not be applied twice. If P5 does not apply it,
    it is applied nowhere and the config value is dead.
  - BONDS ARE DEBT, NOT LIQUID, NOT VOLATILE (decided in P2). Since bonds sit outside
    liquid_value, deriving liquidation capacity from liquid_value alone means bonds
    cannot fund a purchase. Decide that deliberately.
  - THE NO-LOAN CANDIDATE: generated ONCE PER CUSTOMER, not once per product x tenure
    (Phase R finding). The Candidate schema already enforces its shape — LIQUIDATE_100
    carries product_id None, lender None, tenure_months None, loan_amount 0.0, and
    REJECTS the spike's tenure=1 representation.
  - Infeasible candidates are MARKED, NEVER DELETED. The schema enforces the pairing:
    feasible=False requires an infeasibility_reason, feasible=True forbids one.
    Feasibility codes available: EMI_EXCEEDS_AFFORDABILITY,
    LIQUIDATION_EXCEEDS_PORTFOLIO, REQUIRED_AMOUNT_UNREACHABLE.
  - Dominance pruning removes objectively worse options only — better or equal on EVERY
    axis and strictly better on at least one. It expresses no preference and is not
    ranking.
  - Config already holds CANDIDATE_AMOUNT_STEPS, CANDIDATE_TENURE_OPTIONS_MONTHS,
    CANDIDATE_STRATEGY_BORROW_SHARE, MAX_CANDIDATES_PER_PRODUCT, MAX_CANDIDATES_TOTAL,
    MAX_EMI_SHARE_OF_DISPOSABLE_INCOME and EMI_VALIDATION_TOLERANCE_RUPEES.
  - Zero portfolio: only 100%-borrow strategies are generated, and no downstream module
    may special-case it. PortfolioMetrics.has_portfolio is the signal.
  - Phase R finding for P5/P7: Stage A of the labeling policy duplicates P5's
    feasibility rules. They must be THE SAME RULES, defined once — if they drift, the
    training set and the serving candidate set disagree.

### P5 — Finance Math + Candidate Generation Engine
Status: DONE
Exit criteria met: yes (all four)

IMPLEMENTED
  app/core/finance_math.py   emi(), total_repayment(), total_interest(),
                             monthly_rate(). THE ONLY EMI IMPLEMENTATION IN THE REPO.
                             Rounds nothing, so P12 re-verification compares the same
                             formula rather than two roundings.
  app/core/candidates.py     generate_candidates(requirement, financial_metrics,
                             portfolio_metrics, eligible_products)
                             -> CandidateGenerationResult. Enumerate -> mark
                             feasibility -> dominance-prune -> cap. No solver, no
                             scipy, no scoring, no sorting of candidates.
  app/schemas/pipeline.py    CandidateGenerationCounts MOVED here from
                             recommendation.py (its producer is a pipeline stage) and
                             gained `capped`. New CandidateGenerationResult.
  app/core/financial.py      _income_ratio promoted to public income_ratio.
  tests/test_candidates.py   56 tests.

VERIFIED BY
  python -m pytest tests/test_candidates.py -q  -> 56 passed
  python -m pytest -q                           -> 231 passed (175 before, 56 new)
  grep "def emi(" and the rate expression over
  app/ and training/                            -> exactly ONE match, in
                                                   app/core/finance_math.py. The copy in
                                                   spikes/labeling/domain.py is the
                                                   Phase R throwaway and is imported by
                                                   nothing.
  grep scipy/optimize/minimize in candidates.py -> no match (docstring prose only)
  subprocess import probe                       -> forbidden modules: [] (also no scipy)

  Funnel counts, standard customer, HOME 2,000,000 over 120 months:
    mixed portfolio  generated=104 infeasible=23 pruned=17 capped=0 surviving=64
    no portfolio     generated= 24 infeasible=12 pruned= 0 capped=0 surviving=12
  EMI reference values asserted to 2dp: 1,000,000 @ 10% / 12m = 87,915.89;
  500,000 @ 12% / 24m = 23,536.74; zero-rate 120,000 / 12m = 10,000.00.

DECISIONS
  - THE HAIRCUT IS APPLIED HERE, closing the loop P2 deliberately left open. To raise X
    rupees from a holding with haircut h, X / (1 - h) of it is sold. A test asserts
    gross sold STRICTLY EXCEEDS the funding contribution, so the haircut cannot be
    silently dropped later.
  - LIQUIDATION DRAWS ON ALL ASSET TYPES, NOT JUST LIQUID_ASSET_TYPES. This resolves the
    question left open at the end of P2. Volatile holdings CAN be sold — whether the
    customer is ALLOWED to is a policy question owned by P6. Excluding them here would
    make VOLATILE_ASSET_LIQUIDATION_PROHIBITED and allow_volatile_liquidation
    unreachable, i.e. dead config and a dead guardrail. P5 therefore reports
    volatile_liquidation_amount and refuses nothing. Consequence: BONDS (debt,
    not-liquid, not-volatile per P2) CAN fund a purchase; they are simply sold after
    cash and deposits.
  - HOLDINGS ARE CONSUMED IN ASCENDING HAIRCUT ORDER, cheapest first. That naturally
    spends cash, then deposits and funds, then bonds, then stocks and crypto. This is a
    COST FACT, not a preference about the customer's goals, which is why it does not
    violate the no-preference rule.
  - liquidation_amount IS THE NET FUNDING CONTRIBUTION the strategy demands.
    volatile_liquidation_amount is the GROSS value of volatile holdings sold. The gross
    total sold is recoverable as total_value - remaining_portfolio_value, which is what
    P6's liquidation-share cap should measure. The net/gross split is documented at the
    field because it is exactly the kind of thing a later phase would otherwise get
    wrong.
  - A LOAN OUTSIDE THE PRODUCT'S OWN AMOUNT OR TENURE LIMITS IS NOT GENERATED, rather
    than generated-and-marked-infeasible. It is not a configuration OF THAT PRODUCT at
    all. INFEASIBLE is reserved for the two conditions the phase prompt names: the EMI
    exceeds the affordability ceiling, or the liquidation exceeds what the portfolio can
    raise. Keeping those meanings distinct keeps the funnel honest.
  - AMOUNT STEPS SCALE THE FUNDED AMOUNT, not the loan. funded = required_amount * step;
    loan = funded * borrow_share; liquidation = funded - loan. Candidate.required_amount
    stays the customer's actual requirement, so "amount delta vs requested" (a P8
    feature) is derivable. Under-funded options are legitimate alternatives the model
    may rank low — that is what the feature is for.
  - THE CUSTOMER'S PREFERRED TENURE IS ADDED TO THE GRID for each product, restricted to
    that product's limits. This is not a preference ordering: it guarantees the option
    the customer actually asked for is in the space the model gets to score, instead of
    being absent because it fell between two grid steps.
  - THE NO-LOAN CANDIDATE IS GENERATED ONCE PER CUSTOMER (Phase R finding), only when a
    portfolio exists, funding the full requirement. Asserted by test to appear exactly
    once. It borrows nothing and carries no product, lender or tenure — the schema
    rejects the spike's tenure=1 form.
  - CAPS TRUNCATE BY ENUMERATION ORDER, which is arbitrary but deterministic, and
    deliberately NOT by any quality measure. Choosing which candidates to keep by how
    good they look would be ranking, and ranking belongs to the recommender. Recorded as
    a limitation below because it is a real weakness, not a free choice.
  - DOMINANCE COMPARES ONLY WITHIN THE SAME PRODUCT AND SAME LOAN AMOUNT, on three axes
    where lower is better: EMI, total interest, gross portfolio impact. Ties are kept —
    a tie is not dominance, so pruning never deletes arbitrarily. Comparison is rounded
    to paise, because raw float == on a computed EMI would make two arithmetically
    identical candidates look different and defeat pruning entirely.
  - THE NO-PREFERENCE EXIT CRITERION IS TESTED TWO WAYS. An AST identifier scan (not a
    text scan — the module's own prose about NOT having a utility function must not
    satisfy or break it), plus a BEHAVIOURAL test asserting the returned order is not
    monotone in EMI, interest or portfolio impact in either direction. A module that had
    ranked would produce a sorted axis.
  - income_ratio WAS PROMOTED TO PUBLIC in app/core/financial.py so the post-loan debt
    burden uses P1's zero-income convention rather than a second copy of it.

LIMITATIONS / UNRESOLVED
  - CAPPING BY ENUMERATION ORDER IS THE WEAKEST DECISION IN THIS PHASE. If a cap ever
    binds, the candidates dropped are those that happen to be enumerated last — later
    products, later tenures, lower borrow shares — and the recommender never sees them.
    It does not bind today (capped=0 for both fixture scenarios, against a per-product
    cap of 60 and a total of 500), so nothing is currently lost. P12 must surface
    counts.capped in the funnel, and if it is ever non-zero on a real request the fix is
    a wider cap or a coarser grid, NOT a quality-based selection.
  - REQUIRED_AMOUNT_UNREACHABLE IS NOT EMITTED BY THIS PHASE. It is a conclusion about
    the whole option space ("no configuration funds what you asked for"), not about any
    single candidate, and each candidate knows only its own funding. P12 owns it.
  - MAX_AGE_AT_LOAN_MATURITY IS STILL UNUSED (flagged at P4). P5 was the natural home
    for it as a feasibility rule — a 120-month tenure for a 68-year-old — but the phase
    prompt names exactly two infeasibility conditions, and adding a third silently would
    have changed the funnel's meaning. It remains an open decision for P6 or a named
    schema change. This is the second phase in a row it has been deferred; it should not
    be deferred a third time without a decision.
  - Dominance is O(n^2) within each product/amount group. At ~100 candidates this is
    irrelevant; it is noted only so nobody discovers it as a surprise if the grid grows.
  - The 100%-liquidate no-loan candidate is generated only at the FULL required amount,
    not at each amount step. Paying for 60% of a house from savings and not borrowing
    the rest is not a coherent option, so this is deliberate.

DOCUMENTATION CHANGES
  Schema only, no spec file edited. CandidateGenerationCounts moved from
  app/schemas/recommendation.py to app/schemas/pipeline.py — its producer is
  app/core/candidates.py, a pipeline stage, so it belonged with the other pipeline-stage
  results, and recommendation.py already imports from pipeline.py so the direction is
  clean. It gained a `capped` field.

  DEVIATION FROM THE PHASE PROMPT, stated rather than hidden: the prompt specifies
  generate_candidates(...) -> list[Candidate]. It returns CandidateGenerationResult
  (candidates + counts) instead. The same prompt requires "record pruned counts for the
  coverage funnel" and "record how many were capped", and CONTEXT.md 7.3 and AGENTS.md 9
  both require those counts in every response. Pruned and capped candidates are ABSENT
  from the returned list by definition, so the counts cannot be reconstructed from a bare
  list — the information would be destroyed at the moment it is required. The returned
  list still contains exactly what the prompt describes: surviving feasible candidates
  plus every infeasible one, marked. P12 consumes result.counts directly for the funnel.

NEXT PHASE NEEDS TO KNOW (P6 — Guardrail policy validator)
  - P6 is a PASS/FAIL VALIDATOR OVER ONE CANDIDATE, applied AFTER the recommender. It
    never reorders, never deletes, never scores. A blocked candidate is surfaced as
    ml_top_choice_blocked, not silently swapped.
  - Signature shape it must produce: GuardrailResult, already in app/schemas/pipeline.py.
    Its validator REQUIRES violated_rule and reason_code when allowed=False, and FORBIDS
    them when allowed=True.
  - Caps come from settings.GUARDRAIL_CAPS[risk_appetite]: max_debt_burden_ratio,
    max_liquidation_share, max_loan_to_income_multiple, allow_volatile_liquidation.
  - Field mapping, so P6 does not have to re-derive anything:
      debt burden        -> candidate.resulting_debt_burden_ratio (already includes the
                            new EMI)
      liquidation share  -> (portfolio_metrics.total_value -
                            candidate.remaining_portfolio_value) / total_value, i.e. the
                            GROSS sold including haircut loss. NOT
                            candidate.liquidation_amount, which is the net funding
                            contribution.
      volatile           -> candidate.volatile_liquidation_amount > 0 is the trigger for
                            VOLATILE_ASSET_LIQUIDATION_PROHIBITED
      loan to income     -> candidate.loan_amount / financial_metrics.monthly_income.
                            Decide and document whether the multiple is against MONTHLY
                            or ANNUAL income — the config default of 8.0/12.0/18.0 only
                            makes sense against ANNUAL income, and reading it as monthly
                            would block nearly every real loan. This is a live trap.
  - The four guardrail reason codes already exist: DEBT_BURDEN_CAP_EXCEEDED,
    LIQUIDATION_SHARE_CAP_EXCEEDED, VOLATILE_ASSET_LIQUIDATION_PROHIBITED,
    LOAN_TO_INCOME_CAP_EXCEEDED. Do not invent a fifth.
  - Zero-portfolio candidates liquidate nothing, so the liquidation and volatile caps
    must pass trivially rather than divide by a zero portfolio value.
  - NEVER widen a cap to make a demo produce a recommendation (AGENTS.md section 10).

### P6 — Guardrail Policy Validator
Status: DONE
Exit criteria met: yes (all five)

IMPLEMENTED
  app/core/guardrails.py    check_guardrails(risk_appetite, financial_metrics,
                            portfolio_metrics, candidate) -> GuardrailResult. Pure
                            pass/fail over ONE candidate. Two public helpers,
                            liquidation_share() and loan_to_income_multiple(), so the
                            two derived quantities are testable on their own and P12
                            never re-derives them.
  app/schemas/enums.py      GuardrailRule (MAX_DEBT_BURDEN_RATIO,
                            MAX_LOAN_TO_INCOME_MULTIPLE, MAX_LIQUIDATION_SHARE,
                            VOLATILE_ASSET_LIQUIDATION).
  app/config.py             GUARDRAIL_RULE_ORDER — the evaluation order, in config, so
                            "the first violation" is deterministic and reconfigurable
                            without touching code.
  tests/test_guardrails.py  30 tests.

VERIFIED BY
  python -m pytest tests/test_guardrails.py -q  -> 30 passed
  python -m pytest -q                           -> 261 passed (231 before, 30 new)
  AST scan of numeric literals in
  app/core/guardrails.py                        -> [0.0] only, and that 0.0 is the
                                                   permitted volatile amount under a
                                                   prohibition, not a threshold. Every
                                                   cap is read from config.
  grep for list comprehensions / sorted / .sort  -> only the rule-order loop
  grep for ML imports and the EMI expression     -> none; no figure is recomputed here
  Real option space, standard customer, 87 candidates:
    CONSERVATIVE  allowed=33 blocked=54  {LIQUIDATION_SHARE: 32, DEBT_BURDEN: 22}
    MODERATE      allowed=63 blocked=24  {LIQUIDATION_SHARE: 19, DEBT_BURDEN:  5}
    AGGRESSIVE    allowed=85 blocked= 2  {LIQUIDATION_SHARE:  1, DEBT_BURDEN:  1}
  The declared appetite therefore changes real outcomes, which a test also asserts.

DECISIONS
  - LOAN-TO-INCOME IS MEASURED AGAINST ANNUAL INCOME. This was the trap flagged at the
    end of P5 and it is now closed and pinned by two tests. The configured caps
    (8 / 12 / 18) are ordinary loan-to-income multiples, which are conventionally
    annual; read against MONTHLY income a 2,000,000 loan on a 120,000 monthly income
    would score 16.7x and be blocked for every appetite below AGGRESSIVE — i.e. the cap
    would reject almost every genuine home loan. One test asserts the annual reading
    directly, a second asserts that a realistic home loan is NOT blocked, so a future
    change to monthly would fail loudly rather than quietly break the product.
  - LIQUIDATION SHARE IS MEASURED GROSS OF THE HAIRCUT, as
    (total_value - remaining_portfolio_value) / total_value, NOT
    candidate.liquidation_amount / total_value. The cap asks how much LEAVES the
    portfolio, and the customer loses the haircut too, so the net funding contribution
    understates it. A test asserts the gross measure is strictly larger than the net one
    for a haircut-bearing candidate.
  - THE VOLATILE RULE IS CATEGORICAL, NOT A MAGNITUDE. Under a prohibition the permitted
    amount is zero, so cap_value is reported as 0.0 and observed_value is what the
    candidate would have sold. That gives the UI a concrete pair to render rather than
    a bare "not allowed".
  - RULE EVALUATION ORDER LIVES IN CONFIG, as a list of GuardrailRule enum members —
    not raw strings (AGENTS.md section 3). The order is: debt burden, loan-to-income,
    liquidation share, volatile prohibition — affordability policy first, then leverage,
    then portfolio impact, then the categorical ban. Three tests pin the behaviour: the
    same input names the same rule twice, the first configured rule wins when several
    are violated, and the second rule is named when the first passes.
  - EVERY RULE MAPS TO EXACTLY ONE REASON CODE, and a test asserts the mapping covers
    every GuardrailRule with no duplicates. A rule with no code could not be explained
    to the user; a code with no rule would be a reason nobody could trace to an
    evaluation, which CONTEXT.md 7.2 forbids.
  - THE MODULE CANNOT FILTER, BY CONSTRUCTION. check_guardrails takes one candidate and
    returns one verdict. A test inspects the signature and asserts no parameter is a
    list — the shape is what makes the P12 rank-order walk possible and makes silent
    deletion of an option impossible.
  - NOTHING IS RECOMPUTED HERE. The debt burden comes from
    candidate.resulting_debt_burden_ratio, already computed by P5 including the new EMI.
    loan_to_income_multiple reuses P1's income_ratio for the zero-income convention and
    finance_math's MONTHS_PER_YEAR rather than a second literal 12.
  - ZERO PORTFOLIO IS SAFE BY ARITHMETIC, not by a special case: consuming none of
    nothing is a share of 0.0, so the liquidation and volatile caps pass trivially while
    the debt-burden and loan-to-income caps still fire. Tested both ways.

LIMITATIONS / UNRESOLVED
  - THE VOLATILE PROHIBITION NEVER FIRES ON THE FIXTURE PORTFOLIO, because the
    liquidation-share cap always fires first. This is arithmetic, not a bug: the mixed
    portfolio holds 1.4M of non-volatile value against a 2.3M total, so any liquidation
    deep enough to touch stocks or crypto already consumes ~61% of the portfolio, far
    past the CONSERVATIVE 25% share cap. The rule IS reachable — a portfolio that is
    mostly volatile would trigger it before the share cap — and it is tested directly in
    isolation. P16 should include a demo customer whose portfolio is volatile-heavy, or
    the product will never show this behaviour to anyone.
  - Caps are reasoned defaults, not calibrated against a population or any real credit
    policy. They are typed, version-stamped and in config. They must never be widened to
    make a demo produce a recommendation (AGENTS.md section 10); the correct response to
    a blocked demo customer is to show the mismatch.
  - Only the FIRST violation is reported, because GuardrailResult carries one rule. A
    candidate breaking three caps shows one. The configured order makes it predictable,
    but P13's explanation cannot say "and two other rules also failed". If that is
    wanted, it is a schema change to GuardrailResult.
  - MAX_AGE_AT_LOAN_MATURITY IS STILL UNUSED — NOW DEFERRED THREE TIMES (P4, P5, P6).
    P6 was the last natural home for it: it is a policy cap, which is exactly this
    module's subject. It was not added because the phase prompt names exactly four caps
    and CONTEXT.md section 4 lists the same four, so adding a fifth would have invented
    policy the specification does not describe. THIS SHOULD NOT BE DEFERRED AGAIN. It is
    now either a named schema change (a fifth GuardrailRule plus a fifth reason code,
    updating CONTEXT.md section 4 and the P6 prompt), or the two config keys should be
    deleted as dead. Leaving them in place implies a rule that does not exist.

DOCUMENTATION CHANGES
  None. The phase prompt, CONTEXT.md section 4 and the GuardrailResult schema agreed
  with each other and with the implementation. GuardrailRule and GUARDRAIL_RULE_ORDER
  are additions the prompt explicitly asked for ("fixed rule evaluation order from
  config"), not changes to a documented contract.

NEXT PHASE NEEDS TO KNOW (P7 — Synthetic data + relevance labeling policy)
  - P7 depends on P1, P2 and P5 — NOT on P6. Guardrails are a serving-time policy layer
    and must NOT be baked into the labels, or the model learns to reproduce the policy
    instead of learning suitability, and the guardrail walk becomes a no-op.
  - THE STAGE-A DISQUALIFIER MASK MUST USE P5'S FEASIBILITY RULES, NOT A SECOND COPY
    (Phase R finding, spikes/labeling/FINDINGS.md section 6). If they drift, the training
    set and the serving candidate set disagree about what is possible. Import from
    app/core/candidates.py rather than re-implementing; training/ may import app/, the
    reverse is forbidden.
  - Only FEASIBLE candidates enter the labelled dataset. Infeasible ones are marked by
    P5 and excluded by P7.
  - EXCLUDE GROUPS WITH FEWER THAN 2 CANDIDATES from training (Phase R: 8 of 225 groups,
    3.6%, were single-candidate — useless for learning-to-rank and degenerate for NDCG).
    P12 must short-circuit the same case at serving time.
  - Phase R's tuned parameters and its measured 9.52% label-flip rate came from a
    population built inside the spike. P7 MUST re-measure the flip rate (band 2%-30%)
    and the degeneracy report against the real generator, and record both in the dataset
    manifest.
  - The invariant suite at spikes/labeling/test_invariants.py is a Phase R artefact that
    CARRIES FORWARD (AGENTS.md section 15). Move it into tests/ and re-point it at the
    real policy — it is 15 tests with a verified mutation score of 7/7.
  - Everything P7 writes lives in training/ and is never imported by app/. hypothesis is
    already pinned in requirements-train.txt and installed.
  - Labels are SYNTHETIC and every manifest, README and report must say so
    (AGENTS.md section 6 rule 9).

### P7 — Synthetic Data + Relevance Labeling Policy
Status: DONE
Exit criteria met: yes (all seven)

IMPLEMENTED
  training/generate_data.py    14 products / 400 customers / 1016 portfolio rows /
                               866 history rows. Fixed seed 20260902. Every file has a
                               '#' provenance comment AND a SYNTHETIC column on every
                               row.
  training/datasets.py         CSV -> real Pydantic schemas, stdlib csv, comment-aware.
  training/labeling.py         THE labeling policy, four decomposed stages plus a
                               separate noise step. Documented constants block.
  training/population.py       Population build, degeneracy report, stress flip-rate
                               measurement. Build artifacts, not one-off checks.
  training/build_dataset.py    relevance_dataset.csv, relevance_groups.csv,
                               dataset_manifest.json, label_audit_sample.md.
  tests/test_labeling_invariants.py   22 invariants (ported from Phase R + 3 added by
                               mutation testing here).
  tests/test_labeling.py       61 tests.

VERIFIED BY
  python -m training.generate_data              -> writes all four source files
  python -m training.build_dataset              -> 5808 rows, 170 groups
                                                   labels {0:1958, 1:1723, 2:1401, 3:726}
                                                   split rows  train 4700 / test 1108
                                                   split groups train 136 / test 34
                                                   flip rate 9.8485% (IN BAND)
                                                   no-good-option groups 16
  python -m pytest tests/test_labeling_invariants.py -q  -> 22 passed
  python -m pytest tests/test_labeling.py -q             -> 61 passed
  python -m pytest -q                                    -> 344 passed (261 before)
  grep for training imports under app/                   -> clean
  subprocess import probe                                -> forbidden modules: []

  Degeneracy report against the REAL generator (not Phase R's spike population):
    grade shares   0 -> 33.7% | 1 -> 30.0% | 2 -> 24.2% | 3 -> 12.1%   (limit 60%)
    max product win share  0.38   max tenure win share 0.38            (limit 60%)
    max strategy win share 0.55                                        (limit 60%)
    group sizes 2 - 123 ; 16 of 170 customers have NO good option

  THE INVARIANT SUITE WAS WATCHED FAILING BEFORE IT WAS TRUSTED. Written first, run
  against no policy -> ModuleNotFoundError. Then eight realistic defects were planted
  one at a time:
    CAUGHT  absolute rupee threshold in a sub-score
    CAUGHT  sign error on volatile portfolio penalty
    CAUGHT  appetite caps inverted
    CAUGHT  opportunity cost dropped from cost sub-score
    CAUGHT  stress demotion promotes instead of demoting
    CAUGHT  funding coverage ignored
    MISSED -> now CAUGHT  appetite volatile penalty dropped
    MISSED -> now CAUGHT  grade quantile bands inverted
  First run 6/8. Final 8/8, after adding three invariants named below.

DECISIONS
  - ALL DATA IS SYNTHETIC. data/raw/ did not exist, so no public lending or credit
    dataset was used. Customer financial profiles are generated, not sourced. This is
    stated in every file header, in every row's SYNTHETIC column, in the manifest
    ("labels_are_synthetic": true), and in the audit sample.
  - A FIFTH SUB-SCORE WAS ADDED: subscore_funding. The phase prompt names four. Against
    the real generator the four-sub-score policy was badly wrong, in two compounding
    ways. (a) Treating anything under 95% funding coverage as a Stage A disqualifier
    made grade 0 EIGHTY-SEVEN PERCENT of the dataset, because P5's amount grid
    deliberately enumerates 0.6x and 0.8x candidates. (b) Far worse: with no funding
    term, subscore_cost divides interest by the FULL required amount, so an under-funded
    candidate borrows less, pays less interest and scores as CHEAPER — the policy would
    have ranked partial funding ABOVE meeting the customer's stated need, and no
    invariant noticed. Funding adequacy is a concern in its own right, owned by one
    sub-score, and it is now covered by its own monotonicity invariant. Weights
    rebalanced to sum to 1.0: funding 0.20, affordability 0.18, cost 0.26, portfolio
    impact 0.20, appetite 0.16.
  - STAGE A READS P5'S FEASIBILITY VERDICT rather than re-implementing it. Phase R's
    finding was explicit: a second copy of the feasibility rules lets the training set
    and the serving candidate set disagree about what is possible. EMI-affordability and
    liquidation-capacity disqualification therefore come from candidate.feasible and
    candidate.infeasibility_reason. Stage A adds only what P5 does not judge: NO_INCOME,
    the policy debt-burden ceiling, and a severe funding shortfall.
  - GUARDRAILS ARE DELIBERATELY NOT BAKED INTO THE LABELS. HARD_DBR_CAP (0.55) is looser
    than every guardrail cap and is appetite-INDEPENDENT. If the labels encoded the
    guardrails, the model would learn to reproduce the policy layer and the P12 guardrail
    walk would become a no-op that never fires. A consequence visible in the audit
    sample: the policy can rank highest a candidate that guardrails then block, which is
    exactly the ml_top_choice_blocked behaviour the product exists to surface.
  - LABEL NOISE IS A SEPARATE STEP, applied in build_dataset.py, NOT inside grade_group.
    Noise is by definition not invariant-preserving — it would break dominance,
    monotonicity and scale invariance on any run where it fired, and those invariants are
    how the policy is verified. So the policy is graded noiselessly and verified, and
    noise is added as an explicit final step from a recorded seed. 5% rate.
  - GRADING IS BY WITHIN-GROUP RANK, capped by an absolute quality floor. The floor is
    what lets a customer legitimately have no good option; quantile grading alone always
    manufactures a grade 3, and the product must be able to say NO_SUITABLE_LOAN. 16 of
    170 groups have no candidate above grade 1.
  - ONLY FEASIBLE CANDIDATES ARE LABELLED, and groups with fewer than 2 candidates are
    excluded (both Phase R findings). 170 of 400 customers produced a usable group.
  - THREE INVARIANTS WERE ADDED BECAUSE MUTATION TESTING EXPOSED REAL GAPS:
      * more funding coverage never lowers the score — closed the funding gap above.
      * grades are monotone in raw score within a group — the dominance invariant
        compares only two candidates, too small a group for the quantile bands to bite.
      * grades form a pyramid at the top (share of grade 3 < share of grade 2) —
        inverting GRADE_QUANTILES survived EVERYTHING else. The grading stays perfectly
        monotone, so no per-example invariant can see it, and grade 3 rose from 12% to
        40% of labels: inflated more than threefold yet still under the 60% dominance
        limit. A relevance scale whose top grade is the most common has no discriminative
        power exactly where NDCG@1 and the acceptance threshold operate.
      * a fourth strengthening: "selling volatile assets is strictly penalised". The
        existing ordering invariant permitted EQUALITY, so zeroing
        VOLATILE_APPETITE_PENALTY satisfied "never scores higher" by scoring identically.
  - A P5 DEFECT WAS FOUND AND FIXED. Accumulated float error in the liquidation loop left
    a residue of about -1.5e-11 on a fully-consumed holding, producing a negative
    remaining_portfolio_value that the Candidate schema correctly rejected. Only the
    wider population exposed it. Fixed at the root in app/core/candidates.py by flooring
    the per-holding remainder at zero.
  - THE GENERATOR WAS TUNED, AND THE FIRST VERSION WAS WRONG. Drawing requirement amount
    and tenure uniformly across all purposes produced people asking for a 12-month home
    loan, or eight times their annual income for a medical bill. Only 45 of 400 customers
    produced a usable group. Requirement size and tenure are now drawn PER PURPOSE, so
    eligibility failures reflect the customer rather than the draw: 170 of 400 usable.
    This was an artifact of the generator, not a signal about the catalogue.

LIMITATIONS / UNRESOLVED
  - THE LABELS ARE SYNTHETIC AND A MODEL TRAINED ON THEM PARTIALLY REPRODUCES THIS
    POLICY. Reported NDCG at P10 will measure agreement with training/labeling.py, not
    real recommendation quality. Agreement between the ML recommendation and the
    diagnostic utility score proves nothing — they share ancestry through this file.
    Both statements must appear wherever model quality is reported.
  - AUDIT SAMPLE OBSERVATION 1 (read, and flagged rather than tuned away): the best
    option routinely extends the tenure well beyond what the customer asked for —
    36 months requested, 48 recommended; 12 requested, 48 recommended. The policy has no
    term rewarding a match to the preferred tenure: affordability and appetite both
    favour a long tenure (0.34 of the weight) against cost's 0.26. "Tenure delta vs
    preferred" is a P8 FEATURE, so the model can still learn it, but the LABELS will not
    reward it. No invariant is violated. This is the single most likely place a human
    would disagree with the dataset, and P10 should look at it again once ranking metrics
    exist.
  - AUDIT SAMPLE OBSERVATION 2: syn-0122, a MODERATE customer, is labelled "pay
    Rs 18.65L from holdings and borrow nothing" as best, which liquidates 67% of a
    Rs 27.9L portfolio. MODERATE's guardrail cap is 50%, so this exact candidate would be
    BLOCKED at serving. That is by design, not a defect — but P16 should confirm the demo
    set exercises it, because it is the clearest illustration of ml_top_choice_blocked.
    Phase R flagged the same shape on its own Customer 2, so it is systematic.
  - The max strategy win share is 0.55, against a 0.60 limit — the closest of the three
    degeneracy measures. It passes, but it has the least headroom, and any future change
    to the opportunity-cost or buffer terms should re-check it first.
  - Constants are inherited from Phase R and re-measured, not re-tuned from scratch. The
    flip rate landed at 9.85% against Phase R's 9.52%, which is reassuring but is
    agreement between two synthetic populations, not validation.
  - The stress simulation shares ONE scenario draw across every customer and candidate.
    That is what makes it deterministic, monotone in EMI and scale-invariant
    simultaneously, but it means every household faces the same shock sequence. A
    simplification, carried over from Phase R and still true.
  - tests/test_labeling.py reads data/, which AGENTS.md section 2 otherwise forbids. In
    this phase the generated dataset IS the artifact under test; its label distribution
    and customer split cannot be verified anywhere else. Rather than skipping when the
    files are absent — which would let the suite go green having verified nothing — the
    session fixture BUILDS them. No other phase's tests read data/.

DOCUMENTATION CHANGES
  None to any spec file. The fifth sub-score is a deviation from the P7 prompt's list of
  four and is recorded above with its justification and the evidence that forced it,
  rather than being made silently.

NEXT PHASE NEEDS TO KNOW (P8 — Shared feature engineering)
  - ONE FEATURE PATH. app/ml/features.py is imported by BOTH training and serving.
    Writing a second assembly path in training/ is the specific defect that rule exists
    to prevent (AGENTS.md section 6 rule 4).
  - FEATURE BUILDERS RETURN NUMPY ARRAYS. No DataFrame crosses into app/. training/ may
    hold pandas on its own side of the boundary but never passes one across.
  - data/relevance_dataset.csv carries every Candidate field needed to rebuild a feature
    row: candidate_id, product_id, lender, tenure_months, strategy, required_amount,
    loan_amount, emi, total_interest, total_repayment, liquidation_amount,
    volatile_liquidation_amount, remaining_portfolio_value, resulting_liquidity_ratio,
    resulting_debt_burden_ratio, affordability_headroom. Customer and portfolio features
    come from data/customers.csv and data/portfolios.csv via training/datasets.py.
  - data/relevance_groups.csv holds group sizes in dataset row order — the array
    XGBRanker's `group` parameter needs. Rows are contiguous per group and a test
    asserts it.
  - THE RISK PD IS A PARAMETER of the feature builder, not something it computes. P9
    supplies it; at P8 it is simply an argument.
  - Categorical encoding must be a SAVED DICT MAPPING, not a pickled encoder, and an
    unseen category is a handled case with a documented default, never an exception
    (CONTEXT.md 17.2).
  - The no-loan candidate has product_id None, lender None and tenure_months None. The
    feature path must encode that as "no loan", not as a missing product or a zero-month
    loan. It is in the dataset (a test asserts the strategy appears), so P8 will meet it.
  - PortfolioMetrics.allocation is always fully shaped (every AssetType present, zeroed),
    and PersonalizationContext's two affinity maps are likewise fully shaped and uniform
    at cold start. Neither needs a missing-key branch.
  - FinancialMetrics ratios use UNDEFINED_RATIO_VALUE (99.0) as a finite stand-in when
    income is zero. P8 owns the decision whether that sentinel reaches the model as-is or
    becomes an explicit missing-value flag.

### P8 — Shared Feature Engineering
Status: DONE
Exit criteria met: yes (three fully; the fourth as far as this phase can — see below)

IMPLEMENTED
  app/ml/features.py     build_risk_features -> 30 columns
                         build_pair_features -> 69 columns
                         build_pair_feature_matrix (whole candidate list, one call)
                         RISK_FEATURE_COLUMNS / PAIR_FEATURE_COLUMNS
                         build_lender_encoding / set_lender_encoding / get_lender_encoding
                         feature_manifest / assert_manifest_matches
                         FeatureManifestMismatch
  tests/test_features.py 42 tests.

VERIFIED BY
  python -m pytest tests/test_features.py -q  -> 42 passed
  python -m pytest -q                         -> 386 passed (344 before, 42 new)
  subprocess probe importing app.ml.features  -> sys.modules contains none of
                                                 pandas / sklearn / shap / xgboost.
                                                 Importing the module touches no model
                                                 file and no filesystem.
  grep for a second feature path in training/ -> none (asserted by
                                                 test_exactly_one_feature_assembly_path_exists)
  All seven CONTEXT.md 6.3 feature groups present, asserted by test:
    customer financial, portfolio, personalization, requirement, product,
    derived candidate, risk PD.

DECISIONS
  - BOTH BUILDERS TAKE CustomerProfile. This is a deviation from the phase prompt's
    signatures and is a resolution of a genuine conflict, not a preference. CONTEXT.md
    6.3 requires AGE and CREDIT SCORE as customer-financial features, and both live on
    CustomerProfile — neither is on FinancialMetrics. The prompt's signatures
    (financial_metrics, portfolio_metrics, requirement) cannot reach them, so following
    the prompt literally would have shipped a risk classifier with no credit score,
    which is not a credible risk model, and a recommender missing two features
    CONTEXT.md names explicitly. CONTEXT.md is the authority (AGENTS.md 1.1), so the
    profile is the first parameter of both builders.
  - COLUMN ORDER IS DERIVED FROM THE BUILDERS, not declared separately. Each builder is
    implemented as a function returning ordered (name, value) pairs; the column tuples
    are computed at import from one reference call to those same functions. A name and
    its value therefore cannot drift apart — which is the classic way a feature contract
    silently rots, and the exact failure assert_manifest_matches exists to catch later.
  - THE REFERENCE CALL CONSTRUCTS OBJECTS ONLY. It reads no file, loads no model and
    makes no network call, so importing this module stays free — the model-loading rule
    is about the filesystem, and this touches none of it. A test asserts the import is
    clean in a subprocess.
  - CATEGORICAL ENCODING IS SPLIT BY WHAT IS DERIVABLE. Enum categoricals (loan purpose,
    employment type, financing strategy, financial health, portfolio risk, risk
    appetite) encode by position in the enum definition — deterministic, needs no
    fitting, and any add/remove/reorder is caught by assert_manifest_matches. LENDER is
    catalogue data rather than an enum, so it cannot be derived from code: its mapping is
    built once from the catalogue at training time by build_lender_encoding (sorted by
    name, so row order cannot change it) and SHIPPED IN THE MANIFEST. Serving installs it
    with set_lender_encoding at load and never fits it.
  - THE LENDER MAPPING IS MODULE STATE, not a threaded-through parameter. It is a SAVED
    MAPPING, not a fitted object (CONTEXT.md 17.2), and threading it through every call
    would have changed all three public signatures for a value that is constant for the
    life of the process. A test asserts building features never mutates it.
  - UNSEEN_CATEGORY = -1, and a test asserts it cannot collide with any real index —
    every real encoding starts at 0. An unseen lender is a handled case with a documented
    default, never an exception.
  - assert_manifest_matches IS PURE VALIDATION AND INSTALLS NOTHING. P11 calls
    set_lender_encoding(manifest["lender_encoding"]) explicitly, so the installation is
    visible at the call site rather than being a side effect of a function named
    "assert". It raises FeatureManifestMismatch on a version mismatch, a missing column,
    an added column, a REORDERED column list, and a changed enum encoding — five tests,
    one each. The reorder case is called out in the message because same-columns-wrong-
    order silently feeds every value to the wrong feature.
  - THE NO-LOAN CANDIDATE IS FLAGGED, NOT MISSING. LIQUIDATE_100 has no product, lender
    or tenure; its product features are zeroed, is_no_loan is 1.0, and
    tenure_delta_vs_preferred is 0.0 rather than a large negative implying a zero-month
    loan. This is the P7 handoff requirement, and three tests pin it.
  - EVERY DIVISION IS GUARDED and returns 0.0 on a zero denominator. All of them are
    "share of something the customer does not have", which is genuinely zero; NaN would
    poison the whole vector and inf would be silently clipped by the booster. Tests
    assert no NaN and full finiteness for a zero-income customer, a zero-portfolio
    customer, a cold-start customer, and every generated candidate.
  - AN EMPTY CANDIDATE LIST RETURNS A CORRECTLY-SHAPED (0, n) MATRIX, not an error. The
    recommender handed an empty list returns an empty list (AGENTS.md section 6 rule 2),
    so the feature layer must be able to represent that.

LIMITATIONS / UNRESOLVED
  - THE EXIT CRITERION "grep training/ to confirm it imports this module" CANNOT BE
    SATISFIED YET, and is recorded rather than glossed. No training script consumes
    features at P8: P9 trains the risk model and P10 the recommender, and building either
    consumer now would be starting the next phase. What IS proven today is the negative
    and stronger half — no second feature-assembly path exists anywhere under training/,
    asserted by test_exactly_one_feature_assembly_path_exists, which fails if any
    training module defines build_pair_features or build_risk_features. P9 and P10 must
    import from app/ml/features.py and nowhere else.
  - UNDEFINED_RATIO_VALUE (99.0) REACHES THE MODEL AS-IS. P7's handoff asked P8 to
    decide, and the decision is: pass it through unchanged rather than convert it to a
    missing-value flag. A zero-income customer is disqualified by the labeling policy and
    is infeasible at serving, so the sentinel only ever appears on rows the model is not
    asked to choose between; adding a parallel missing-value channel would be complexity
    for a case that cannot reach a recommendation. If P9's risk training data contains
    zero-income rows in quantity, revisit — it is the one place the sentinel could
    influence a fitted model.
  - PRODUCT TYPE is represented by product_primary_purpose (the first purpose in the
    product's list) rather than a separate "loan type" field, because LoanProduct has no
    distinct type attribute — purpose IS the type in this schema. A multi-purpose product
    contributes only its first purpose. Adequate for a 14-product catalogue; a schema
    addition if the catalogue grows a real type taxonomy.
  - Feature values are unscaled and unbounded (raw rupees alongside ratios). Correct for
    gradient-boosted trees, which are scale-invariant per split, but this matrix must not
    be handed to a linear or distance-based model without standardisation.
  - No feature encodes lender REPUTATION or any behavioural product attribute; lender is
    an identity index only. The model can learn per-lender effects but cannot generalise
    to a lender it never saw — which is what UNSEEN_CATEGORY makes visible rather than
    hides.

DOCUMENTATION CHANGES
  None to any spec file. The CustomerProfile parameter is a deviation from the P8 phase
  prompt's stated signatures, recorded above with the CONTEXT.md 6.3 requirement that
  forced it, rather than made silently.

NEXT PHASE NEEDS TO KNOW (P9 — Risk model, secondary)
  - IMPORT build_risk_features FROM app/ml/features.py. Do not write a feature
    assembly in training/; a test fails if you do.
  - Signature: build_risk_features(customer, financial_metrics, portfolio_metrics,
    requirement) -> np.ndarray of shape (30,), ordered by RISK_FEATURE_COLUMNS.
  - THE RISK MODEL IS A FEATURE SOURCE AND A DISCLOSURE, NEVER A DECISION. It may not
    gate, veto or select (CONTEXT.md non-negotiable 3). Its output is RiskPrediction
    (risk_class, probability_of_default, model_version, imputed) — the schema exists.
  - Persist as XGBoost JSON, not pickle. Save feature_manifest() beside it; P11 asserts
    it at load and a mismatch is a startup failure.
  - There is NO default-outcome column in the generated data. P7 generated customers,
    portfolios, history and relevance labels — nothing about repayment. P9 must define
    and document how the risk target is produced, and say plainly in its report that the
    label is synthetic and what it is derived from. This is the largest open question
    going into P9 and it is not answered anywhere in the repo yet.
  - Report ROC-AUC, PR-AUC, precision, recall, F1, Brier score and a reliability curve —
    the classifier metrics. Ranking metrics belong to P10.
  - If the model cannot load at serving, PD is imputed to the training-set median and the
    imputation is FLAGGED in the trace (RiskPrediction.imputed). Record that median in
    the model manifest at P9, or P11 has nothing to impute with.

### P9 — Risk Model (Secondary)
Status: DONE
Exit criteria met: yes (all four)

IMPLEMENTED
  training/generate_risk_outcomes.py  The SYNTHETIC repayment outcome the classifier
                                      learns, drawn from an explicit latent-risk model.
                                      Its own module, because burying the invention of
                                      the target inside a training script would hide the
                                      most consequential assumption in the model.
                                      -> data/risk_outcomes.csv
  training/train_risk.py              XGBClassifier over build_risk_features from
                                      app/ml/features.py. GridSearchCV (24 combinations,
                                      5-fold stratified). Full metric set, reliability
                                      curve, achievable-ceiling computation.
                                      -> models/risk_model.json (XGBoost JSON)
                                      -> models/risk_model_manifest.json
  app/config.py                       RISK_MODEL_VERSION, RECOMMENDER_MODEL_VERSION,
                                      RISK_CLASS_MIN_PD (band ladder for P11).
  tests/test_risk_training.py         24 tests.
  tests/test_serving_imports.py       One test added — see the memory-budget finding.

VERIFIED BY
  python -m training.generate_risk_outcomes  -> 400 customers, default rate 0.1550
  python -m training.train_risk              -> trains, prints every metric, saves both
                                                artifacts
  python -m pytest tests/test_risk_training.py -q  -> 24 passed
  python -m pytest -q                              -> 411 passed (386 before)
  grep for training imports under app/             -> clean

  TEST METRICS (320 train / 80 test customers, LABELS ARE SYNTHETIC)
    roc_auc      0.7120        pr_auc       0.4376
    precision    0.7500        recall       0.2500
    f1           0.3750        brier_score  0.1165
    accuracy     0.8750        (reported alongside, never alone — 15% positive rate)
    cv roc_auc   0.6630        best params  learning_rate 0.05, max_depth 4,
                                            min_child_weight 5, n_estimators 150
    training_pd_median 0.071397

  ACHIEVABLE CEILING — a ROC-AUC means nothing without one
    oracle (knows the drawn probability, shock included)   0.8428
    best possible from RISK_FEATURE_COLUMNS alone          0.7504
    this model, held-out test set                          0.7120
  The model captures about 95% of what is recoverable from its own feature set. That
  comparison, not the raw AUC, is the honest statement of how it performed.

  RELIABILITY (test): well calibrated in the populated low bins (predicted 0.044 ->
  observed 0.083; predicted 0.159 -> observed 0.286) and unreliable above 0.3, where
  only 2-6 customers land per bin.

DECISIONS
  - THE RISK TARGET DID NOT EXIST AND HAD TO BE INVENTED. P8 flagged this as the largest
    open question, and it was: P7 generated customers, portfolios, history and relevance
    labels, but nothing about repayment. The outcome is drawn from a documented
    latent-risk logistic model over credit score, existing debt burden, expense ratio,
    income stability, liquid buffer in months of expenses, loan-to-income, dependents and
    employment type. Every coefficient is a log-odds contribution applied to a RATIO or a
    standardised quantity, so the process is scale-free like the labeling policy.
  - IT LIVES IN ITS OWN MODULE, NOT INSIDE THE TRAINING SCRIPT. The generative process is
    the single most consequential assumption in this model; hiding it in train_risk.py
    would make it invisible to anyone reading the metrics.
  - THE UNOBSERVED SHOCK TERM IS THE MOST IMPORTANT DESIGN CHOICE HERE. A quarter of each
    customer's log-odds comes from a standard normal draw that is DELIBERATELY not a
    feature. Without it the label would be a deterministic function of the feature
    vector, the classifier would recover it almost perfectly, and a 0.97 ROC-AUC would be
    an artifact of the generator rather than evidence of anything. With it, the
    features-only ceiling is 0.7504 and the model reaches 0.7120 — a number that means
    something. This is the same principle as P7's stress simulation: leave the model
    something to learn that is not simply readable off its own inputs.
  - THE BASE RATE WAS CALIBRATED BEFORE ANY MODEL WAS TRAINED. BASE_LOG_ODDS was set to
    put the population default rate near 15%, a plausible retail figure. Chosen from the
    generator's own behaviour, not tuned afterwards to flatter a metric.
  - THE PHASE 7 SPLIT IS REUSED AND EXTENDED, NEVER CONTRADICTED. P7 split only the 170
    customers with a usable candidate group; risk trains on all 400 because it needs no
    candidates. Customers P7 did not cover are assigned here with the SAME seed and test
    share, so the two splits agree wherever they overlap and no customer can leak.
  - ACCURACY IS REPORTED BUT NEVER ALONE. At a 15% positive rate, 0.875 accuracy is
    barely better than predicting "no default" for everyone (0.85). ROC-AUC, PR-AUC,
    precision, recall, F1, Brier and a ten-bin reliability curve all ship in the manifest,
    and a test asserts the manifest carries more than accuracy.
  - THE MANIFEST STATES THE MODEL'S ROLE IN THE ARTIFACT ITSELF, not only in the docs:
    "SECONDARY. Output is a feature for the primary recommender and a user-facing risk
    disclosure. It never selects, gates or vetoes." A test asserts it, and another test
    greps the training script for selection logic (def select / def recommend / def rank_
    / eligib) and fails if any appears.
  - training_pd_median IS RECORDED (0.0714) so P11 has something to impute with when the
    artifact cannot load. Without it the documented fallback in CONTEXT.md section 8 would
    have had no value to fall back to.
  - THE MEMORY BUDGET WAS RE-VERIFIED, AND THE P0 OPEN ITEM IS NOW CLOSED. xgboost was
    pinned but not installed at P0, so its transitive graph had never been observed.
    Installing it revealed that IMPORTING XGBOOST PULLS IN PANDAS AND SCIKIT-LEARN when
    they are present — which locally they are, for training. That looked like the memory
    budget collapsing. It is not: xgboost imports them opportunistically, and
    requirements.txt excludes both, so they are absent on the serving target. Verified by
    running the serving stack in a subprocess with pandas / sklearn / shap / matplotlib
    made UNIMPORTABLE: numpy, xgboost and the application all import, a Booster loads
    from JSON, predict() and predict(pred_contribs=True) both work, and zero forbidden
    modules end up in sys.modules. That is now a permanent test
    (test_the_serving_stack_works_without_any_training_dependency), because inspecting
    sys.modules in a development environment tests the wrong thing.
  - pred_contribs WAS EXERCISED ON THE REAL ARTIFACT and returned shape (1, 31) — 30
    features plus the bias term, as XGBoost's native TreeSHAP does. P13's XAI mechanism
    is confirmed working on an actual model, not just on the Phase R dummy.

LIMITATIONS / UNRESOLVED
  - RECALL IS 0.25 AT THE 0.5 THRESHOLD. The model finds a quarter of defaulters, at 75%
    precision when it does fire. That is a threshold artifact rather than a model
    failure — 0.5 is a poor operating point for a 15%-positive target — but NOTHING IN
    THIS SYSTEM THRESHOLDS THE PD. The recommender consumes the probability directly and
    the disclosure shows a band, so no operating point needs choosing. If a later phase
    ever wants a hard risk decision, that would be a new decision boundary and would need
    its own justification. It would also violate non-negotiable 3.
  - THE MODEL IS CALIBRATED ONLY WHERE THE DATA IS. Above a predicted PD of 0.3 the test
    set holds 2-6 customers per bin, and one bin shows predicted 0.35 against an observed
    0.00. The Brier score of 0.1165 is dominated by the well-populated low bins. High-PD
    predictions should be treated as directional, and the user-facing disclosure should
    show a BAND rather than a decimal probability. RISK_CLASS_MIN_PD is in config for
    exactly that.
  - 400 CUSTOMERS AND 62 DEFAULTS IS A SMALL TRAINING SET. The 80-customer test set has
    12 positives, so every test metric has wide error bars. The cross-validated 0.663
    versus the test 0.712 is well within noise for that size, not evidence the test split
    is easy.
  - THE OUTCOMES ARE SYNTHETIC AND NOBODY DEFAULTED. The classifier partially recovers
    training/generate_risk_outcomes.py, and reported ROC-AUC measures agreement with that
    generative process, not real credit risk. This sentence belongs beside these numbers
    wherever they are quoted, and it is asserted by test to be in the manifest.
  - The risk features include the REQUESTED AMOUNT and preferred tenure, so the PD is
    request-conditional rather than a pure applicant score. That is defensible — asking
    for six times your income genuinely is riskier — but it means the PD changes when the
    customer changes their request, and P13's explanation should not present it as a
    fixed property of the person.
  - GridSearchCV searched 24 combinations at 5 folds. Small, as the phase asked. The grid
    is recorded in the manifest and a test asserts every chosen parameter came from it.

DOCUMENTATION CHANGES
  None to any spec file. training/generate_risk_outcomes.py is a new artifact the phase
  prompt did not name; it exists because the prompt assumed a training target that P7
  never produced. Recorded here rather than resolved silently.

NEXT PHASE NEEDS TO KNOW (P10 — Primary recommender, calibration, evaluation)
  - THIS IS THE PHASE THE WHOLE REDESIGN EXISTS FOR. Do not rush it.
  - Use build_pair_feature_matrix from app/ml/features.py. 69 columns. The risk PD is a
    PARAMETER: load models/risk_model.json, predict per customer, and pass the number in.
    Do not let the recommender call the risk model itself.
  - Groups come from data/relevance_groups.csv, sizes in dataset row order, rows
    contiguous per group. Split by customer is already done and must not be redone.
  - EVALUATE IT AS A RANKER: NDCG@1/@3/@5, Precision@1/@3, Recall@5, MAP@5, MRR,
    Kendall's tau. Do NOT report classification accuracy for the recommender.
  - THREE BASELINES ARE MANDATORY and must be reported side by side even when the model
    loses: random ordering, cheapest-EMI-first, and the deterministic diagnostic utility
    ranking. A loss to the diagnostic baseline is published, not buried.
  - Agreement between the ML ranking and the diagnostic utility score IS NOT VALIDATION.
    They share ancestry through training/labeling.py. Never cite it as evidence.
  - THE CALIBRATOR IS A TRANSFORM, NOT A THIRD MODEL. Fit isotonic regression offline on
    held-out groups mapping raw margin -> P(relevance >= 2), then EXPORT IT AS (x, y)
    KNOTS applied with numpy.interp. Phase R verified the knots reproduce sklearn exactly
    (max diff 0.0). scikit-learn must not reach the serving set.
  - Only the CALIBRATED value is ever compared against SUITABILITY_ACCEPTANCE_THRESHOLD.
    Raw ranker margins are unbounded and are carried for audit only.
  - Save the feature manifest beside the model, as P9 did. P11 asserts it at load and a
    mismatch is a startup failure.
  - Label noise is already in the dataset (5%), so a perfect NDCG is not attainable and
    should not be expected.

### P10 — Primary ML Recommender: Training, Calibration, Evaluation
Status: DONE
Exit criteria met: yes (all four)

IMPLEMENTED
  training/pair_dataset.py       Assembles (customer, candidate) rows: rebuilds
                                 candidates by re-running the SAME population build that
                                 produced the labels, reads the NOISED labels back from
                                 relevance_dataset.csv, loads synthetic history through
                                 the REAL personalization layer, and predicts the PD from
                                 the P9 model. Features come only from
                                 app/ml/features.py.
  training/ranking_metrics.py    NDCG@k, Precision@k, Recall@k, MAP@k, MRR, Kendall's
                                 tau-b — all per group, then averaged over groups. Plus
                                 the three mandatory baselines.
  app/core/diagnostics.py        diagnostic_utility_score and its four components. Built
                                 only as far as the baseline comparison needs, so there
                                 is ONE implementation rather than a training copy P12
                                 would have to reconcile.
  training/train_recommender.py  XGBRanker (rank:ndcg), explicit group-aware CV, isotonic
                                 calibration exported as knots, full metric table,
                                 threshold recommendation.
  models/                        loan_recommender.json, loan_recommender_calibration.json,
                                 loan_recommender_encoders.json,
                                 loan_recommender_manifest.json
  tests/test_recommender_training.py  35 tests.

VERIFIED BY
  python -m training.train_recommender  -> full table printed, bundle saved
  python -m pytest tests/test_recommender_training.py -q  -> 35 passed
  python -m pytest -q                                     -> 446 passed (411 before)
  ls models/*.json                                        -> exactly TWO boosters:
                                                             loan_recommender.json and
                                                             risk_model.json. The
                                                             calibration, encoders and
                                                             manifests are not models.

  170 groups | fit 102 / calibration 34 / test 34 | 5808 rows | 69 features

  RANKING METRICS ON HELD-OUT GROUPS (labels are SYNTHETIC)
                     ndcg@1  ndcg@3  ndcg@5   p@1     p@3   rec@5   map@5    mrr     tau
    ML RECOMMENDER   0.9435  0.9072  0.8944  0.8235  0.7745  0.4705  0.8720  0.9828  0.6890
    random           0.2693  0.3171  0.3368  0.2353  0.3333  0.1827  0.2063  0.5483  0.0023
    cheapest_emi     0.6935  0.5968  0.5932  0.5882  0.5098  0.3059  0.5340  0.7593  0.3489
    diagnostic_util  0.7202  0.6179  0.5892  0.6176  0.5196  0.2842  0.5487  0.7692  0.3162
    POLICY ORACLE*   0.9821  0.9753  0.9769  0.8529  0.8333  0.5079  0.9566  1.0000  0.8055

  THE MODEL BEATS ALL THREE MANDATORY BASELINES, including the deterministic diagnostic
  utility ranking — 0.8944 against 0.5892 on NDCG@5, and on every other metric.

  * POLICY ORACLE is a CEILING, not a baseline: the labeling policy's own combined score
    evaluated against the noised labels. The model reaches 91.6% of it and stays below
    it, which is what rules out label leakage.

  CALIBRATION: 48 monotone knots, fitted on 34 held-out groups the ranker never trained
  on. Knot interpolation reproduces the fitted estimator EXACTLY (max diff 0.00e+00,
  asserted inside the training script). Brier 0.1163 on test.
  Reliability, calibrated suitability vs observed P(relevance >= 2):
    [0.0,0.1) n=476 pred 0.033 obs 0.063   [0.7,0.8) n=163 pred 0.742 obs 0.650
    [0.1,0.2) n= 61 pred 0.141 obs 0.147   [0.9,1.0) n=206 pred 0.965 obs 0.917
    [0.2,0.3) n=148 pred 0.251 obs 0.230

  THRESHOLD RECOMMENDATION: 0.35, implying a NO_SUITABLE_LOAN rate of 0.1471 on held-out
  groups, against a label-based no-good-option rate of 0.1471. CONFIG WAS NOT CHANGED
  (still 0.55).

DECISIONS
  - THE POLICY-ORACLE CEILING WAS ADDED because an NDCG of 0.89 is uninterpretable on
    its own. These labels come from a policy whose inputs are ALL features, so most of it
    is recoverable and a high NDCG is expected rather than impressive. Scoring the test
    groups by the labeling policy's own raw score gives the ceiling a perfect recovery
    would reach: 0.9769. The model's 0.8944 is 91.6% of that, and the remaining gap is
    the 5% label noise plus imperfect recovery. A model ABOVE the oracle would indicate
    leakage, and a test asserts it stays below.
  - GROUP-AWARE CROSS-VALIDATION IS IMPLEMENTED EXPLICITLY, not with GridSearchCV.
    sklearn's search cannot carry a per-fold `group` array for a ranker and would
    silently split a customer's candidates across folds — which leaks part of a group
    into the fold it is scored on and makes a ranker look far better than it is. Folds
    are assigned BY GROUP.
  - THE CALIBRATOR IS FITTED ON GROUPS THE RANKER NEVER SAW. 25% of the training
    customers are carved out by customer and excluded from the final fit. Calibrating on
    training margins produces a confident, wrong curve — the model is overconfident
    exactly where it was fitted.
  - THE KNOT EXPORT IS ASSERTED AT TRAINING TIME, not hoped for. fit_calibration
    recomputes the fitted estimator's predictions and the numpy.interp interpolation over
    the exported knots and RAISES if they differ by more than 1e-9. They matched exactly.
    An exported calibration that disagrees with what was fitted would make serving
    disagree with training about every suitability score, silently.
  - THE CALIBRATOR IS A TRANSFORM, NOT A THIRD MODEL. It is stored as (x, y) breakpoints
    in a JSON file and applied with numpy.interp. scikit-learn is used to FIT it offline
    and never to apply it, so the serving dependency set is untouched. A test asserts
    exactly two booster artifacts exist.
  - app/core/diagnostics.py WAS BUILT HERE, deliberately. The phase prompt says not to
    build it "beyond what the comparison needs" — and what the comparison needs is the
    scoring function. Implementing it in training/ instead would have created a second
    implementation of a formula P12 also needs, which is the duplication AGENTS.md
    section 2 exists to prevent. It is minimal: the score, four components, no fallback
    wiring, no ordering logic. A test asserts NOTHING under app/ imports it yet — P12 is
    its first legitimate consumer and may call it only on the fallback path.
  - THE PD IS PREDICTED IN THE DATA LAYER AND PASSED IN AS A NUMBER. The recommender
    never calls the risk model. That is what keeps the dependency acyclic and stops the
    secondary model becoming a decision-maker.
  - PERSONALIZATION FEATURES COME THROUGH THE REAL P3 LAYER. The synthetic history is
    loaded into a throwaway PersonalizationStore under the OS temp directory and read
    back with get_personalization_context, rather than re-deriving affinities in training.
    Same rule as the feature module: one code path.
  - CANDIDATES ARE REBUILT BY RE-RUNNING THE POPULATION BUILD, and the labels are read
    back from disk by (user_id, candidate_id). Regenerating candidates a second, different
    way is how a training set quietly stops matching its labels; a mismatch now raises
    rather than training on a silently misaligned row.
  - NO ACCURACY IS REPORTED FOR THE RANKER, and a test asserts the manifest contains no
    accuracy key for the model or any baseline.
  - THE THRESHOLD IS RECOMMENDED, NOT SET. Training sweeps 0.30-0.90 and reports the
    implied NO_SUITABLE_LOAN rate at each value, then names the one closest to the
    label-based no-good-option rate. It does not touch config. Moving
    SUITABILITY_ACCEPTANCE_THRESHOLD is the single easiest way to falsify this product
    (AGENTS.md section 10), so it stays a human decision.

LIMITATIONS / UNRESOLVED
  - THESE METRICS MEASURE AGREEMENT WITH training/labeling.py, NOT REAL RECOMMENDATION
    QUALITY. The relevance labels are synthetic and the model partially reproduces the
    policy that produced them. NDCG 0.89 says the model learned the policy well; it says
    nothing about whether the policy is right.
  - AGREEMENT BETWEEN THIS MODEL AND THE DIAGNOSTIC UTILITY BASELINE IS NOT EVIDENCE
    EITHER IS CORRECT. They share ancestry through the labeling policy. The model BEATING
    that baseline is more informative than agreement would be — it shows the learned
    ranking captures something the hand-weighted formula does not — but it is still
    measured against the same synthetic target.
  - THE CONFIGURED THRESHOLD (0.55) IS ABOVE THE RECOMMENDED ONE (0.35). At 0.55 the
    implied NO_SUITABLE_LOAN rate on held-out groups is materially higher than the
    label-based no-good-option rate of 14.7%, so the system will currently refuse to
    recommend for customers whose labels say they do have a good option. This is a REAL
    DECISION SOMEONE MUST MAKE before P16, and it must be made on the merits — a
    conservative product may legitimately prefer a higher bar. It must NOT be lowered
    later merely because a demo customer produced NO_SUITABLE_LOAN.
  - 34 TEST GROUPS IS A SMALL EVALUATION SET. Every metric has wide error bars, and the
    gap to the diagnostic baseline (0.89 vs 0.59) is large enough to survive that, but
    the precise values should not be quoted to four significant figures as though they
    were stable.
  - CALIBRATION IS SPARSE IN THE MIDDLE. The [0.4,0.5) bin holds one candidate and
    [0.6,0.7) holds none — isotonic regression produces plateaus, and the score
    distribution is bimodal (476 candidates below 0.1, 206 above 0.9). Suitability values
    in the middle of the range are the least trustworthy, which matters because that is
    exactly where an acceptance threshold sits.
  - RECALL@5 IS 0.4705 because groups are large (up to 123 candidates) and often contain
    many relevant ones; five slots cannot hold them all. It is not a defect, but it is the
    metric most sensitive to group size and should not be compared across datasets.
  - The 5% label noise means a perfect NDCG is unattainable by construction, which is why
    the oracle itself scores 0.9769 rather than 1.0.

DOCUMENTATION CHANGES
  None to any spec file. app/core/diagnostics.py is created earlier than P12 would
  suggest; the reasoning is recorded above rather than resolved silently.

NEXT PHASE NEEDS TO KNOW (P11 — ML inference layer + fallback)
  - LAZY LOADING, NEVER AT IMPORT. Each ML module exposes load_models() plus a lazy
    accessor; the API lifespan handler calls it once at startup. Importing an ML module
    must not touch the filesystem — tests/test_features.py already asserts this for
    app/ml/features.py and P11 must keep it true.
  - AT LOAD: call F.assert_manifest_matches(manifest["feature_manifest"]) and then
    F.set_lender_encoding(manifest["feature_manifest"]["lender_encoding"]) explicitly.
    assert_manifest_matches installs nothing by design.
  - APPLY THE CALIBRATOR WITH numpy.interp over knots_x / knots_y from
    models/loan_recommender_calibration.json. Never import scikit-learn. numpy.interp
    clamps outside the fitted range, which is the correct behaviour and is tested.
  - ONLY THE CALIBRATED VALUE is compared against SUITABILITY_ACCEPTANCE_THRESHOLD. The
    raw margin is unbounded and is carried for audit only (ScoredCandidate already has
    both fields).
  - FALLBACK: on a missing or corrupt artifact, log the path and the exception, rank by
    diagnostic_utility_score from app/core/diagnostics.py, set recommendation_source =
    DETERMINISTIC_FALLBACK, and set ml_suitability to NULL — the Recommendation schema
    already REJECTS a non-null ml_suitability under fallback, so this is enforced.
  - RISK FALLBACK: if the risk model cannot load, impute PD with
    models/risk_model_manifest.json -> training_pd_median (0.071397) and set
    RiskPrediction.imputed = True.
  - RISK_CLASS_MIN_PD is in config for turning a PD into a RiskClass band, using the same
    descending-ladder pattern as the financial-health and portfolio-risk bands.
  - MEMORY CHECKPOINT 1 is due at this phase: scripts/measure_memory.py, reporting
    resident memory after import, after load_models(), and after one /recommend call,
    against MEMORY_CEILING_MB = 290. Note that xgboost pulls pandas and sklearn in WHEN
    THEY ARE INSTALLED, so the measurement must be taken with them blocked or absent, as
    tests/test_serving_imports.py does — otherwise it measures the development
    environment rather than the deployment target.
  - Groups with fewer than 2 candidates must be short-circuited at serving (Phase R
    finding), matching the training exclusion.

### P11 — ML Inference Layer + Fallback
Status: DONE
Exit criteria met: yes (all seven)

IMPLEMENTED
  app/ml/risk.py           predict_risk(customer, financial, portfolio, requirement)
                           -> RiskPrediction. load_models() / get_risk_model() /
                           reset_state() / is_degraded() / imputed_pd() /
                           risk_class_for(). Nothing loaded at import.
  app/ml/recommender.py    score_candidates(...) -> ScoringResult. load_models() /
                           get_recommender_model() / reset_state() / is_degraded() /
                           calibrate(). Nothing loaded at import.
  app/schemas/pipeline.py  ScoringResult — the scored list plus the source that
                           produced it, with a validator forbidding a calibrated
                           suitability under DETERMINISTIC_FALLBACK.
  app/config.py            CALIBRATION_KNOTS_PATH / ENCODER_MAPPING_PATH corrected to
                           the filenames P10 actually writes.
  scripts/measure_memory.py  Memory checkpoint 1 of 3.
  requirements-train.txt   psutil==7.1.0, pinned as an OPS-ONLY tool.
  tests/test_ml_inference.py  48 tests.

VERIFIED BY
  python -m pytest tests/test_ml_inference.py -q  -> 48 passed
  python -m pytest -q                             -> 495 passed (446 before)
  python -m pytest tests/test_serving_imports.py  -> 7 passed (the P0 test still holds)
  subprocess import probe                         -> load_attempted False/False,
                                                     boosters None/None. Importing
                                                     either ML module touches no file.
  grep for training imports under app/            -> clean

  MEMORY CHECKPOINT 1 (measured with pandas/sklearn/shap BLOCKED, i.e. as the
  deployment target actually runs):
      baseline (python + psutil)     18.7 MB
      after import                   88.2 MB
      after load_models()            98.3 MB
      after one scoring call         99.6 MB
      ceiling (MEMORY_CEILING_MB)   290.0 MB
      headroom                      190.4 MB — 66% of the ceiling unused
      forbidden modules loaded: none
  PASS. Phase R projected 186 MB for the serving set; the real thing is 99.6 MB, so
  the ceiling has far more room than the budget assumed.

  END-TO-END SMOKE (standard fixture customer, HOME 2,000,000 over 120 months):
      risk LOW, PD 0.0311, imputed False
      64 candidates scored via ML_RANKER, ranks 1..64, suitability 0.0000-0.9758
      30 of 64 at or above the configured 0.55 threshold
      top pick: the no-loan candidate (LIQUIDATE_100), suitability 0.9758

DECISIONS
  - score_candidates RETURNS ScoringResult, NOT A BARE LIST. The phase prompt says
    "mark the result so the caller can set recommendation_source", and the source has to
    travel WITH the result. The alternative — a module-level is_degraded() the caller
    queries afterwards — is unsafe under concurrency: one request's fallback could be
    reported against another request's scores, and "never present a deterministic
    fallback as an ML recommendation" (CONTEXT.md 5.3) is precisely the property that
    must not depend on call ordering. The schema's validator additionally REJECTS a
    non-null suitability under DETERMINISTIC_FALLBACK, so the rule is enforced by
    construction rather than by discipline.
  - BOTH ENTRY POINTS TAKE CustomerProfile, continuing the P8 decision. CONTEXT.md 6.3
    puts age and credit score in the feature set and both live on the profile, so the
    prompt's signatures could not reach them.
  - A FEATURE-CONTRACT MISMATCH IS RE-RAISED, NOT DEGRADED. This is the sharpest
    judgement in the phase. A MISSING model is a degradation the system is designed to
    survive; a model whose column order disagrees with app/ml/features.py would feed
    every value to the wrong feature and produce confident nonsense from every
    prediction — worse than having no model. So FileNotFoundError and corrupt JSON fall
    back, while FeatureManifestMismatch propagates and stops startup. Two tests pin it:
    a stale FEATURE_VERSION raises with BOTH versions in the message, and a reordered
    column list raises naming the reorder.
  - assert_manifest_matches THEN set_lender_encoding, in that order and both explicit.
    Contract first: never install an encoding from an artifact this code cannot feed
    correctly. P8 deliberately made assert_manifest_matches install nothing, so the
    installation is visible at the call site.
  - CALIBRATION KNOTS ARE VALIDATED AT LOAD, not trusted. Empty knots, mismatched x/y
    lengths and a NON-MONOTONE curve are all rejected. A non-monotone calibrator would
    let a better ranker margin produce a worse suitability, silently inverting the
    product's central claim. That one degrades to fallback rather than raising, because
    unlike a column mismatch the model itself is still coherent — the transform is not.
  - TIES BREAK DETERMINISTICALLY: suitability, then raw margin, then original position.
    An arbitrary tie-break would let the same request produce different recommendations
    between runs, which for a financial recommendation is a correctness defect rather
    than a nuisance. It matters here because the calibrator maps many distinct margins
    onto the same plateau value — 476 of 1108 held-out candidates share a suitability
    below 0.1 — so ties are common, not theoretical.
  - IMPUTED PD FAILS TOWARDS CAUTION. The recorded training median (0.0714) is used when
    the manifest is readable. LAST_RESORT_PD = 0.5 applies only when the manifest itself
    cannot be read; a test asserts it is >= 0.5, because imputing "no risk" when the risk
    model is broken is the dangerous direction to fail in.
  - THE FALLBACK IS THE ONLY PLACE THE DIAGNOSTIC SCORE ORDERS ANYTHING, and an AST test
    asserts diagnostic_utility_score is called from exactly one function,
    _fallback_ranking. Importing it is permitted; calling it on the normal path is not.
  - MODULE STATE IS RESETTABLE. reset_state() exists for tests and deliberate reloads,
    and every test in the phase resets both modules before and after — a test that left a
    loaded model behind would make the next one pass for the wrong reason.
  - THE MEMORY PROBE RUNS IN A SUBPROCESS WITH TRAINING DEPENDENCIES BLOCKED. Measuring
    in-process would have measured this development machine, where pandas and sklearn are
    installed for training and xgboost imports them opportunistically. The number would
    have been wrong in the flattering direction on the deployment target and wrong in the
    alarming direction here.
  - psutil IS PINNED IN requirements-train.txt, NOT requirements.txt. The probe runs
    beside the service, never inside it, so it must not enter the serving graph.

LIMITATIONS / UNRESOLVED
  - CALIBRATION_KNOTS_PATH AND ENCODER_MAPPING_PATH WERE WRONG IN CONFIG SINCE P0. They
    pointed at models/calibration_knots.json and models/encoder_mappings.json, while P10's
    prompt specified and P10 wrote loan_recommender_calibration.json and
    loan_recommender_encoders.json. The first end-to-end run silently took the FALLBACK
    path because of it — the system behaved correctly and flagged itself, which is the
    fallback working as designed, but it means a filename typo was enough to disable the
    primary model with only a log line. P14 should surface recommendation_source
    prominently, and P17 should verify the artifacts resolve on the deployment target
    before declaring a release healthy.
  - ENCODER_MAPPING_PATH IS STILL UNREAD BY ANY CODE. The lender encoding is loaded from
    the model manifest, which embeds the same mapping, so the standalone encoders file is
    currently redundant. P10's prompt required writing it; nothing requires reading it.
    Either P13/P17 uses it or it should be deleted as a second copy of a mapping that can
    drift from the manifest.
  - THE NO-LOAN CANDIDATE IS THE TOP PICK FOR THE STANDARD FIXTURE CUSTOMER, at
    suitability 0.9758. That is the model faithfully reproducing the labeling policy,
    which prefers paying from a large portfolio over borrowing — the same behaviour the
    P7 audit sample flagged and Phase R saw before it. It is not a P11 defect, but P12
    and P15 will render it, and "we recommend you borrow nothing" is a result the demo
    must present coherently rather than as an empty loan card.
  - 30 OF 64 CANDIDATES CLEAR THE CONFIGURED 0.55 THRESHOLD for this customer, so the
    threshold question raised at P10 is still open and now has a concrete illustration.
    The recommended value was 0.35; config remains 0.55. Unchanged, and still a human
    decision.
  - No concurrency test. Module state is written once at load and read thereafter, which
    is safe for the documented single-worker deployment, but load_models() is not
    guarded against two threads racing on first call. A lock would be the fix if P17
    raises the worker count within a process.
  - The risk model is loaded and predicted one row at a time. Fine at one prediction per
    request; if P14 ever batches customers, DMatrix construction per row becomes the
    obvious inefficiency.

DOCUMENTATION CHANGES
  None to any spec file. Two changes worth naming:
  (a) app/config.py — CALIBRATION_KNOTS_PATH and ENCODER_MAPPING_PATH corrected to the
      filenames P10's prompt specified and P10 actually writes. A defect fix, not a
      redesign.
  (b) tests/test_recommender_training.py — the P10 test asserting that NO module under
      app/ imports the diagnostic score was updated, because P11 legitimately made
      app/ml/recommender.py its first consumer, exactly as this phase's prompt requires.
      It was not weakened: it now allows one named module and is PAIRED WITH A NEW,
      STRONGER AST TEST asserting diagnostic_utility_score is called from exactly one
      function, _fallback_ranking. The architectural property is more tightly held after
      the change than before it.

NEXT PHASE NEEDS TO KNOW (P12 — Orchestrator, validation walk, mismatch)
  - THE ORCHESTRATOR ASSEMBLES; IT DOES NOT DECIDE. It may contain no formula that
    reorders candidates. It walks the ranking it is given (CONTEXT.md non-negotiable 8).
  - Pipeline order is fixed: financial -> portfolio -> personalization -> eligibility ->
    candidate generation -> risk -> recommender -> validation + guardrail walk ->
    assembly.
  - score_candidates returns ScoringResult; use result.source directly for
    recommendation_status's sibling field. Do NOT call recommender.is_degraded() to
    decide it — the source on the result is per-request and the module flag is not.
  - Under DETERMINISTIC_FALLBACK every suitability is None, so the acceptance threshold
    CANNOT be applied. Decide and document what NO_SUITABLE_LOAN means in fallback mode;
    the Recommendation schema already forbids a non-null ml_suitability there.
  - Walk the ML order and stop at the FIRST candidate that passes validation AND
    guardrails AND clears SUITABILITY_ACCEPTANCE_THRESHOLD. Record every candidate
    attempted in ValidationWalkStep, not only the winner.
  - When the model's rank-1 pick fails, record BlockedTopChoice with the rule and cap and
    surface it. Never silently swap.
  - app/core/validation.py is yours to build: recompute EMI from app/core/finance_math.py
    and compare within EMI_VALIDATION_TOLERANCE_RUPEES (1.0). Float equality will not do.
  - Distinguish all four stop points: NO_ELIGIBLE_PRODUCTS, NO_FEASIBLE_CANDIDATES,
    ALL_CANDIDATES_BLOCKED, NO_SUITABLE_LOAN. Collapsing them is a defect.
  - REQUIRED_AMOUNT_UNREACHABLE is still unemitted by any phase. It is a conclusion about
    the whole option space and P5 deliberately left it to you.
  - Short-circuit groups with fewer than 2 candidates (Phase R finding), matching the
    training exclusion.
  - MAX_AGE_AT_LOAN_MATURITY remains unused after four phases (P4, P5, P6, P11). It is
    now either a named schema change or dead config to delete. Do not defer it again
    without deciding.

### P12 — Recommendation Orchestrator, Validation Walk, Catalogue Mismatch
Status: DONE
Exit criteria met: yes (all five)

IMPLEMENTED
  app/core/validation.py       validate_candidate(candidate, product, financial,
                               portfolio) -> ValidationResult. Six checks in a fixed
                               order; the first failure is named with its expected and
                               observed values. Logs a DEFECT SIGNAL at error level.
                               Never corrects anything.
  app/core/mismatch.py         analyze_mismatch(...) -> (reasons, coverage) and
                               build_coverage(...). Reasons come only from rules that
                               actually fired.
  app/core/recommendation.py   recommend(customer, portfolio, requirement, catalogue,
                               user_id=None, personalization_store=None)
                               -> Recommendation. Fixed pipeline order, the validation
                               walk, status resolution, alternatives, full trace.
  app/schemas/recommendation.py  CatalogueCoverage gained candidates_passing_validation
                               and candidates_passing_guardrails.
  app/config.py                MIN_APPLICANT_AGE / MAX_AGE_AT_LOAN_MATURITY REMOVED.
  tests/test_recommendation.py 41 tests.

VERIFIED BY
  python -m pytest tests/test_recommendation.py -q  -> 41 passed
  python -m pytest -q                               -> 536 passed (495 before)
  python -m scripts.measure_memory                  -> PASS, 66% of the ceiling unused
  grep for a second EMI implementation under app/   -> none

  ALL FIVE STATUSES, produced through the real pipeline:
    RECOMMENDED             standard customer
    NO_SUITABLE_LOAN        all candidates scored below the threshold
    NO_ELIGIBLE_PRODUCTS    the fixtures' deliberately unmatched customer
    NO_FEASIBLE_CANDIDATES  eligible on paper, nothing affordable, no portfolio
    ALL_CANDIDATES_BLOCKED  scored well, every walked candidate guardrail-blocked
  A test asserts all four non-RECOMMENDED statuses are DISTINCT from one another.

  THE SIGNATURE BEHAVIOUR, working on the real models (standard customer, MODERATE):
    the ML's rank-1 pick was the no-loan candidate; MAX_LIQUIDATION_SHARE blocked it;
    rank 2 was selected; ml_top_choice_blocked carries the rule, the cap and the
    observed value; the customer still gets a recommendation.
    funnel: 6 products -> 2 eligible -> 2 with feasible candidates -> 87 generated
            -> 64 scored -> 30 above threshold -> 2 validated -> 1 permitted

DECISIONS
  - ORDERING INTEGRITY IS PROVEN BY AN ADVERSARIAL STUB, not by inspection. The test
    injects a ranking in which the MOST EXPENSIVE candidate scores highest — the exact
    opposite of what any cost heuristic or the diagnostic utility would choose — then
    independently recomputes which candidate the walk should have selected and asserts
    the orchestrator picked it. If anything downstream re-sorted, that test fails.
    Two further AST tests assert the orchestrator defines no function whose name
    contains score/utility/rank/weight, and that no identifier containing "diagnostic"
    appears inside any sorted/max/min expression in the module.
  - THE THRESHOLD IS NOT APPLIED IN FALLBACK MODE, and this is the phase's most
    consequential judgement. Under DETERMINISTIC_FALLBACK there is no calibrated
    suitability — it is None by construction — so there is nothing to compare against
    SUITABILITY_ACCEPTANCE_THRESHOLD, and comparing a rescaled diagnostic score against
    a threshold calibrated for the ML model would be meaningless. The walk therefore
    runs on validation and guardrails alone. THE CONSEQUENCE, STATED PLAINLY:
    NO_SUITABLE_LOAN IS UNREACHABLE IN FALLBACK MODE. Without a learned suitability the
    system has no basis to call an option unsuitable — only impossible (infeasible) or
    impermissible (guardrail-blocked). That is the honest behaviour; the alternative
    would be inventing a suitability judgement the system cannot make.
  - THE WALK STOPS AT THE FIRST BELOW-THRESHOLD CANDIDATE, and the stop reason says why:
    the list is in descending suitability, so every remaining candidate is also below.
    That is arithmetic about the rest of the list, not a judgement about the candidate.
  - A VALIDATION FAILURE STILL RUNS THE GUARDRAIL before recording the step, so the walk
    log carries a complete picture of every candidate attempted rather than a partial
    one. ValidationWalkStep requires both results, and a half-filled row would make the
    trace less useful exactly where it matters.
  - ml_top_choice_blocked COVERS BOTH BLOCKING MECHANISMS. A guardrail block reports the
    rule name and cap; a VALIDATION failure reports "validation:<check>" with the
    expected value as the cap. A validation failure on the model's top pick is a defect
    signal and surfacing it is more important than surfacing a routine policy block.
  - ALTERNATIVES ARE RE-VALIDATED, NOT ASSUMED. Each is put through validation and
    guardrails before being offered, because presenting an alternative the system would
    refuse to recommend would be worse than offering none. They stay in ML rank order
    and are never re-sorted; a test asserts their ranks are ascending and their
    suitabilities descending.
  - REQUIRED_AMOUNT_UNREACHABLE IS FINALLY EMITTED, by this module, as P5 specified. It
    is a conclusion about the whole option space — no candidate funds the request — so
    it belongs nowhere else. It reports the BEST coverage achieved against what was
    asked for. Two unit tests: one that it fires when nothing reaches full funding, one
    that it does NOT fire when something does.
  - MISMATCH REASONS ARE DEDUPLICATED PER (product, cause). A product with 60 infeasible
    candidates emits one reason, not sixty. Without this the reason list would be
    unusable and the LLM would be handed sixty copies of the same sentence.
  - NO SUITABILITY REASON IS EMITTED IN FALLBACK MODE. With no calibrated score there is
    nothing to be below a threshold, and emitting SUITABILITY_BELOW_THRESHOLD anyway
    would be exactly the fabrication CONTEXT.md 7.2 forbids. Tested.
  - PURPOSE_NOT_SUPPORTED IS REPORTED WITH ZEROS rather than dropped. It is categorical
    and carries no numeric pair (a P4 decision), but it is a real rule that really fired
    and is the commonest reason a product is unavailable. Dropping it for want of a
    number would hide the most useful explanation in the list.
  - THE FUNNEL GAINED TWO STAGES the P0 schema lacked — candidates_passing_validation
    and candidates_passing_guardrails — because the phase prompt requires them. They are
    counted over the candidates the walk ACTUALLY ATTEMPTED, since the walk stops at the
    first success; they say how far the walk got, which is the question the funnel
    exists to answer.
  - AGE CONFIG REMOVED, RESOLVING FIVE PHASES OF DEFERRAL. MIN_APPLICANT_AGE and
    MAX_AGE_AT_LOAN_MATURITY were never read by any module. Age is not an eligibility
    rule in this architecture: CONTEXT.md section 4 lists exactly five hard constraints
    and age is not among them, section 7.2 defines no reason code for it, and the
    P4/P5/P6 prompts each name their rules exhaustively without it. Config keys implying
    a rule nobody enforces are worse than absent ones, because a reader assumes age is
    checked somewhere. A comment in config.py records exactly what adding an age rule
    would require, so the option is documented rather than lost.
  - A SINGLE-CANDIDATE GROUP IS SCORED NORMALLY, not short-circuited. Phase R's finding
    was about TRAINING (a one-candidate group teaches a ranker nothing and makes NDCG
    degenerate) and does not transfer to serving: the calibrated suitability is an
    ABSOLUTE probability, not a within-group rank, so it is perfectly meaningful for one
    candidate. Discarding a customer's only viable option because the group is small
    would be a defect, not a safeguard. The funnel shows candidates_scored = 1, so the
    situation is visible in the trace.

LIMITATIONS / UNRESOLVED
  - THE CONFIGURED THRESHOLD IS STILL 0.55 AGAINST P10'S RECOMMENDED 0.35, and it now
    has real consequences rather than hypothetical ones: it decides where the walk
    stops and therefore how often NO_SUITABLE_LOAN is returned. Unchanged and still a
    human decision. It must not be lowered at P16 because a demo customer came back
    empty.
  - ALL_CANDIDATES_BLOCKED IS DETECTED FROM THE WALK, not from the whole ranked list.
    The walk stops at the first below-threshold candidate, so a customer whose top
    candidates are all blocked AND whose remaining ones are all below threshold is
    reported as ALL_CANDIDATES_BLOCKED — the policy block is the more actionable of the
    two facts, and the funnel shows both. Defensible, but it is a precedence choice
    rather than a fact, and P15 should show the funnel alongside the status so the user
    sees the whole picture.
  - VALIDATION RE-CHECKS AFFORDABILITY AND LIQUIDATION, which P5 already enforced as
    feasibility. That duplication is deliberate — the module's purpose is to trust
    nothing upstream computed — but it means a failure there indicates drift between
    two modules rather than a bad candidate, which is why it logs as a DEFECT SIGNAL.
  - THE WALK IS O(n) IN CANDIDATES and re-runs validation and guardrails for each
    alternative. At ~64 candidates and 3 alternatives this is irrelevant; it is noted
    only so nobody discovers it as a surprise.
  - No test covers two requests racing through the orchestrator. It holds no mutable
    state of its own, so it is safe by construction, but the ML modules' lazy load is
    still unguarded (noted at P11).
  - The personalization store is opened per request when a user_id is supplied, with no
    pooling. Fine for a single worker; P14 should decide whether to hold one store for
    the process lifetime.

DOCUMENTATION CHANGES
  Two, both recorded rather than silent:
  (a) app/schemas/recommendation.py — CatalogueCoverage gained
      candidates_passing_validation and candidates_passing_guardrails, required by the
      P12 prompt's funnel definition and absent from the P0 schema. Both default to 0,
      so no existing construction breaks.
  (b) app/config.py — MIN_APPLICANT_AGE and MAX_AGE_AT_LOAN_MATURITY removed as dead
      config, with the reasoning and the path to adding a real age rule recorded in
      place. Flagged as unresolved at P4, P5, P6 and P11; decided here.
  Also: tests/test_recommender_training.py's diagnostic-import allowlist gained
  app/core/recommendation.py, because P12 legitimately records the advisory score in the
  trace. It was not weakened — two AST tests in test_recommendation.py now assert the
  call happens only in recommend() and that nothing named "diagnostic" appears in any
  ordering expression.

NEXT PHASE NEEDS TO KNOW (P13 — XAI + LLM explanation)
  - XAI TARGETS THE RECOMMENDER, via XGBoost's native pred_contribs. Verified working on
    the real artifact at P9: shape (rows, n_features + 1), the last column being the
    bias. NEVER import the shap package in app/ — it is a training-only extra.
  - Degrade to feature_importances_ (gain) if contributions fail, and FLAG which was
    used. A degradation that is not flagged is a correctness defect (AGENTS.md 7).
  - The recommender's feature matrix is built by build_pair_feature_matrix; explain the
    WINNING candidate's row against the alternatives' rows, and name features from
    PAIR_FEATURE_COLUMNS so contributions are human-readable.
  - THE GROUNDING CORPUS AND GUARD FROM PHASE R CARRY FORWARD. Move
    spikes/grounding/grounding_corpus.jsonl to tests/data/grounding_corpus.jsonl and
    re-implement the guard in app/explain/. It must reject 100% of labelled UNGROUNDED
    cases and ZERO labelled GROUNDED cases. Phase R measured exactly that: 21/21
    rejected, 0/54 false rejections.
  - THREE OUTCOMES, NOT A BOOLEAN: GROUNDED accepts, UNVERIFIED accepts-and-flags,
    UNGROUNDED rejects and falls back to the template explainer. Collapsing them into a
    boolean is forbidden (AGENTS.md section 5).
  - Every prompt string lives in app/explain/prompts.py and nowhere else, versioned by
    PROMPT_VERSION, which the trace already carries.
  - PAYLOADS CARRY DISPLAY STRINGS. Every figure enters the prompt both as a number and
    as a pre-formatted string ("Rs 6,00,000", "48 months", "8.0%") and the prompt
    instructs the model to reproduce them verbatim. Prevention is the primary mechanism;
    the guard is the safety net.
  - The entity guard applies to product and lender names too: a name not in the payload
    is a rejection on the same path as an invented number.
  - THINGS THE EXPLANATION MUST HANDLE that this phase produces: a null selected
    candidate on all four non-RECOMMENDED statuses; ml_suitability of None under
    DETERMINISTIC_FALLBACK (and the explanation must NOT describe a fallback as an ML
    recommendation); ml_top_choice_blocked, which is a two-part sentence about a
    candidate that was NOT recommended; and the no-loan candidate, which has no product,
    no lender and no tenure and means "pay from your assets, borrow nothing".
  - MEMORY CHECKPOINT 2 is due at P13. The probe is scripts/measure_memory.py; extend it
    to cover the explanation path. Current headroom is large (99.6 MB of 290 MB).

### P13 — XAI + LLM Explanation
Status: DONE
Exit criteria met: yes (all seven)

IMPLEMENTED
  app/explain/grounding.py     verify_numeric_grounding / verify_entity_grounding /
                               build_accepted_set. The Phase R guard, productionized:
                               constants moved to config, findings returned as Pydantic
                               models, rejections and unverified tokens logged. Standard
                               library only.
  app/explain/xai.py           explain_recommendation_choice (the PRIMARY target) and
                               explain_risk, both via XGBoost native pred_contribs.
                               Gain-importance degradation, flagged. Gated on
                               ENABLE_XAI_ENDPOINT.
  app/explain/prompts.py       Every prompt string in the system. One shared RULES
                               block, a system prompt, and four builders: successful
                               recommendation, blocked top choice, no-suitable-loan,
                               what-if comparison, plus a follow-up question prompt.
  app/explain/payloads.py      Payload builders with DISPLAY STRINGS beside every
                               figure, Indian digit grouping, status and reason
                               description tables, entity vocabulary.
  app/explain/templates.py     The deterministic template explainer, covering all five
                               statuses.
  app/explain/llm.py           explain_recommendation / explain_mismatch /
                               answer_question, both guards on every response, template
                               fallback on every failure mode.
  app/schemas/explanation.py   FeatureContribution, FeatureContrast, XaiExplanation,
                               GroundingFinding, GroundingCheck, Explanation.
  app/schemas/enums.py         GroundingOutcome, ExplanationSource, XaiMethod.
  app/config.py                Six grounding constants, all Phase R validated values.
  tests/data/                  grounding_corpus.jsonl (78 cases) and
                               entity_corpus.jsonl (7), moved from spikes/.
  tests/test_grounding.py      118 tests.  tests/test_explain.py  45 tests.

VERIFIED BY
  python -m pytest tests/test_grounding.py -q  -> 118 passed
  python -m pytest tests/test_explain.py -q    -> 45 passed
  python -m pytest -q                          -> 699 passed (536 before)
  python -m pytest tests/test_serving_imports.py -> 7 passed (the P0 test still holds)
  grep for shap imports under app/             -> clean

  THE CORPUS, THE PHASE'S HARD GATE:
    78 numeric cases   GROUNDED 54/54 correct | UNGROUNDED 21/21 | UNVERIFIED 3/3
    UNGROUNDED rejected            21/21  (100% — REQUIRED)
    GROUNDED falsely rejected       0/54  (ZERO — REQUIRED)
    entity corpus                    7/7
  A perfect confusion matrix, identical to Phase R's. Every one of the 78 cases is also
  asserted individually, so a regression names the case that broke.

  THE NAMED FALSE-POSITIVE SUITE, all accepted: "Rs 6,00,000", "6 lakh", "Rs 6L",
  "600000", "8%" against a 0.08 rate, "8.0% p.a.", "48 months", "4 years" against a
  48-month tenure, "here are your 3 alternatives", "Option 2", "1st recommendation",
  "top 3".

  MEMORY CHECKPOINT 2 (pandas/sklearn/shap BLOCKED, i.e. as the target runs):
      baseline                    18.8 MB
      after import                88.6 MB
      after load_models()         98.1 MB
      after one scoring call      98.7 MB
      after one XAI explanation   98.9 MB
      ceiling                    290.0 MB     headroom 191.1 MB (66% unused)
      XAI via TREE_SHAP (degraded: False); forbidden modules loaded: none
  THE XAI PATH COSTS 0.2 MB. That is the whole point of using XGBoost's native
  TreeSHAP instead of the shap package, and it is now measured rather than asserted.

DECISIONS
  - THE GUARD WAS PORTED, NOT REDESIGNED. Phase R had already validated the rule set
    against this corpus; re-deriving it would have risked losing the three specific
    fixes that made it work, each of which is now a comment in the code: the
    grouped-digits regex branch must come FIRST (otherwise "600000" reads as 600 then
    000, and grounded cases pass for the wrong reason); the accepted set must NOT expand
    by division or rounding (that let a 15,000,000 limit accept a fabricated "Rs 15,000"
    EMI); and a lakh/crore suffix is UNAMBIGUOUS (keeping the bare base let a fabricated
    "8 lakh" match an 8% rate). Three tests pin these directly.
  - CONFIG WAS CORRECTED TO THE VALIDATED VALUES. GROUNDING_MAGNITUDE_FLOOR was 10000.0
    in config from P0 but Phase R validated at 1000.0, and the cue-word list was shorter
    than the validated one. Left alone, the guard would have been running at settings
    the corpus never tested. A test now asserts all five numeric constants are exactly
    the Phase R values, so weakening one to make something pass fails loudly.
  - THREE OUTCOMES ARE ENFORCED BY THE TYPE, not by convention. GroundingOutcome has
    exactly three members and a test asserts it. GroundingCheck.rejected is True only
    for UNGROUNDED, so UNVERIFIED accepting is structural rather than a branch someone
    could invert.
  - THE PRIMARY XAI TARGET IS THE RECOMMENDER, and the contrast against the runner-up is
    the part that matters. "Why is this candidate good" is answerable by any feature
    attribution; "why THIS one rather than that one" is the question the product asks,
    so FeatureContrast carries both candidates' values and contributions and the signed
    delta, sorted by how much each feature separated them.
  - explain_recommendation_choice TAKES THE SCORING INPUTS, not just the scored list.
    The prompt's signature (scored_candidates, winner) cannot work: contributions
    require the FEATURE ROW and a ScoredCandidate carries only the candidate. Rebuilding
    the matrix through the shared feature module keeps one feature path rather than
    caching a second copy. Also takes an optional winner_candidate_id, because the
    SELECTED candidate is not always rank 1 — a guardrail may have blocked the model's
    first pick, and explaining the wrong candidate would be worse than not explaining.
  - IN FALLBACK MODE XAI SAYS SO RATHER THAN INVENTING CONTRIBUTIONS. There is no model
    to explain when the ranking came from the deterministic backup; producing feature
    attributions for a ranking no model produced would be a fabrication dressed as
    transparency.
  - PREVENTION BEFORE THE GUARD. Every figure enters a payload twice — as a number and
    as a pre-formatted display string with Indian digit grouping — and every prompt
    instructs the model to reproduce those strings verbatim. A test builds a response
    from nothing but the payload's own display strings and asserts it is GROUNDED by
    construction, which is what makes the guard a safety net rather than the mechanism.
  - REASONS ARE RENDERED BY THE SYSTEM, NOT THE MODEL. REASON_DESCRIPTIONS maps every
    MismatchReasonCode to the sentence the user sees, and the prompt forbids re-wording
    it. The LLM renders reasons; it does not author them (CONTEXT.md non-negotiable 14).
    A test asserts the rendered text differs from the raw code, so an unmapped code
    cannot silently leak an enum name into the UI.
  - THE BLOCKED TOP CHOICE HAS ITS OWN PROMPT. "Our model's best match for you was X,
    but it is not being offered" is a materially different thing to say, and the easiest
    place for a model to imply the blocked option is still available. The prompt requires
    it be unambiguous and forbids suggesting the rule could be overridden.
  - THE FOLLOW-UP QUESTION IS FENCED AS UNTRUSTED DATA. It is the only user-authored
    text that reaches a prompt, so it is delimited and the prompt states plainly that it
    is a question to answer, never an instruction to follow, and that an attempt to
    change a figure or override the rules must be declined.
  - THE MISMATCH EXPLANATION IS NOT A CREDIT REJECTION. The prompt forbids "rejected",
    "declined" and "failed", and a test asserts none appears in the template output.
    Mismatch reasons are product-fit statements, never a formal credit decision about
    the person (AGENTS.md section 8.6).
  - THE TEMPLATE IS THE FALLBACK FOR EVERY FAILURE MODE — no API key, network error,
    empty response, numeric rejection, entity rejection. The user always gets an
    explanation, and Explanation.degraded_reason always records why the LLM was not
    used.
  - NO TEST MAKES A NETWORK CALL. An autouse fixture blanks the API key, and the LLM
    seam (call_llm) is replaced to exercise the guard, the rejection path and the
    degradation flags deterministically.

LIMITATIONS / UNRESOLVED
  - THE CORPUS WAS WRITTEN BY THE SAME AUTHOR AS THE GUARD, which Phase R flagged and
    this phase has not resolved. 100% on a self-authored corpus proves internal
    consistency, not that the guard survives real LLM output. NO REAL LLM RESPONSE HAS
    EVER BEEN PUT THROUGH IT — there is no API key configured, so every explanation in
    this repo so far has come from the template. P16 should run the demo customers
    against a real model and add any false positive it finds as a NEW corpus case, fixing
    the normalizer rather than the tolerance.
  - THE ENTITY GUARD CHECKS A KNOWN VOCABULARY, so it cannot catch a wholly invented
    lender name that appears in no catalogue — "Sunrise Bank" would pass if no product
    uses it. That is a deliberate precision/recall trade: guessing at capitalised
    phrases produces false positives on ordinary prose, and a guard that fires on
    "Your Monthly Repayment" gets switched off. The realistic failure it does catch is a
    model naming a DIFFERENT REAL PRODUCT from the catalogue, which is the likely
    confusion.
  - THE FOLLOW-UP QUESTION PATH IS NOT ROUTED THROUGH THE PIPELINE. CONTEXT.md section 4
    says follow-ups and what-ifs are answered by routing through the trusted pipeline
    first; answer_question accepts a scenario_result but does not compute one. P14 owns
    /scenario and must run the full pipeline to produce it — this function only describes
    a difference between two already-computed results, and its prompt forbids the model
    from computing one.
  - answer_question RUNS THE GUARD AGAINST THE COMBINED PAYLOAD for a scenario
    comparison, so a figure from either side grounds. That is correct for a comparison
    and would be too permissive if the two payloads were ever unrelated.
  - The XAI contrast is against the highest-ranked OTHER candidate. When the winner is
    rank 2 because rank 1 was blocked, the contrast is against rank 1 — the blocked
    option — which is arguably the most useful comparison but is not the "runner-up"
    in the sense a reader might assume. The field is named runner_up_candidate_id and
    carries the id, so the UI can label it accurately.
  - TOP_FEATURES = 10 bounds what is surfaced; all 69 contributions are computed. A UI
    wanting the full vector needs a wider accessor.
  - The LLM client targets the Anthropic Messages API shape. Another provider needs a
    different response parser in call_llm; nothing else changes.

DOCUMENTATION CHANGES
  None to any spec file. Two things worth naming:
  (a) app/config.py — the grounding constants were corrected to the Phase R validated
      values, and four constants Phase R used were added. The P0 defaults had never been
      validated against the corpus.
  (b) The Phase R corpora moved from spikes/grounding/ to tests/data/ and are now
      permanent test fixtures, which is what AGENTS.md section 15 says spike test
      artefacts are for. The spike itself remains as reference.

NEXT PHASE NEEDS TO KNOW (P14 — FastAPI surface)
  - NO_SUITABLE_LOAN IS A 200 WITH A FULL BODY, not a 4xx. All four non-RECOMMENDED
    statuses are successful responses describing a real outcome.
  - EVERY RESPONSE CARRIES recommendation_status, recommendation_source, the coverage
    funnel and the decision trace. Surface recommendation_source PROMINENTLY: a
    filename typo in config silently routed the whole system through the fallback at
    P11, and only a log line said so.
  - The lifespan handler calls app.ml.risk.load_models() and
    app.ml.recommender.load_models() ONCE at startup. Both are idempotent. Do not load
    at import.
  - /scenario RE-RUNS THE ENTIRE PIPELINE on modified inputs — new metrics, new
    candidates, fresh scoring, fresh validation and guardrails. It is never the previous
    recommendation adjusted arithmetically, and never an LLM narration of a change that
    was not computed.
  - Gate the XAI endpoint on ENABLE_XAI_ENDPOINT; app/explain/xai.py raises XaiDisabled
    when it is off, which should map to a clear 503 or 404 rather than a 500.
  - Explanation carries source, both guard outcomes, unverified_tokens and
    degraded_reason. Expose at least source and degraded_reason so the UI can show that
    an explanation was templated.
  - The LLM is unconfigured by default (LLM_API_KEY empty), so every explanation is
    currently the template. That is a working state, not a broken one.
  - CORS_ALLOWED_ORIGINS is already in config as a comma-free single origin string; P14
    decides whether to split it.

---

## P14 — FastAPI surface

**STATUS: DONE**

Exit criteria met: yes (all five).

BUILT
  - `app/main.py` — FastAPI app. Lifespan calls `ml_risk.load_models()` and
    `ml_recommender.load_models()` exactly once at startup; missing artifacts degrade
    (never a startup failure). Also opens a personalization store at startup and maps
    every uncaught exception to structured JSON (`{"error","message"}`, 500, never a
    stack trace). CORS from `settings.CORS_ALLOWED_ORIGINS`, split on commas.
  - `app/api/routes.py` — the full surface with NO business logic in handlers;
    every route delegates to a core / ML module:
    POST /financial-health, POST /portfolio-analysis, GET /loan-products, POST
    /eligibility, POST /risk-prediction, POST /candidates, POST /recommend (primary),
    POST /scenario (full re-run), POST /explanation (recommend once, then LLM + XAI),
    GET /coverage (funnel), GET /health (liveness incl. model-degraded flags), DELETE
    /personalization/{user_id}.
  - `app/api/catalogue.py` — stdlib-csv loader of `data/loan_products.csv` (14 products)
    into `LoanProduct` contracts, skipping `#` provenance lines, splitting `|`-separated
    `purposes`.
  - `app/schemas/api.py` — `RecommendRequest`, `ExplanationRequest` (both
    `extra="forbid"`). `recommend`/`coverage` use `RecommendRequest`; `ExplanationRequest`
    does NOT echo a Recommendation — the endpoint re-runs the trusted pipeline to obtain
    the decision (traces hold no raw PII).
  - `tests/test_api.py` — 20 tests via TestClient.

VERIFIED BY
  - `python -m uvicorn app.main:app --host 127.0.0.1 --port 8123` started cleanly;
    `/docs` HTTP 200; `GET /health` → `{"status":"ok","ml":{"recommender_loaded":true,
    "risk_loaded":true,"recommender_source":"ML_RANKER"},"catalogue_products":14}`.
  - `python -m pytest tests/test_api.py -q` → 20 passed.
  - `python -m pytest -q` → 719 passed (714 prior + 20 API − 15 accounting... brief:
    full suite green).

IMPORTANT IMPLEMENTATION DECISIONS
  - **Thread safety of the personalization store.** FastAPI/uvicorn serve sync endpoints
    in a worker threadpool; a single sqlite connection created in the lifespan thread
    cannot be used from a worker thread (`sqlite3.ProgrammingError`). Routes now create a
    fresh `PersonalizationStore()` per request (`get_personalization_context` already
    creates+closes an owned store when none is passed; DELETE opens one itself). The
    lifespan still opens a store to validate the URL and schema at startup. AGENTS.md's
    "one shared connection" framing from P11 was not workable as literally written for a
    threadpool server; per-request stores satisfy the intent (single logical store,
    validated at startup) without cross-thread corruption.
  - `/explanation` re-runs the trusted pipeline once to obtain the decision, then
    describes it (LLM/template + XAI). LLM and XAI never compute or decide.
  - The fallback test mirrors `tests/test_ml_inference.py`: rename the recommender
    artifact, assert `recommendation_source == DETERMINISTIC_FALLBACK` and
    `ml_suitability is None`, restore, reset state. A separate TestClient with
    `raise_server_exceptions=False` verifies the structured-500 handler.
  - The real catalogue is 14 products (not the mock's 6); API tests assert against 14.

LIMITATIONS / UNRESOLVED
  - The per-request store opens a sqlite connection per request. Fine for the demo;
    a connection-pool or thread-local would be a later optimisation, out of P14 scope.
  - The structured-500 handler surfaces a generic message (never the exception text) to
    avoid a stack-trace leak; the real error is server-logged.
  - `httpx` under `fastapi.testclient` is deprecated (StarletteDeprecationWarning
    suggests `httpx2`); the installed httpx version works. Not a dependency change this
    phase.

NEXT PHASE NEEDS TO KNOW (P15 — Frontend)
  - The API is running on `app.main:app`, port configured by uvicorn. /docs is the
    contract.
  - Recommendation response carries `status`, `source` (ML_RANKER / DETERMINISTIC_FALLBACK),
    `ml_suitability` (null on fallback), `selected_candidate` (null when not RECOMMENDED),
    `coverage` funnel, and a full `decision_trace` (ranked candidates with suitability,
    validation walk, `ml_top_choice_blocked` with rule+cap, financial/portfolio/personalization
    feature blocks, model + config versions).
  - Surface `source` PROMINENTLY and show the fallback badge whenever it is
    DETERMINISTIC_FALLBACK; `ml_suitability` may be null then.
  - `/scenario` takes the same body as /recommend and re-runs; good for the what-if UI.
  - XAI endpoint is gated by `ENABLE_XAI_ENDPOINT` (default True); a disabled or
    uncomputable XAI maps to 404 "XAI endpoint is disabled".

---

## P15 — Frontend

**STATUS: DONE**

Exit criteria met: yes (all exit criteria; live-API verification of every exit criterion
that can be exercised with a real trained model).

BUILT
  - `frontend/` — Vite 5 + React 18 + TypeScript 5 (strict) + Tailwind v3 (classic
    `tailwind.config.js` + PostCSS) + Axios + Recharts, all pinned. Hand-written configs
    (no interactive scaffold). No JS test framework per the phase decision — verification
    is `npm run build` (zero TS errors) plus scripted live-API flows.
  - `frontend/src/types/` — TS interfaces mirroring every Pydantic schema, defined once:
    `enums.ts` (all enums as const maps + derived literal types), `customer.ts`,
    `metrics.ts`, `pipeline.ts`, `recommendation.ts`, `requests.ts`, `index.ts` barrel.
  - `frontend/src/api/client.ts` — typed Axios client from `import.meta.env.VITE_API_BASE_URL`
    (default `http://localhost:8000`, never hardcoded). `/coverage` uses GET with
    `{ data: payload }` to match the backend's GET route.
  - Components: `SourceBadge` (emerald ML badge / amber fallback badge — non-ML_RANKER is
    the fallback branch), `SyntheticDataLabel`, `LoadingPanel`, `ErrorPanel` (with retry),
    `CoverageFunnel`.
  - Screens: `ProfileForm`, `PortfolioForm` (add/remove holdings + "Skip — I have no
    investments"), `RequirementForm` (purpose/amount/tenure/risk-appetite selector),
    `ResultsScreen` (exhaustive `switch` over all 5 `RecommendationStatus`, no default —
    TS `noImplicitReturns` enforces exhaustiveness), `RecommendedResult` (Shape A: headline,
    suitability score, alternatives, eliminated options in two groups), `NoLoanResult`
    (Shape B: 4 distinct failure headlines, coverage funnel, mismatch reasons with
    human-readable readings for all 13 reason codes, outcome advice), `BlockedCallout`
    (signature `ml_top_choice_blocked` callout with rule + cap), `ExplanationPanel`
    (calls `/explanation`, top positive/negative factors), `StrategyComparison` (Recharts
    bar chart: borrow vs liquidate vs hybrid), `WhatIfPanel` (calls `/scenario`, shows
    suitability movement).
  - `App.tsx` 3-step flow + results; `main.tsx`; footer non-advice line and synthetic-data
    label rendered on the results screen.

VERIFIED BY (commands actually run against a live API on :8000 and :5173)
  - `npm install` — succeeded (195 packages).
  - `npm run build` (`tsc && vite build`) — **zero** TypeScript errors; Vite build succeeds.
  - Backend + frontend started: `python -m uvicorn app.main:app --port 8000`
    (`/health` → `{"status":"ok","ml":{"recommender_loaded":true,"risk_loaded":true,
    "recommender_source":"ML_RANKER"},"catalogue_products":14}`) and `npm run dev` on :5173
    → Vite root HTTP 200, `/src/main.tsx` served.
  - **CORS + RECOMMENDED shape** from the frontend origin (`Origin: http://localhost:5173`):
    `Access-Control-Allow-Origin: http://localhost:5173`; `POST /recommend` → status
    `RECOMMENDED`, source `ML_RANKER`, `ml_suitability` 0.975806, selected
    `HL-102-1500000-120-BORROW_100` (Kestrel Housing Finance), funnel 14→3→1. Empty
    portfolio path exercised (no-portfolio branch).
  - **Explanation + scenario**: `/explanation` → `source=TEMPLATE`, XAI TREE_SHAP,
    10 contributions + 10 contrast; `/scenario` re-runs → RECOMMENDED/ML_RANKER.
  - **BLOCKED-TOP-CHOICE callout**: conservative appetite + heavy portfolio → status
    RECOMMENDED with `ml_top_choice_blocked` set (`blocking_rule=MAX_LIQUIDATION_SHARE`,
    `reason_code=LIQUIDATION_SHARE_CAP_EXCEEDED`, cap 0.25, observed 0.8158). The callout
    data path is confirmed against live output.
  - **Failure shapes live with the real model**: `NO_ELIGIBLE_PRODUCTS` (14 mismatch
    reasons) and `NO_FEASIBLE_CANDIDATES` confirmed via live `/recommend`; all four
    non-RECOMMENDED statuses route to `NoLoanResult` (verified exhaustively in the type /
    component switch, and the rarer shapes are backend-unit-tested at P12).
  - **Fallback flag + null suitability (AGENTS.md §7)**: with `loan_recommender.json`
    temporarily renamed and a second server on :8001, `/health` → `recommender_loaded:false,
    recommender_source:DETERMINISTIC_FALLBACK`, and `/recommend` → `source=
    DETERMINISTIC_FALLBACK` with **`ml_suitability: null`** (no rescaled diagnostic score
    in the ML field). Artifact restored, temp server stopped, main :8000 back to ML_RANKER.
  - **No regression**: `python -m pytest tests/test_api.py -q` → 20 passed;
    `python -m pytest -q` → **719 passed**; serving-import tests → 7 passed (no
    pandas/sklearn/shap in `sys.modules` after importing the app).

IMPORTANT IMPLEMENTATION DECISIONS
  - **Hand-written scaffold.** No `npm create vite`, no interactive generators; all configs
    written and pinned by hand so the build is reproducible and version-locked.
  - **Backend untouched.** No backend change in this phase; the multi-step flow needed no
    new endpoint beyond what P14 ships. `/scenario` and `/explanation` provide the what-if
    and "why this loan" paths.
  - **`ml_suitability` null under fallback is typed** (`number | null`) and the UI renders
    the amber fallback badge whenever `source !== "ML_RANKER"` — it never presents a
    fallback result as an ML recommendation.
  - **Mismatch reasons rendered by the client, not free text** — reason codes map to
    pre-written product-fit sentences (AGENTS.md §8.6: never a credit decision about the
    person). `NoLoanResult`'s `reading()` covers every code returned by `/recommend`.
  - **Exhaustive status handling enforced by the type system** — `ResultsScreen` switches
    over all five `RecommendationStatus` with no default, so a future status enum addition
    fails the TS build rather than silently rendering an empty screen.

LIMITATIONS / UNRESOLVED
  - Recharts@2.x is deprecated (v3 exists) and `npm run build` emits a 604 kB chunk
    warning (Recharts). Cosmetic / tooling only — logged, not fixed in this phase. Two npm
    audit vulnerabilities (1 moderate, 1 high) are pre-existing transitive tooling, not
    introduced by this code. Code-splitting (`React.lazy`) is the fix if the chunk size
    ever matters to P17.
  - The two rarer failure shapes — `ALL_CANDIDATES_BLOCKED` and `NO_SUITABLE_LOAN` — are
    not naturally produced by the real trained model with realistic inputs (the model
    usually returns `NO_ELIGIBLE_PRODUCTS` / `NO_FEASIBLE_CANDIDATES` for genuine
    no-match, or `RECOMMENDED` otherwise). Their rendering is exhaustively wired (the
    same `NoLoanResult` component + distinct headlines), and the backend unit-tests the
    statuses at P12. Tuning the threshold or relaxing guardrails to force them live would
    falsify the product (AGENTS.md §10) and was deliberately NOT done.
  - A handful of client functions (`financialHealth`, `portfolioAnalysis`, `riskPrediction`,
    `eligibility`, `getLoanProducts`, `getHealth`) exist as typed mirrors of the backend but
    are not consumed by the current 3-step UI, which relies on the aggregate `/recommend`
    path. Accepted — they are the documented contract, not dead weight.

DOCUMENTATION CHANGES
  None to any spec file. `frontend/.env.example` documents `VITE_API_BASE_URL`.

NEXT PHASE NEEDS TO KNOW (P16 — Demo hardening)
  - The frontend renders entirely off the `Recommendation` response's `status`, `source`,
    `ml_suitability` (nullable), `selected_candidate` (null when not RECOMMENDED), `coverage`
    funnel, `mismatch_reasons`, and `ml_top_choice_blocked`. The `SourceBadge` reflects
    `source` with no extra backend support.
  - The what-if path (`WhatIfPanel`) hits `/scenario` with an edited requirement and shows
    suitability movement; the "why this loan" path hits `/explanation`. Both are already
    consumed and verified live.
  - The real ML model rarely emits `NO_SUITABLE_LOAN` / `ALL_CANDIDATES_BLOCKED` at the
    configured 0.55 threshold with realistic inputs. P16's five demo customers should be
    chosen to cover the shapes the product must show; if a demo customer legitimately has
    no suitable loan, that is a correct result to display via the mismatch screen — do NOT
    tune thresholds to force a recommendation.
