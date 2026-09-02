// Mirror app/schemas/pipeline.py.
import type {
  CandidateOutcome,
  EligibilityStatus,
  FinancingStrategy,
  MismatchReasonCode,
} from "./enums";

export interface EligibilityResult {
  product_id: string;
  status: EligibilityStatus;
  reason_code?: MismatchReasonCode | null;
  observed_value?: number | null;
  threshold_value?: number | null;
}

export interface Candidate {
  candidate_id: string;
  product_id?: string | null;
  lender?: string | null;
  tenure_months?: number | null;
  strategy: FinancingStrategy;
  required_amount: number;
  loan_amount: number;
  emi: number;
  total_interest: number;
  total_repayment: number;
  liquidation_amount: number;
  volatile_liquidation_amount: number;
  remaining_portfolio_value: number;
  resulting_liquidity_ratio: number;
  resulting_debt_burden_ratio: number;
  affordability_headroom: number;
  feasible: boolean;
  infeasibility_reason?: MismatchReasonCode | null;
}

export interface CandidateGenerationCounts {
  generated: number;
  infeasible: number;
  dominance_pruned: number;
  capped: number;
  surviving: number;
}

export interface ScoredCandidate {
  candidate: Candidate;
  raw_ranker_margin?: number | null;
  suitability?: number | null;
  rank: number;
}

export interface ScoringResult {
  scored_candidates: ScoredCandidate[];
  source: "ML_RANKER" | "DETERMINISTIC_FALLBACK";
}

export interface ValidationResult {
  passed: boolean;
  failed_check?: string | null;
  expected_value?: number | null;
  observed_value?: number | null;
}

export interface GuardrailResult {
  allowed: boolean;
  violated_rule?: string | null;
  reason_code?: MismatchReasonCode | null;
  cap_value?: number | null;
  observed_value?: number | null;
}

export interface ValidationWalkStep {
  rank: number;
  candidate_id: string;
  suitability?: number | null;
  validation: ValidationResult;
  guardrail: GuardrailResult;
  outcome: CandidateOutcome;
}