"""Every data structure that crosses a module boundary (AGENTS.md section 3)."""

from app.schemas.customer import (
    CustomerProfile,
    Holding,
    LoanProduct,
    LoanRequirement,
    Portfolio,
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
    CandidateGenerationResult,
    EligibilityResult,
    GuardrailResult,
    ScoredCandidate,
    ScoringResult,
    ValidationResult,
    ValidationWalkStep,
)
from app.schemas.recommendation import (
    BlockedTopChoice,
    CatalogueCoverage,
    DecisionTrace,
    MismatchReason,
    Recommendation,
)

__all__ = [
    "BlockedTopChoice",
    "Candidate",
    "CandidateGenerationCounts",
    "CandidateGenerationResult",
    "CatalogueCoverage",
    "CustomerProfile",
    "DecisionTrace",
    "EligibilityResult",
    "FinancialMetrics",
    "GuardrailResult",
    "Holding",
    "LoanProduct",
    "LoanRequirement",
    "MismatchReason",
    "PersonalizationContext",
    "Portfolio",
    "PortfolioMetrics",
    "Recommendation",
    "RiskPrediction",
    "ScoredCandidate",
    "ScoringResult",
    "ValidationResult",
    "ValidationWalkStep",
]
