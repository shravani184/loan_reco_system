"""
Pipeline-stage results: eligibility, candidates, scoring, validation, guardrails.

Ownership (AGENTS.md section 2):
  EligibilityResult -> app/core/eligibility.py (P4)
  Candidate         -> app/core/candidates.py  (P5)
  ScoredCandidate   -> app/ml/recommender.py   (P10/P11)
  ValidationResult  -> app/core/validation.py  (P12)
  GuardrailResult   -> app/core/guardrails.py  (P6)
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.enums import (
    CandidateOutcome,
    EligibilityStatus,
    FinancingStrategy,
    MismatchReasonCode,
    RecommendationSource,
)


class EligibilityResult(BaseModel):
    """
    One per catalogue product, ALWAYS. The eligibility engine never silently drops a
    product: an ineligible product appears here with its reason code
    (CONTEXT.md section 4).
    """

    model_config = ConfigDict(extra="forbid")

    product_id: str
    status: EligibilityStatus
    reason_code: MismatchReasonCode | None = None
    observed_value: float | None = None
    threshold_value: float | None = None

    @model_validator(mode="after")
    def _reason_required_when_ineligible(self) -> "EligibilityResult":
        if self.status is EligibilityStatus.INELIGIBLE and self.reason_code is None:
            raise ValueError("an INELIGIBLE product must carry a reason_code")
        if self.status is EligibilityStatus.ELIGIBLE and self.reason_code is not None:
            raise ValueError("an ELIGIBLE product must not carry a reason_code")
        return self


class Candidate(BaseModel):
    """
    A FULLY SPECIFIED financing configuration — not a product id.

    The recommender scores these. Reducing a Candidate to a product reference is an
    architectural regression (AGENTS.md section 3).

    THE NO-LOAN CANDIDATE (Phase R finding, adopted here):
      LIQUIDATE_100 borrows nothing, so product_id, lender and tenure_months are
      meaningless for it and are None. It means "pay from your assets, borrow
      nothing" — it must never be rendered as a 1-month loan. Every other strategy
      borrows, so all three fields are required.

    Infeasible candidates are MARKED, never deleted (CONTEXT.md section 4).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str

    # None for the LIQUIDATE_100 no-loan candidate; required otherwise.
    product_id: str | None = None
    lender: str | None = None
    tenure_months: int | None = Field(default=None, gt=0)

    strategy: FinancingStrategy
    required_amount: float = Field(ge=0.0)
    loan_amount: float = Field(ge=0.0)

    # Computed by app/core/finance_math.py — the only EMI implementation (P5).
    emi: float = Field(ge=0.0)
    total_interest: float = Field(ge=0.0)
    total_repayment: float = Field(ge=0.0)

    liquidation_amount: float = Field(ge=0.0)
    volatile_liquidation_amount: float = Field(ge=0.0)
    remaining_portfolio_value: float = Field(ge=0.0)
    resulting_liquidity_ratio: float = Field(ge=0.0, le=1.0)
    resulting_debt_burden_ratio: float = Field(ge=0.0)
    affordability_headroom: float

    feasible: bool = True
    infeasibility_reason: MismatchReasonCode | None = None

    @model_validator(mode="after")
    def _shape(self) -> "Candidate":
        borrows = self.strategy is not FinancingStrategy.LIQUIDATE_100
        if borrows:
            missing = [
                name
                for name in ("product_id", "lender", "tenure_months")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    f"a borrowing candidate requires {', '.join(missing)}"
                )
        else:
            if self.loan_amount != 0.0:
                raise ValueError("LIQUIDATE_100 must borrow nothing")
            present = [
                name
                for name in ("product_id", "lender", "tenure_months")
                if getattr(self, name) is not None
            ]
            if present:
                raise ValueError(
                    "LIQUIDATE_100 borrows nothing, so it carries no "
                    f"{', '.join(present)} — it is not a 1-month loan"
                )
        if self.feasible and self.infeasibility_reason is not None:
            raise ValueError("a feasible candidate must not carry an infeasibility_reason")
        if not self.feasible and self.infeasibility_reason is None:
            raise ValueError("an infeasible candidate must carry an infeasibility_reason")
        return self


class CandidateGenerationCounts(BaseModel):
    """
    What candidate generation did (P5), for the coverage funnel and the trace.

    dominance_pruned and capped candidates are NOT in the returned list, so these
    counts are the only record that they existed. That is why generation returns
    them alongside the candidates rather than leaving them to be re-derived.
    """

    model_config = ConfigDict(extra="forbid")

    generated: int = Field(ge=0)
    infeasible: int = Field(ge=0)
    dominance_pruned: int = Field(ge=0)
    capped: int = Field(ge=0)
    surviving: int = Field(ge=0)


class CandidateGenerationResult(BaseModel):
    """
    The output of app/core/candidates.py.

    `candidates` holds the surviving feasible candidates PLUS every infeasible one,
    marked — infeasible candidates are never deleted (CONTEXT.md section 4). The
    ordering is enumeration order and carries NO preference: this module generates
    the option space, it does not have an opinion about it.
    """

    model_config = ConfigDict(extra="forbid")

    candidates: list[Candidate] = Field(default_factory=list)
    counts: CandidateGenerationCounts


class ScoredCandidate(BaseModel):
    """
    Produced by the primary recommender (P11).

    `suitability` is the CALIBRATED [0,1] value and is the only thing ever compared
    against SUITABILITY_ACCEPTANCE_THRESHOLD. The raw margin is unbounded and is
    carried for audit only (CONTEXT.md 6.4).

    In DETERMINISTIC_FALLBACK mode `suitability` and `raw_ranker_margin` are None —
    never a rescaled diagnostic score (AGENTS.md section 7.3).
    """

    model_config = ConfigDict(extra="forbid")

    candidate: Candidate
    raw_ranker_margin: float | None = None
    suitability: float | None = Field(default=None, ge=0.0, le=1.0)
    rank: int = Field(ge=1)


class ScoringResult(BaseModel):
    """
    The output of app/ml/recommender.py (P11).

    The SOURCE travels with the scored list rather than sitting in module state that a
    caller has to remember to query. Under concurrency a queryable global would let one
    request's fallback be reported against another request's result, and
    "never present a deterministic fallback as an ML recommendation" (CONTEXT.md 5.3)
    is exactly the property that must not depend on call ordering.

    Under DETERMINISTIC_FALLBACK every ScoredCandidate carries suitability = None.
    """

    model_config = ConfigDict(extra="forbid")

    scored_candidates: list["ScoredCandidate"] = Field(default_factory=list)
    source: RecommendationSource

    @model_validator(mode="after")
    def _fallback_carries_no_suitability(self) -> "ScoringResult":
        if self.source is RecommendationSource.DETERMINISTIC_FALLBACK:
            if any(item.suitability is not None for item in self.scored_candidates):
                raise ValueError(
                    "DETERMINISTIC_FALLBACK must not carry a calibrated suitability — "
                    "never emit a rescaled diagnostic score in an ML field"
                )
        return self


class ValidationResult(BaseModel):
    """
    Deterministic re-verification of a single candidate (P12). Pass/fail only —
    it never corrects the candidate and never re-ranks.
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    failed_check: str | None = None
    expected_value: float | None = None
    observed_value: float | None = None

    @model_validator(mode="after")
    def _detail_required_on_failure(self) -> "ValidationResult":
        if not self.passed and not self.failed_check:
            raise ValueError("a failed validation must name the failed check")
        if self.passed and self.failed_check:
            raise ValueError("a passed validation must not name a failed check")
        return self


class GuardrailResult(BaseModel):
    """
    Policy pass/fail over a single candidate (P6), applied AFTER the recommender.
    It never deletes an option and never reorders.
    """

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    violated_rule: str | None = None
    reason_code: MismatchReasonCode | None = None
    cap_value: float | None = None
    observed_value: float | None = None

    @model_validator(mode="after")
    def _detail_required_on_block(self) -> "GuardrailResult":
        if not self.allowed and (self.violated_rule is None or self.reason_code is None):
            raise ValueError("a blocked candidate must name the rule and reason_code")
        if self.allowed and self.violated_rule is not None:
            raise ValueError("an allowed candidate must not name a violated rule")
        return self


class ValidationWalkStep(BaseModel):
    """
    One row of the validation walk, in ML rank order (AGENTS.md section 9). The walk
    is recorded in full, including the candidates that failed before the winner.
    """

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    candidate_id: str
    suitability: float | None = Field(default=None, ge=0.0, le=1.0)
    validation: ValidationResult
    guardrail: GuardrailResult
    outcome: CandidateOutcome
