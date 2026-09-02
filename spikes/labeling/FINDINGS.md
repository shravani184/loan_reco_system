# SPIKE 1 — Labeling policy invariants: FINDINGS

**Risk addressed:** CONTEXT.md §17.1 — a flawed relevance labeling policy silently
teaches the primary recommender the wrong notion of "suitable", and no downstream
metric can detect it because every downstream metric is measured against those labels.

**Status: RESOLVED.** 15 invariants pass, mutation score 7/7, degeneracy constraints
met, stress label-flip rate inside the target band.

Verified by:

```
python3 -m pytest spikes/labeling/test_invariants.py -q    ->  15 passed
python3 spikes/labeling/population.py                      ->  report below
```

---

## 1. Validated sub-score definitions

Four stages, each separately testable. Every quantity is a **ratio**, which is what
makes scale invariance hold.

| Stage | Contents |
|---|---|
| A — disqualifiers | `EMI_EXCEEDS_AFFORDABILITY`, `DEBT_BURDEN_CAP_EXCEEDED`, `FUNDING_SHORTFALL`, `LIQUIDATION_EXCEEDS_PORTFOLIO`, `NO_INCOME` |
| B — sub-scores | affordability, cost, portfolio impact, appetite alignment — each in `[0,1]`, each owning one concern |
| C — combination | weighted sum → within-group rank → absolute quality cap |
| D — stress | shared-scenario income shock → one-grade demotion |

**Sub-score definitions as validated:**

- **affordability** = `1 − EMI / (disposable × 0.60)`
- **cost** = `1 − (total_interest + opportunity_cost) / required_amount / 1.20`
  where `opportunity_cost` is the return forgone on liquidated holdings over a fixed
  5-year horizon (liquid 6%, volatile 11%)
- **portfolio impact** = `1 − liquidation_share − 0.50 × volatile_share − 1.20 × buffer_shortfall`
  where `buffer_shortfall` is the deficit against a 6-month emergency buffer
- **appetite** = `1 − post_loan_DBR / cap[appetite] − volatile_penalty[appetite] × volatile_share`
  with caps 0.30 / 0.40 / 0.50 and volatile penalties 0.60 / 0.30 / 0.10

**Final constants:**

```
W_AFFORDABILITY = 0.22    W_COST = 0.33    W_PORTFOLIO_IMPACT = 0.25    W_APPETITE = 0.20
GRADE_QUANTILES        = (0.15, 0.40, 0.70)     # top 15% -> 3, next 25% -> 2, next 30% -> 1
ABSOLUTE_GRADE_FLOORS  = (0.60, 0.45, 0.33)     # raw score needed to be ALLOWED grade 3/2/1
TARGET_BUFFER_MONTHS   = 6.0    BUFFER_SHORTFALL_WEIGHT = 1.20
OPPORTUNITY_HORIZON_YEARS = 5.0  LIQUID_ASSET_RETURN = 0.06  VOLATILE_ASSET_RETURN = 0.11
```

Affordability carries a deliberately modest weight because it is **already enforced
twice** — as a Stage A hard disqualifier and inside the appetite sub-score's debt-burden
term. Weighting it a third time was one of the causes of the degeneracy below.

## 2. Stress simulation: parameters and measured flip rate

```
STRESS_SEED = 20260901        STRESS_SIMS = 200
STRESS_SHOCK_PROBABILITY = 0.35        STRESS_MAGNITUDE_RANGE = (0.20, 0.55)
STRESS_DEMOTION_THRESHOLD = 0.32
```

**Measured label-flip rate: 9.52%** (788 of 8,277 labels), inside the required 2%–30%
band. Scenario draws are shared across all customers and candidates from a constant
seed — that is what keeps the simulation deterministic, monotone in EMI, and
scale-invariant simultaneously.

During tuning, `STRESS_DEMOTION_THRESHOLD = 0.35` produced a **0.00%** flip rate: the
simulation ran but changed nothing. That is precisely the "below 2% means it is doing
nothing" case the band exists to catch, and it argues for keeping the band check in
Phase 7 rather than treating it as a formality.

## 3. Invariants — all passing

| # | Invariant | Result |
|---|---|---|
| 1 | Dominance (score and grade) | PASS |
| 2 | Single-axis monotonicity: lower rate, smaller liquidation share | PASS |
| 2b | Volatile liquidation never scores above liquid | PASS *(added after mutation testing)* |
| 2c | Liquidation is never free | PASS *(added after mutation testing)* |
| 2d | Stress can only demote, never promote | PASS *(added after mutation testing)* |
| 3 | Scale invariance (grades and scores) | PASS |
| 4 | Appetite ordering | PASS |
| 5 | Zero-portfolio consistency | PASS |
| 6 | Population non-degeneracy | PASS |
| 7 | Population contains no-good-option customers | PASS |

## 4. Mutation testing — the invariants have teeth

Invariants that pass prove nothing unless they can fail. Seven realistic defects were
planted one at a time:

| Planted defect | First run | After closing gaps |
|---|---|---|
| Absolute rupee threshold in a sub-score | CAUGHT | CAUGHT |
| Sign error on the volatile portfolio penalty | **MISSED** | CAUGHT |
| Appetite caps inverted | CAUGHT | CAUGHT |
| Opportunity cost dropped from the cost sub-score | **MISSED** | CAUGHT |
| Quantile bands inverted | CAUGHT | CAUGHT |
| Stress demotion promotes instead of demoting | **MISSED** | CAUGHT |
| Funding-shortfall disqualifier removed | — | CAUGHT |

**Final mutation score: 7/7.**

The three misses are the most valuable output of this spike. The original suite looked
complete and was not: the liquidation invariant only ever exercised
`volatile_liquidated == 0`, so a sign error on the volatile penalty survived every
test. **Phase 7 must run this mutation check after porting the suite** — a passing
invariant suite is not evidence until you have watched it fail.

## 5. Degeneracy report (300 synthetic customers, seed 42)

```
customers with candidates : 225        labels: 8,277
grade shares              : 0 -> 39.4% | 1 -> 32.6% | 2 -> 21.2% | 3 -> 6.8%
max grade share           : 0.39   (limit 0.60)  PASS
max product win share     : 0.50   (limit 0.60)  PASS
max tenure win share      : 0.50   (limit 0.60)  PASS
max strategy win share    : 0.50   (limit 0.60)  PASS
no-good-option customers  : 59 of 225 (26.2%)    PASS (must be > 0)
```

### Two real defects the report exposed

**(a) 100%-liquidate won 92% of groups.** The policy treated selling holdings as free —
no interest, no EMI, so affordability and cost both scored 1.0 and nothing could beat
it. Two fixes: an **opportunity-cost term** in the cost sub-score (return forgone on
liquidated assets over a fixed horizon) and an **emergency-buffer term** in portfolio
impact. Concentration fell 92% → 73% → **50%**, and the labels now contain a real
trade-off: short-tenure borrowing beats liquidation, long-tenure borrowing loses to it.

**(b) One product won 99% of groups — a candidate-generation artifact, not a policy
flaw.** A 100%-liquidate candidate borrows nothing, so product and tenure are
meaningless for it, yet one was emitted per product × tenure: 26 candidates per
customer with **identical scores**, decided by tie-break order. Fixed by emitting the
no-loan candidate exactly **once**. See §6 — this is a Phase 5 requirement.

**(c) Infeasible candidates must not be labelled.** Labelling them inflated grade 0 to
75% of the dataset. In the v2.0 architecture the recommender only ever sees feasible
candidates, so the labelled set must be filtered first.

## 6. Findings that belong to OTHER phases

| Finding | Owning phase |
|---|---|
| The 100%-liquidate ("no loan") candidate must be generated **once per customer**, not per product × tenure — product and tenure are meaningless when nothing is borrowed | **P5** |
| Only **feasible** candidates enter the labelled dataset; infeasible ones are marked and excluded | **P5 / P7** |
| Group sizes ranged 1–111 (median 28). **8 of 225 groups (3.6%) had a single candidate** — useless for learning-to-rank and degenerate for NDCG. Exclude groups with <2 candidates from training, and short-circuit ranking at serving | **P7 / P12** |
| The no-loan candidate carries `tenure = 1 month, EMI = 0`. Rendering that as a 1-month loan would be wrong; it is "pay from your assets, borrow nothing" | **P0 schema / P15 frontend** |
| Stage A duplicates Phase 5's feasibility rules. They must be the same rules, defined once — if they drift, the training set and the serving candidate set disagree | **P5 / P7** |

## 7. Human audit sample

`label_audit_sample.md` (20 customers) was generated and read. The labels are broadly
sensible: thin-file customers get few candidates and low grades; large-portfolio
customers are told to pay from assets; long-tenure high-interest options are graded
down.

One judgment call worth flagging for Phase 7: **Customer 2** (AGGRESSIVE appetite,
₹11.6M portfolio, needs ₹7.8M) is labelled "liquidate 67% of the portfolio" as its best
option. That is defensible on cost, but an aggressive investor may well prefer to
borrow and keep market exposure. The appetite sub-score's volatile penalty for
AGGRESSIVE (0.10) may be too weak. This is a *tuning* question, not a correctness one —
no invariant is violated — and it is exactly the class of issue only a human reading the
sample will catch.

## 8. What Phase 7 inherits

- **Port `test_invariants.py`** to `tests/test_labeling_invariants.py` against the real
  schemas, and run it **before** writing the policy.
- **Re-run the mutation check** after porting. Do not trust a green suite you have not
  seen fail.
- Adopt the constants in §1–§2 as starting values; re-measure the flip rate and the
  degeneracy report against the real generator, since both depend on the candidate mix.
- The degeneracy report and the audit sample are **build artifacts**, produced on every
  dataset build — not one-off checks.

## 9. Risks remaining

- The stress simulation shares one scenario draw across all customers. This is what
  makes it deterministic and scale-invariant, but it means every customer faces the
  same shock sequence. Realistic enough for a demo; noted as a simplification.
- Constants were tuned against a synthetic population built in this spike. Phase 7's
  real generator will shift the distributions, so the degeneracy thresholds must be
  re-checked, not assumed.
- Everything here remains a synthetic policy. Nothing in this spike makes the labels
  *correct* — only *self-consistent and non-degenerate*. The gap to real relevance data
  stands and is recorded in `PRODUCTION_ROADMAP.md`.
