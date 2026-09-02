"""
Catalogue mismatch analysis and the coverage funnel (P12).

WHY IT EXISTS. The system must be able to conclude that nothing in the catalogue is
right for this customer, and say WHY in terms they can act on. "Loan not recommended"
is a rejection; a funnel plus rule-sourced reasons is guidance (CONTEXT.md section 7).

IT NEVER INVENTS A REASON. Every MismatchReason returned here corresponds to a rule
evaluation that ACTUALLY FIRED or a score that was ACTUALLY COMPUTED, and carries the
observed value and the threshold it failed. Nothing is inferred, and nothing is
generated to fill a gap — if no rule fired, no reason is emitted.

The LLM renders these. It does not author them (CONTEXT.md non-negotiable 14).
"""

from app.config import settings
from app.schemas import (
    Candidate,
    CatalogueCoverage,
    EligibilityResult,
    MismatchReason,
    ScoredCandidate,
    ValidationWalkStep,
)
from app.schemas.enums import EligibilityStatus, MismatchReasonCode

# A candidate funding less than this share of the requirement has not met the need.
# Matches the labeling policy's disqualification floor, so training and serving agree
# about what "does not meet the need" means.
FULL_FUNDING_TOLERANCE = 0.995


def _funding_coverage(candidate: Candidate) -> float:
    if candidate.required_amount <= 0.0:
        return 1.0
    funded = candidate.loan_amount + candidate.liquidation_amount
    return funded / candidate.required_amount


def analyze_mismatch(
    eligibility_results: list[EligibilityResult],
    candidates: list[Candidate],
    scored_candidates: list[ScoredCandidate],
    walk_log: list[ValidationWalkStep],
) -> tuple[list[MismatchReason], CatalogueCoverage]:
    """
    Structured reasons plus the coverage funnel.

    Both are produced on EVERY response, successful or not (CONTEXT.md 7.3): the funnel
    is how a customer learns how far their request got, and that is as useful on a
    success as on a refusal.
    """
    reasons: list[MismatchReason] = []

    # --- eligibility: every product that failed a hard rule, with its own numbers.
    for result in eligibility_results:
        if result.status is not EligibilityStatus.INELIGIBLE:
            continue
        if result.reason_code is None:
            continue
        # PURPOSE_NOT_SUPPORTED is categorical and carries no numeric pair (P4). It is
        # still a real, fired rule, so it is reported with zeros rather than dropped —
        # dropping it would hide the commonest reason a product is unavailable.
        reasons.append(
            MismatchReason(
                code=result.reason_code,
                observed_value=result.observed_value
                if result.observed_value is not None
                else 0.0,
                threshold_value=result.threshold_value
                if result.threshold_value is not None
                else 0.0,
                product_id=result.product_id,
            )
        )

    # --- feasibility: candidates P5 marked infeasible, one reason per distinct cause
    #     per product, so a 60-candidate product does not emit 60 identical reasons.
    seen_infeasible: set[tuple[str | None, MismatchReasonCode]] = set()
    for candidate in candidates:
        if candidate.feasible or candidate.infeasibility_reason is None:
            continue
        key = (candidate.product_id, candidate.infeasibility_reason)
        if key in seen_infeasible:
            continue
        seen_infeasible.add(key)
        if candidate.infeasibility_reason is MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY:
            observed, threshold = candidate.emi, candidate.emi - candidate.affordability_headroom
        else:
            observed, threshold = (
                candidate.liquidation_amount,
                candidate.remaining_portfolio_value,
            )
        reasons.append(
            MismatchReason(
                code=candidate.infeasibility_reason,
                observed_value=observed,
                threshold_value=threshold,
                product_id=candidate.product_id,
                candidate_id=candidate.candidate_id,
            )
        )

    # --- the whole option space under-funds the request. This is a conclusion about
    #     the SET, not about any one candidate, which is why P5 left it here.
    feasible = [candidate for candidate in candidates if candidate.feasible]
    if feasible:
        best_coverage = max(_funding_coverage(c) for c in feasible)
        if best_coverage < FULL_FUNDING_TOLERANCE:
            best = max(feasible, key=_funding_coverage)
            reasons.append(
                MismatchReason(
                    code=MismatchReasonCode.REQUIRED_AMOUNT_UNREACHABLE,
                    observed_value=best.loan_amount + best.liquidation_amount,
                    threshold_value=best.required_amount,
                    product_id=best.product_id,
                    candidate_id=best.candidate_id,
                )
            )

    # --- guardrail blocks, taken from the walk that actually ran.
    seen_guardrail: set[tuple[str, MismatchReasonCode]] = set()
    for step in walk_log:
        guardrail = step.guardrail
        if guardrail.allowed or guardrail.reason_code is None:
            continue
        key = (step.candidate_id, guardrail.reason_code)
        if key in seen_guardrail:
            continue
        seen_guardrail.add(key)
        reasons.append(
            MismatchReason(
                code=guardrail.reason_code,
                observed_value=guardrail.observed_value
                if guardrail.observed_value is not None
                else 0.0,
                threshold_value=guardrail.cap_value
                if guardrail.cap_value is not None
                else 0.0,
                candidate_id=step.candidate_id,
            )
        )

    # --- suitability. Emitted only when a score was ACTUALLY COMPUTED: in fallback
    #     mode there is no calibrated suitability, so there is nothing to be below a
    #     threshold, and inventing one would be exactly the fabrication this module
    #     exists to prevent.
    threshold = settings.SUITABILITY_ACCEPTANCE_THRESHOLD
    scored_with_suitability = [
        item for item in scored_candidates if item.suitability is not None
    ]
    if scored_with_suitability:
        best = max(scored_with_suitability, key=lambda item: item.suitability)
        if best.suitability < threshold:
            reasons.append(
                MismatchReason(
                    code=MismatchReasonCode.SUITABILITY_BELOW_THRESHOLD,
                    observed_value=best.suitability,
                    threshold_value=threshold,
                    product_id=best.candidate.product_id,
                    candidate_id=best.candidate.candidate_id,
                )
            )

    coverage = build_coverage(
        eligibility_results, candidates, scored_candidates, walk_log
    )
    return reasons, coverage


def build_coverage(
    eligibility_results: list[EligibilityResult],
    candidates: list[Candidate],
    scored_candidates: list[ScoredCandidate],
    walk_log: list[ValidationWalkStep],
) -> CatalogueCoverage:
    """
    The funnel. Each stage is a count of what survived the one before it, so a reader
    can see exactly where a request stopped.
    """
    threshold = settings.SUITABILITY_ACCEPTANCE_THRESHOLD
    feasible = [candidate for candidate in candidates if candidate.feasible]

    eligible_ids = {
        result.product_id
        for result in eligibility_results
        if result.status is EligibilityStatus.ELIGIBLE
    }
    # The no-loan candidate has no product, so it is not attributed to one here — it
    # is counted in the candidate stages below, where it belongs.
    products_with_feasible = {
        candidate.product_id for candidate in feasible if candidate.product_id
    }

    above_threshold = sum(
        1
        for item in scored_candidates
        if item.suitability is not None and item.suitability >= threshold
    )

    return CatalogueCoverage(
        catalogue_products=len(eligibility_results),
        products_passing_eligibility=len(eligible_ids),
        products_with_feasible_candidates=len(products_with_feasible),
        candidates_generated=len(candidates),
        candidates_infeasible=len(candidates) - len(feasible),
        candidates_dominance_pruned=0,  # filled in by the orchestrator from P5's counts
        candidates_scored=len(scored_candidates),
        candidates_above_suitability_threshold=above_threshold,
        candidates_passing_validation=sum(
            1 for step in walk_log if step.validation.passed
        ),
        candidates_passing_guardrails=sum(
            1 for step in walk_log if step.validation.passed and step.guardrail.allowed
        ),
    )
