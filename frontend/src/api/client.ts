import axios from "axios";
import type {
  CoverageResponse,
  DeletePersonalizationResponse,
  EligibilityResult,
  ExplanationResponse,
  FinancialMetrics,
  HealthResponse,
  LoanProduct,
  PortfolioMetrics,
  Recommendation,
  RiskPrediction,
} from "../types";
import type { CustomerProfile, Portfolio } from "../types/customer";
import type {
  ExplanationRequest,
  RecommendRequest,
} from "../types/requests";

const baseURL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

export function recommend(payload: RecommendRequest): Promise<Recommendation> {
  return api.post<Recommendation>("/recommend", payload).then((r) => r.data);
}

export function runScenario(
  payload: RecommendRequest,
): Promise<Recommendation> {
  return api.post<Recommendation>("/scenario", payload).then((r) => r.data);
}

export function explain(
  payload: ExplanationRequest,
): Promise<ExplanationResponse> {
  return api.post<ExplanationResponse>("/explanation", payload).then(
    (r) => r.data,
  );
}

export function getCoverage(
  payload: RecommendRequest,
): Promise<CoverageResponse> {
  // Backend exposes /coverage as a GET with the request in the body.
  return api
    .get<CoverageResponse>("/coverage", { data: payload })
    .then((r) => r.data);
}

export function getLoanProducts(): Promise<LoanProduct[]> {
  return api.get<LoanProduct[]>("/loan-products").then((r) => r.data);
}

export function getHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>("/health").then((r) => r.data);
}

export function financialHealth(
  customer: CustomerProfile,
): Promise<FinancialMetrics> {
  return api.post<FinancialMetrics>("/financial-health", customer).then(
    (r) => r.data,
  );
}

export function portfolioAnalysis(
  portfolio: Portfolio,
): Promise<PortfolioMetrics> {
  return api
    .post<PortfolioMetrics>("/portfolio-analysis", portfolio)
    .then((r) => r.data);
}

export function riskPrediction(
  payload: RecommendRequest,
): Promise<RiskPrediction> {
  return api
    .post<RiskPrediction>("/risk-prediction", payload)
    .then((r) => r.data);
}

export function eligibility(
  payload: RecommendRequest,
): Promise<EligibilityResult[]> {
  return api.post<EligibilityResult[]>("/eligibility", payload).then(
    (r) => r.data,
  );
}

export function deletePersonalization(
  userId: string,
): Promise<DeletePersonalizationResponse> {
  return api
    .delete<DeletePersonalizationResponse>(`/personalization/${userId}`)
    .then((r) => r.data);
}