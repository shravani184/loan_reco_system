# Production Roadmap

What this demo does not attempt, and would need before any real deployment involving
real customer data or real lending decisions.

Architecture v2.0 makes a machine-learning model the primary recommender. That raises
the stakes of everything below: a miscalibrated ranker no longer merely tints a
deterministic decision, it *is* the decision. The recommendation-model sections come
first for that reason.

---

## Recommendation model (the primary model)

- **Real relevance data.** Replace the synthetic labeling policy in
  `training/labeling.py` with observed outcomes: which offers customers accepted,
  which they repaid comfortably, which they refinanced, which went delinquent.
  Until then, every reported ranking metric measures agreement with a policy the
  project wrote itself. This is the single largest gap — see `LIMITATIONS.md`.
- **Recommendation quality measurement in production.** Offline NDCG against
  synthetic labels is not recommendation quality. Production needs accept rate,
  time-to-decision, post-disbursal repayment performance of recommended options
  versus alternatives, and complaint/regret rates, tracked per segment.
- **Counterfactual and off-policy evaluation.** Because the deployed recommender
  determines what customers see, naive logging cannot answer "would another ranking
  have done better". Needs logged propensities, inverse-propensity or doubly-robust
  estimators, and an interleaving or A/B framework before any ranking change ships.
- **Ranking drift monitoring.** Track the distribution of calibrated suitability
  scores, rank-position churn for equivalent profiles over time, and pairwise
  ranking stability. A ranker can retain its NDCG while quietly changing which
  segment it favours — score-distribution drift and feature drift must both alert.
- **Suitability calibration in production.** The isotonic transform is fitted on
  synthetic labels and inherits their bias. Refit against real observed outcomes,
  monitor reliability curves and Brier score continuously, and treat a calibration
  break as a page-worthy incident, because `SUITABILITY_ACCEPTANCE_THRESHOLD` sits
  directly on top of it — a drifted calibrator silently changes who gets told "no
  suitable loan".
- **Acceptance-threshold governance.** That threshold is a business policy, not a
  tuning knob. It needs an owner, a change-approval path, versioned history, and
  monitoring of the `NO_SUITABLE_LOAN` rate before and after every change.
- **Candidate-space auditing.** The recommender can only choose from what candidate
  generation produces. Grid steps, tenure options, strategy splits and the
  per-product cap therefore shape outcomes as much as the model does, and need the
  same change control and the same drift review.
- **Cold-start and personalization fairness.** Verify that returning customers do
  not receive systematically better options than cold-start ones for equivalent
  financial profiles, and that personalization features do not become proxies for
  protected attributes.

## Risk model (secondary)

- **Probability calibration.** Platt scaling or isotonic regression against real
  observed default rates, with calibration drift monitored (reliability diagrams,
  Brier score).
- **Contained blast radius.** The risk PD is a feature of the recommender. Any
  change to it shifts recommendations, so risk-model releases need the same
  champion/challenger treatment as recommender releases, evaluated on
  *recommendation* metrics and not only on AUC.
- **Real training data.** Replace synthetic financial profiles with real, licensed
  lending/credit data.

## Shared model infrastructure

- **Fairness auditing.** Disparate-impact analysis (e.g. Aequitas or Fairlearn)
  across protected and proxy attributes for the recommender *and* the risk model,
  measured on what customers actually receive — recommended rate, recommended
  amount and tenure, suitability score distribution, and `NO_SUITABLE_LOAN` rate by
  group — with a defined remediation process, repeated on every retrain.
- **Labeling-policy lineage and governance.** `LABELING_POLICY_VERSION` ties every
  model to the definition of "suitable" it was trained on. In production that
  definition is a business artefact: changes need an owner, review, a recorded
  rationale, and a re-run of the invariant suite plus the label audit sample before
  any retrain. The invariants themselves (dominance, scale invariance, appetite
  ordering) should run in CI on every dataset build, not only when the policy changes.
- **Model registry with lineage.** Every deployed model version tracked with its
  training data snapshot, labeling-policy version, `FEATURE_VERSION`, the calibrator
  fitted with it, hyperparameters and evaluation metrics (MLflow or equivalent), so
  any production recommendation traces back to exactly what produced it. The
  recommender and its calibrator version together, never independently.
- **Feature contract enforcement across environments.** `FEATURE_VERSION` is
  asserted at load today; production needs the same assertion in CI, at deploy time,
  and against the feature store, so a training/serving skew fails a pipeline rather
  than a customer.
- **Drift monitoring.** Feature-distribution and prediction-distribution drift
  detection (e.g. population stability index), with alerting thresholds tied to a
  retraining trigger — for pair features, not only customer features.
- **Champion/challenger deployment.** New recommender versions shadow-ranked against
  the current production model on live traffic before promotion, compared on ranking
  and business metrics, with an automated rollback path that can roll back the model
  without rolling back the application.

## Catalogue and coverage

- **Catalogue coverage as an operational metric.** The coverage funnel is per-request
  today. Production needs it aggregated: which products never survive eligibility,
  which never get recommended, which customer segments routinely reach
  `NO_SUITABLE_LOAN`. A persistent mismatch cluster is a product-gap signal for the
  lending team, not a modelling problem.
- **Catalogue freshness and provenance.** Real rates, fees and eligibility criteria
  change constantly. Production needs sourced, dated, versioned product data with an
  update pipeline, and every decision trace must record the catalogue version it saw.
- **Lender-neutrality controls.** Once real lenders are involved, ranking becomes
  commercially sensitive. Any commercial arrangement that influences ordering must be
  disclosed and separately auditable, and the recommender must be testable for
  lender bias independent of customer fit.

## Decisioning and compliance

- **Immutable decision logging.** Every eligibility rejection, every
  `NO_SUITABLE_LOAN` outcome and every recommendation logged immutably with the
  exact reason codes, threshold values, model versions, calibrated suitability
  scores and the full validation walk in effect at that moment — required for
  adverse-action notices under lending regulation (e.g. ECOA/Reg B in the US, or
  local equivalents), and incompatible with the current in-memory, non-persisted
  design.
- **Adverse-action reasons from an ML recommender.** This is materially harder than
  in v1.0. A deterministic rejection has a rule; a low suitability score does not.
  Production needs a defensible mapping from recommender behaviour to
  customer-facing reasons — likely: hard-rule reasons stated as rules, and
  model-driven "not suitable" outcomes explained through XAI contributions with
  legal review of the wording. The distinction between "you are ineligible" and
  "you qualify but this is a poor fit for you" must survive that review.
- **Policy versioning.** `CONFIG_VERSION` and `FEATURE_VERSION` are already stamped
  into every decision trace; production needs a full changelog of every
  threshold/weight/cap change, who approved it, and when it took effect, queryable
  against historical decisions.
- **Human review path.** A route for a customer to contest a recommendation or a
  `NO_SUITABLE_LOAN` outcome, with the trace legible to the reviewer, plus a
  documented override mechanism that is itself logged.
- **Compliance review of the liquidation-recommendation boundary.** Recommending
  that a customer liquidate investments to fund a loan sits close to investment
  advice, which is separately regulated in most jurisdictions. A *learned*
  recommendation to liquidate is harder to defend than a rule-based one. This needs
  formal legal/compliance review before going live — the current "decision support,
  not advice" framing is a design intent, not a compliance determination.
- **LLM output governance.** The numeric- and entity-grounding guards are the last
  line before a customer reads a sentence. Production needs monitoring of both the
  `UNGROUNDED` rejection rate and the `UNVERIFIED` rate — a rising `UNVERIFIED` rate
  means the normalizer is falling behind the model's phrasing and is the early warning
  that precedes someone proposing to disable the guard. The corpus is a living
  artefact: every production `UNVERIFIED` token is triaged and, where legitimate,
  becomes a new labelled case. Add sampled human review of generated explanations,
  prompt-version change control, and an incident path for a guard failure.

## Data protection and personalization

- **PII handling.** The personalization store persists pseudonymous behavioural data,
  which is a material change from the stateless v1.0 pipeline. Production needs
  encryption at rest and in transit, access controls, a retention policy, and a
  right-to-erasure path that also removes the affected rows from training corpora
  and documents the model-retraining consequence — deleting a user's rows does not
  remove their influence from an already-trained model.
- **Consent for personalization.** Behavioural personalization needs explicit,
  revocable consent, and the pipeline must remain fully functional when it is
  refused — the cold-start path is the compliance mechanism, not just an edge case.
- **Re-identification risk.** Derived affinity features plus financial profile can
  re-identify individuals. Needs a privacy review, and k-anonymity or aggregation
  thresholds on any exported analytics.

## Operational

- Rate limiting and authentication on the API (currently open, per the demo scope).
- A real database instead of the current SQLite/CSV-catalogue design, with
  migrations and backups.
- Structured application monitoring and alerting beyond basic logging, including
  fallback-rate alerting: a rising `DETERMINISTIC_FALLBACK` rate means customers are
  silently receiving a different, non-ML product experience and must page someone.
- Memory headroom for two model artifacts, the calibrator and contribution
  computation; the free-tier
  ceiling documented in `DEPLOY.md` is a demo constraint, not a production budget.
- Latency budgets for candidate generation and batch scoring as the catalogue grows —
  candidate count scales with products × amounts × tenures × strategies, and the
  per-product cap is currently the only bound.
