// Mirror app/schemas/recommendation.py (Recommendation, DecisionTrace,
// BlockedTopChoice, MismatchReason, CatalogueCoverage) and app/schemas/explanation.py.
import type {
  FinancialMetrics,
  PersonalizationContext,
  PortfolioMetrics,
  RiskPrediction,
} from "./metrics";
import type {
  Candidate,
  CandidateGenerationCounts,
  EligibilityResult,
  ScoredCandidate,
  ValidationWalkStep,
} from "./pipeline";
import type {
  ExplanationSource,
  GroundingOutcome,
  MismatchReasonCode,
  RecommendationSource,
  RecommendationStatus,
  XaiMethod,
} from "./enums";

export interface CatalogueCoverage {
  catalogue_products: number;
  products_passing_eligibility: number;
  products_with_feasible_candidates: number;
  candidates_generated: number;
  candidates_infeasible: number;
  candidates_dominance_pruned: number;
  candidates_scored: number;
  candidates_above_suitability_threshold: number;
  candidates_passing_validation: number;
  candidates_passing_guardrails: number;
}

export interface MismatchReason {
  code: MismatchReasonCode;
  observed_value: number;
  threshold_value: number;
  product_id?: string | null;
  candidate_id?: string | null;
}

export interface BlockedTopChoice {
  candidate: Candidate;
  suitability?: number | null;
  blocking_rule: string;
  reason_code: MismatchReasonCode;
  cap_value?: number | null;
  observed_value?: number | null;
}

export interface DecisionTrace {
  user_id?: string | null;
  financial_metrics: FinancialMetrics;
  portfolio_metrics: PortfolioMetrics;
  personalization: PersonalizationContext;
  eligibility: EligibilityResult[];
  candidate_counts: CandidateGenerationCounts;
  risk: RiskPrediction;
  ranked_candidates: ScoredCandidate[];
  validation_walk: ValidationWalkStep[];
  ml_top_choice_blocked?: BlockedTopChoice | null;
  selected_candidate_id?: string | null;
  selection_stop_reason: string;
  winner_diagnostic_utility_score?: number | null;
  coverage: CatalogueCoverage;
  recommendation_status: RecommendationStatus;
  recommendation_source: RecommendationSource;
  config_version: string;
  feature_version: string;
  prompt_version: string;
  labeling_policy_version: string;
  risk_model_version: string;
  recommender_model_version: string;
}

export interface Recommendation {
  status: RecommendationStatus;
  source: RecommendationSource;
  selected_candidate?: Candidate | null;
  ml_suitability?: number | null;
  alternatives: ScoredCandidate[];
  ml_top_choice_blocked?: BlockedTopChoice | null;
  mismatch_reasons: MismatchReason[];
  risk?: RiskPrediction | null;
  coverage: CatalogueCoverage;
  decision_trace: DecisionTrace;
}

// ---- Explanation (app/schemas/explanation.py) ----

export interface FeatureContribution {
  feature: string;
  value: number;
  contribution: number;
}

export interface FeatureContrast {
  feature: string;
  winner_value: number;
  runner_up_value: number;
  winner_contribution: number;
  runner_up_contribution: number;
  delta: number;
}

export interface XaiExplanation {
  candidate_id: string;
  method: XaiMethod;
  degraded: boolean;
  base_value?: number | null;
  contributions: FeatureContribution[];
  contrast: FeatureContrast[];
  runner_up_candidate_id?: string | null;
  note?: string | null;
}

export interface GroundingFinding {
  text: string;
  outcome: GroundingOutcome;
  interpretations: number[];
  note?: string;
}

export interface GroundingCheck {
  outcome: GroundingOutcome;
  findings: GroundingFinding[];
}

export interface Explanation {
  text: string;
  source: ExplanationSource;
  prompt_version: string;
  numeric_grounding?: GroundingCheck | null;
  entity_grounding?: GroundingCheck | null;
  unverified_tokens: string[];
  degraded_reason?: string | null;
}

export interface ExplanationResponse {
  explanation: Explanation;
  xai: XaiExplanation;
}

export interface CoverageResponse {
  recommendation_status: RecommendationStatus;
  recommendation_source: RecommendationSource;
  coverage: CatalogueCoverage;
}

export interface HealthResponse {
  status: string;
  ml: {
    recommender_loaded: boolean;
    risk_loaded: boolean;
    recommender_source: RecommendationSource;
  };
  catalogue_products: number;
}

export interface DeletePersonalizationResponse {
  user_id: string;
  rows_removed: number;
}