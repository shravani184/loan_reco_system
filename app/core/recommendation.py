"""
The Recommendation Orchestrator (P12).

IT ASSEMBLES A RECOMMENDATION; IT DOES NOT CHOOSE ONE. There is no scoring formula in
this module and none may be added. In v1.0 this module made the decision; in v2.0 it
RECORDS one (CONTEXT.md non-negotiable 8). If you find yourself writing a weighted
score here that reorders candidates, you have rebuilt the architecture this redesign
removed.

What it does:
  - runs the pipeline in the fixed order
  - WALKS the ML ranking, in the model's own order, stopping at the first candidate
    that survives validation and guardrails and clears the suitability threshold
  - assembles the result, the alternatives, the coverage funnel and the full trace

What it must never do:
  - reorder, re-score, or re-sort anything
  - manufacture a recommendation to avoid saying NO_SUITABLE_LOAN
  - silently swap a blocked top choice for a safer one. The block is SURFACED
    (CONTEXT.md section 9)
"""

import logging

from app.config import settings
from app.core.candidates import generate_candidates
from app.core.diagnostics import diagnostic_utility_score
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.guardrails import check_guardrails
from app.core.mismatch import analyze_mismatch
from app.core.portfolio import analyze_portfolio
from app.core.validation import validate_candidate
from app.ml.recommender import score_candidates
from app.ml.risk import predict_risk
from app.personalization.context import get_personalization_context
from app.schemas import (
    BlockedTopChoice,
    Candidate,
    CustomerProfile,
    DecisionTrace,
    LoanProduct,
    LoanRequirement,
    Portfolio,
    Recommendation,
    ScoredCandidate,
    ValidationWalkStep,
)
from app.schemas.enums import (
    CandidateOutcome,
    EligibilityStatus,
    RecommendationSource,
    RecommendationStatus,
)

logger = logging.getLogger(__name__)


def _walk(
    scored: list[ScoredCandidate],
    products_by_id: dict[str, LoanProduct],
    financial_metrics,
    portfolio_metrics,
    requirement: LoanRequirement,
    apply_suitability_threshold: bool,
) -> tuple[list[ValidationWalkStep], ScoredCandidate | None, str]:
    """
    Walk the ML ranking IN ITS OWN ORDER and return (walk log, winner, stop reason).

    The walk never reorders. It only answers, for each candidate in turn, whether it
    may be recommended — and stops at the first that may.

    `apply_suitability_threshold` is False in DETERMINISTIC_FALLBACK mode, where there
    is no calibrated suitability to compare. See the note in recommend().
    """
    threshold = settings.SUITABILITY_ACCEPTANCE_THRESHOLD
    walk: list[ValidationWalkStep] = []

    for item in scored:
        candidate = item.candidate

        # The list is in descending suitability, so the first candidate below the
        # threshold means every remaining one is too. Stopping here is not a
        # judgement about the candidate; it is arithmetic about the rest of the list.
        if (
            apply_suitability_threshold
            and item.suitability is not None
            and item.suitability < threshold
        ):
            return (
                walk,
                None,
                f"walk stopped at rank {item.rank}: suitability "
                f"{item.suitability:.4f} is below the acceptance threshold "
                f"{threshold:.4f}, and the list is in descending order",
            )

        product = (
            products_by_id.get(candidate.product_id) if candidate.product_id else None
        )
        validation = validate_candidate(
            candidate, product, financial_metrics, portfolio_metrics
        )
        if not validation.passed:
            logger.error(
                "DEFECT SIGNAL: candidate %s failed deterministic validation on %s "
                "(expected %s, observed %s)",
                candidate.candidate_id,
                validation.failed_check,
                validation.expected_value,
                validation.observed_value,
            )
            guardrail = check_guardrails(
                requirement.risk_appetite, financial_metrics, portfolio_metrics, candidate
            )
            walk.append(
                ValidationWalkStep(
                    rank=item.rank,
                    candidate_id=candidate.candidate_id,
                    suitability=item.suitability,
                    validation=validation,
                    guardrail=guardrail,
                    outcome=CandidateOutcome.INFEASIBLE,
                )
            )
            continue

        guardrail = check_guardrails(
            requirement.risk_appetite, financial_metrics, portfolio_metrics, candidate
        )
        if not guardrail.allowed:
            walk.append(
                ValidationWalkStep(
                    rank=item.rank,
                    candidate_id=candidate.candidate_id,
                    suitability=item.suitability,
                    validation=validation,
                    guardrail=guardrail,
                    outcome=CandidateOutcome.GUARDRAIL_BLOCKED,
                )
            )
            continue

        walk.append(
            ValidationWalkStep(
                rank=item.rank,
                candidate_id=candidate.candidate_id,
                suitability=item.suitability,
                validation=validation,
                guardrail=guardrail,
                outcome=CandidateOutcome.RECOMMENDED,
            )
        )
        return (
            walk,
            item,
            f"selected at rank {item.rank}: the highest-ranked candidate that passed "
            "deterministic validation and every guardrail",
        )

    return (
        walk,
        None,
        "walk exhausted the ranked list without finding a candidate that passed "
        "validation and guardrails",
    )


def _blocked_top_choice(
    scored: list[ScoredCandidate], walk: list[ValidationWalkStep]
) -> BlockedTopChoice | None:
    """
    The model's rank-1 pick, when a deterministic rule rejected it.

    SURFACED, NEVER SILENTLY SWAPPED. "The model's best match for you was X, but it
    exceeds your conservative profile, so we recommend Y" is a signature behaviour of
    this product, not an implementation detail (CONTEXT.md section 4).
    """
    if not scored or not walk:
        return None
    first = walk[0]
    if first.rank != 1 or first.outcome is CandidateOutcome.RECOMMENDED:
        return None

    top = scored[0]
    if not first.guardrail.allowed:
        return BlockedTopChoice(
            candidate=top.candidate,
            suitability=top.suitability,
            blocking_rule=first.guardrail.violated_rule,
            reason_code=first.guardrail.reason_code,
            cap_value=first.guardrail.cap_value,
            observed_value=first.guardrail.observed_value,
        )
    if not first.validation.passed:
        from app.schemas.enums import MismatchReasonCode

        return BlockedTopChoice(
            candidate=top.candidate,
            suitability=top.suitability,
            blocking_rule=f"validation:{first.validation.failed_check}",
            reason_code=MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY,
            cap_value=first.validation.expected_value,
            observed_value=first.validation.observed_value,
        )
    return None


def _resolve_status(
    eligible_products: list[LoanProduct],
    candidates: list[Candidate],
    scored: list[ScoredCandidate],
    walk: list[ValidationWalkStep],
    winner: ScoredCandidate | None,
) -> RecommendationStatus:
    """
    The four stop points are DIFFERENT ANSWERS to "how far did my request get", and
    collapsing them is a defect (CONTEXT.md 7.1). Resolved in pipeline order, so the
    earliest genuine stopping point wins.
    """
    if winner is not None:
        return RecommendationStatus.RECOMMENDED
    if not eligible_products:
        return RecommendationStatus.NO_ELIGIBLE_PRODUCTS
    if not any(candidate.feasible for candidate in candidates):
        return RecommendationStatus.NO_FEASIBLE_CANDIDATES
    # Every candidate the walk actually reached was blocked by a guardrail, and none
    # failed for suitability. That is a policy outcome, not an unsuitability one.
    if walk and all(
        step.outcome is CandidateOutcome.GUARDRAIL_BLOCKED for step in walk
    ):
        return RecommendationStatus.ALL_CANDIDATES_BLOCKED
    return RecommendationStatus.NO_SUITABLE_LOAN


def recommend(
    customer: CustomerProfile,
    portfolio: Portfolio | None,
    requirement: LoanRequirement,
    catalogue: list[LoanProduct],
    user_id: str | None = None,
    personalization_store=None,
) -> Recommendation:
    """
    Run the whole pipeline and assemble the result.

    Fixed order (CONTEXT.md section 3):
        financial -> portfolio -> personalization -> eligibility
          -> candidate generation -> risk -> ML scoring -> validation/guardrail walk
          -> assembly
    """
    financial_metrics = analyze_financials(customer)
    portfolio_metrics = analyze_portfolio(portfolio)
    personalization = get_personalization_context(
        user_id, store=personalization_store
    )

    eligibility_results = check_eligibility(
        customer, financial_metrics, requirement, catalogue
    )
    eligible_ids = {
        result.product_id
        for result in eligibility_results
        if result.status is EligibilityStatus.ELIGIBLE
    }
    eligible_products = [p for p in catalogue if p.product_id in eligible_ids]
    products_by_id = {product.product_id: product for product in catalogue}

    generation = generate_candidates(
        requirement, financial_metrics, portfolio_metrics, eligible_products
    )
    feasible_candidates = [c for c in generation.candidates if c.feasible]

    risk = predict_risk(customer, financial_metrics, portfolio_metrics, requirement)

    scoring = score_candidates(
        customer,
        financial_metrics,
        portfolio_metrics,
        personalization,
        requirement,
        products_by_id,
        feasible_candidates,
        risk.probability_of_default,
    )
    scored = scoring.scored_candidates

    # IN FALLBACK MODE THERE IS NO CALIBRATED SUITABILITY, so the acceptance threshold
    # cannot be applied — a None suitability is not "below" anything, and comparing a
    # rescaled diagnostic score against a threshold calibrated for the ML model would
    # be meaningless. The walk therefore runs on validation and guardrails alone, and
    # NO_SUITABLE_LOAN is consequently unreachable in fallback: without a learned
    # suitability the system has no basis to call an option unsuitable, only
    # impossible or impermissible.
    apply_threshold = scoring.source is RecommendationSource.ML_RANKER

    walk, winner, stop_reason = _walk(
        scored,
        products_by_id,
        financial_metrics,
        portfolio_metrics,
        requirement,
        apply_threshold,
    )

    status = _resolve_status(
        eligible_products, generation.candidates, scored, walk, winner
    )
    blocked_top_choice = _blocked_top_choice(scored, walk)

    # ALTERNATIVES ARE THE NEXT CANDIDATES IN THE MODEL'S OWN RANKING that also pass
    # validation and guardrails. They are never re-sorted by cost, EMI or any
    # deterministic score (CONTEXT.md section 4).
    alternatives: list[ScoredCandidate] = []
    if winner is not None:
        for item in scored:
            if len(alternatives) >= settings.MAX_ALTERNATIVES_RETURNED:
                break
            if item.rank <= winner.rank:
                continue
            if apply_threshold and (
                item.suitability is None
                or item.suitability < settings.SUITABILITY_ACCEPTANCE_THRESHOLD
            ):
                break
            product = (
                products_by_id.get(item.candidate.product_id)
                if item.candidate.product_id
                else None
            )
            if not validate_candidate(
                item.candidate, product, financial_metrics, portfolio_metrics
            ).passed:
                continue
            if not check_guardrails(
                requirement.risk_appetite,
                financial_metrics,
                portfolio_metrics,
                item.candidate,
            ).allowed:
                continue
            alternatives.append(item)

    reasons, coverage = analyze_mismatch(
        eligibility_results, generation.candidates, scored, walk
    )
    coverage = coverage.model_copy(
        update={"candidates_dominance_pruned": generation.counts.dominance_pruned}
    )

    # ADVISORY ONLY. Recorded in the trace so the ML and deterministic views can be
    # compared offline. It orders nothing here (CONTEXT.md section 4).
    winner_diagnostic = (
        diagnostic_utility_score(
            financial_metrics,
            portfolio_metrics,
            winner.candidate,
            risk.probability_of_default,
        )
        if winner is not None
        else None
    )

    trace = DecisionTrace(
        user_id=user_id,
        financial_metrics=financial_metrics,
        portfolio_metrics=portfolio_metrics,
        personalization=personalization,
        eligibility=eligibility_results,
        candidate_counts=generation.counts,
        risk=risk,
        ranked_candidates=scored,
        validation_walk=walk,
        ml_top_choice_blocked=blocked_top_choice,
        selected_candidate_id=winner.candidate.candidate_id if winner else None,
        selection_stop_reason=stop_reason,
        winner_diagnostic_utility_score=winner_diagnostic,
        coverage=coverage,
        recommendation_status=status,
        recommendation_source=scoring.source,
        config_version=settings.CONFIG_VERSION,
        feature_version=settings.FEATURE_VERSION,
        prompt_version=settings.PROMPT_VERSION,
        labeling_policy_version=settings.LABELING_POLICY_VERSION,
        risk_model_version=risk.model_version,
        recommender_model_version=settings.RECOMMENDER_MODEL_VERSION,
    )

    return Recommendation(
        status=status,
        source=scoring.source,
        selected_candidate=winner.candidate if winner else None,
        # Null under DETERMINISTIC_FALLBACK by construction: the fallback carries no
        # suitability, and the schema rejects a non-null value there anyway.
        ml_suitability=winner.suitability if winner else None,
        alternatives=alternatives,
        ml_top_choice_blocked=blocked_top_choice,
        mismatch_reasons=reasons,
        risk=risk,
        coverage=coverage,
        decision_trace=trace,
    )
