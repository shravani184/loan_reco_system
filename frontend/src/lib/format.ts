// Currency / unit formatting helpers. Money is in rupees (float).

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inrCents = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function rupees(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return "—";
  return inr.format(value);
}

export function rupeesPrecise(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return "—";
  return inrCents.format(value);
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value == null || !isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function rate(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return "—";
  return `${value.toFixed(1)}%`;
}

export function yearsMonths(months: number | null | undefined): string {
  if (months == null || !isFinite(months)) return "—";
  const y = Math.floor(months / 12);
  const m = months % 12;
  if (y === 0) return `${m} ${m === 1 ? "month" : "months"}`;
  if (m === 0) return `${y} ${y === 1 ? "year" : "years"}`;
  return `${y}y ${m}m`;
}

export type StrategyLabel = string;

export const STRATEGY_LABELS: Record<string, string> = {
  BORROW_100: "Borrow 100%",
  BORROW_80_LIQUIDATE_20: "Borrow 80% / liquidate 20%",
  BORROW_60_LIQUIDATE_40: "Borrow 60% / liquidate 40%",
  BORROW_40_LIQUIDATE_60: "Borrow 40% / liquidate 60%",
  BORROW_20_LIQUIDATE_80: "Borrow 20% / liquidate 80%",
  LIQUIDATE_100: "Liquidate 100%",
};

export function strategyHuman(strategy: string): string {
  return STRATEGY_LABELS[strategy] ?? strategy;
}

export function candidateTitle(candidate: {
  lender?: string | null;
  product_id?: string | null;
  strategy: string;
}): string {
  if (candidate.lender) return candidate.lender;
  if (candidate.strategy === "LIQUIDATE_100") return "Full liquidation";
  return candidate.product_id || "Holding-backed option";
}