"""
The output contract: mismatch reasons, coverage funnel, decision trace, recommendation.

Owner: app/core/recommendation.py (P12) — which ASSEMBLES these. It contains no
formula that can reorder candidates (CONTEXT.md non-negotiable 8).
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.enums import (
    MismatchReasonCode,
    RecommendationSource,
    RecommendationStatus,
)
from app.schemas.metrics import (
    FinancialMetrics,
    PersonalizationContext,
    PortfolioMetrics,
    RiskPrediction,
)
from app.schemas.pipeline import (
    Candidate,
    CandidateGenerationCounts,
    EligibilityResult,
    ScoredCandidate,
    ValidationWalkStep,
)


class MismatchReason(BaseModel):
    """
    A structured, rule-sourced explanation of why something did not work.

    Every instance must correspond to a rule evaluation that ACTUALLY FIRED or a
    score that was ACTUALLY COMPUTED, and carries the observed value and the
    threshold it failed (CONTEXT.md 7.2). The LLM renders these; it never authors
    them.
    """

    model_config = ConfigDict(extra="forbid")

    code: MismatchReasonCode
    observed_value: float
    threshold_value: float
    product_id: str | None = None
    candidate_id: str | None = None


class BlockedTopChoice(BaseModel):
    """
    The model's first pick, when a deterministic rule blocked it.

    Recorded and SURFACED, never silently swapped — this is a signature behaviour of
    the product, not an implementation detail (CONTEXT.md section 9).
    """

    model_config = ConfigDict(extra="forbid")

    candidate: Candidate
    suitability: float | None = Field(default=None, ge=0.0, le=1.0)
    blocking_rule: str
    reason_code: MismatchReasonCode
    cap_value: float | None = None
    observed_value: float | None = None


class CatalogueCoverage(BaseModel):
    """
    The funnel (CONTEXT.md 7.3). Emitted on EVERY response, success or failure.
    """

    model_config = ConfigDict(extra="forbid")

    catalogue_products: int = Field(ge=0)
    products_passing_eligibility: int = Field(ge=0)
    products_with_feasible_candidates: int = Field(ge=0)
    candidates_generated: int = Field(ge=0)
    candidates_infeasible: int = Field(ge=0)
    candidates_dominance_pruned: int = Field(ge=0)
    candidates_scored: int = Field(ge=0)
    candidates_above_suitability_threshold: int = Field(ge=0)

    # Counted over the candidates the walk ACTUALLY ATTEMPTED. The walk stops at the
    # first candidate that passes everything, so these are not totals over the whole
    # ranked list — they say how far the walk got, which is the question the funnel
    # exists to answer.
    candidates_passing_validation: int = Field(default=0, ge=0)
    candidates_passing_guardrails: int = Field(default=0, ge=0)


class DecisionTrace(BaseModel):
    """
    Reconstructs the whole decision. Every element required by AGENTS.md section 9.

    Contains NO raw PII: the customer is identified by pseudonymous id only.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None

    financial_metrics: FinancialMetrics
    portfolio_metrics: PortfolioMetrics
    personalization: PersonalizationContext

    eligibility: list[EligibilityResult]
    candidate_counts: CandidateGenerationCounts
    risk: RiskPrediction

    # The full ML-ranked list with calibrated suitability, in the model's own order.
    ranked_candidates: list[ScoredCandidate]
    validation_walk: list[ValidationWalkStep]
    ml_top_choice_blocked: BlockedTopChoice | None = None

    selected_candidate_id: str | None = None
    selection_stop_reason: str

    # Advisory only. Recorded so ML and deterministic orderings can be compared
    # offline. It may never reorder anything during normal operation.
    winner_diagnostic_utility_score: float | None = None

    coverage: CatalogueCoverage
    recommendation_status: RecommendationStatus
    recommendation_source: RecommendationSource

    config_version: str
    feature_version: str
    prompt_version: str
    labeling_policy_version: str
    risk_model_version: str
    recommender_model_version: str


class Recommendation(BaseModel):
    """
    The top-level result.

    Constructible with NO selected candidate: NO_SUITABLE_LOAN and the three earlier
    stop points are first-class shapes, not errors (CONTEXT.md section 7).

    Status and source are SEPARATE AXES. A DETERMINISTIC_FALLBACK run can still be
    RECOMMENDED, and an ML_RANKER run can still be NO_SUITABLE_LOAN.
    """

    model_config = ConfigDict(extra="forbid")

    status: RecommendationStatus
    source: RecommendationSource

    selected_candidate: Candidate | None = None
    ml_suitability: float | None = Field(default=None, ge=0.0, le=1.0)

    # Next candidates in the MODEL'S OWN ranking that also passed validation and
    # guardrails. Never re-sorted by cost, EMI or any deterministic score.
    alternatives: list[ScoredCandidate] = Field(default_factory=list)

    ml_top_choice_blocked: BlockedTopChoice | None = None
    mismatch_reasons: list[MismatchReason] = Field(default_factory=list)

    risk: RiskPrediction | None = None
    coverage: CatalogueCoverage
    decision_trace: DecisionTrace

    @model_validator(mode="after")
    def _status_matches_shape(self) -> "Recommendation":
        recommended = self.status is RecommendationStatus.RECOMMENDED
        if recommended and self.selected_candidate is None:
            raise ValueError("RECOMMENDED requires a selected_candidate")
        if not recommended and self.selected_candidate is not None:
            raise ValueError(
                f"{self.status.value} must not carry a selected_candidate — "
                "never manufacture a recommendation"
            )
        # In fallback mode the ML suitability field is null, not a rescaled
        # diagnostic score (AGENTS.md section 7.3).
        if (
            self.source is RecommendationSource.DETERMINISTIC_FALLBACK
            and self.ml_suitability is not None
        ):
            raise ValueError(
                "ml_suitability must be null under DETERMINISTIC_FALLBACK"
            )
        return self
