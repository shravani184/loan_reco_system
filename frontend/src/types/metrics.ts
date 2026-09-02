// Mirror app/schemas/metrics.py, app/schemas/personalization.py, app/schemas/risk.py.
import type {
  AssetType,
  FinancialHealth,
  FinancingStrategy,
  LoanPurpose,
  PortfolioRisk,
  RiskClass,
} from "./enums";

export interface FinancialMetrics {
  monthly_income: number;
  monthly_expenses: number;
  existing_emi: number;
  disposable_income: number;
  debt_burden_ratio: number;
  expense_ratio: number;
  emi_affordability_ceiling: number;
  income_stability_score: number;
  financial_health: FinancialHealth;
}

export interface PortfolioMetrics {
  has_portfolio: boolean;
  total_value: number;
  allocation: Record<AssetType, number>;
  liquid_value: number;
  liquidity_ratio: number;
  equity_exposure: number;
  debt_exposure: number;
  crypto_exposure: number;
  concentration_risk: number;
  unrealized_gain_loss: number;
  portfolio_risk: PortfolioRisk;
}

export interface RiskPrediction {
  risk_class: RiskClass;
  probability_of_default: number;
  model_version: string;
  imputed?: boolean;
}

export interface PersonalizationContext {
  is_cold_start: boolean;
  session_count: number;
  prior_declines: number;
  engagement_score: number;
  preferred_tenure_band_months?: number | null;
  purpose_affinity: Record<LoanPurpose, number>;
  strategy_affinity: Record<FinancingStrategy, number>;
}