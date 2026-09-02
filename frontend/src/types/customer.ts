// Mirror app/schemas/customer.py.
import type {
  AssetType,
  EmploymentType,
  LoanPurpose,
  RiskAppetite,
} from "./enums";

export interface CustomerProfile {
  user_id?: string | null;
  monthly_income: number;
  monthly_expenses: number;
  existing_emi?: number;
  credit_score: number;
  employment_type: EmploymentType;
  employment_years: number;
  age: number;
  dependents?: number;
}

export interface Holding {
  asset_type: AssetType;
  current_value: number;
  invested_value: number;
}

export interface Portfolio {
  holdings: Holding[];
}

export interface LoanRequirement {
  purpose: LoanPurpose;
  required_amount: number;
  preferred_tenure_months: number;
  risk_appetite: RiskAppetite;
}

export interface LoanProduct {
  product_id: string;
  lender: string;
  product_name: string;
  purposes: LoanPurpose[];
  annual_rate: number;
  min_amount: number;
  max_amount: number;
  min_tenure_months: number;
  max_tenure_months: number;
  min_credit_score: number;
  min_monthly_income: number;
  processing_fee_pct: number;
}