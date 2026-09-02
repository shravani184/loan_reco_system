// Mirror app/schemas/api.py (RecommendRequest, ExplanationRequest).
import type { CustomerProfile, LoanRequirement, Portfolio } from "./customer";

export interface RecommendRequest {
  customer: CustomerProfile;
  requirement: LoanRequirement;
  portfolio?: Portfolio | null;
  user_id?: string | null;
}

export interface ExplanationRequest extends RecommendRequest {
  question?: string | null;
}