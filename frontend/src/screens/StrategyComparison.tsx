import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candidate, DecisionTrace, ScoredCandidate } from "../types";
import { rupees, strategyHuman } from "../lib/format";

/**
 * Strategy comparison (borrow vs liquidate vs hybrid) for the winner's product.
 * Built from the ranked candidates so it reflects what the model actually scored.
 */
export default function StrategyComparison({
  traceCounts,
  winner,
}: {
  traceCounts: DecisionTrace;
  winner: Candidate;
}) {
  const productId = winner.product_id;
  const rows = traceCounts.ranked_candidates
    .filter((s) => s.candidate.product_id === productId)
    .sort((a, b) => a.candidate.loan_amount - b.candidate.loan_amount);

  if (rows.length < 2) return null;

  const toChartRow = (s: ScoredCandidate) => ({
    name: strategyHuman(s.candidate.strategy),
    "EMI (₹)": Math.round(s.candidate.emi),
    "Total interest (₹)": Math.round(s.candidate.total_interest),
    "Remaining portfolio (₹)": Math.round(s.candidate.remaining_portfolio_value),
  });

  const data = rows.map(toChartRow);

  return (
    <div className="card card-pad card-accent">
      <h3 className="text-base font-semibold text-slate-900">Strategy comparison</h3>
      <p className="text-xs text-slate-500">
        How borrow vs liquidate changes your EMI, total interest and remaining
        portfolio. This is the model's scored view across financing strategies.
      </p>
      <div className="mt-4 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
            <Tooltip
              formatter={(value: number | string, name: string) => [
                rupees(Number(value)),
                name,
              ]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="EMI (₹)" fill="#1d4ed8" />
            <Bar dataKey="Total interest (₹)" fill="#d97706" />
            <Bar dataKey="Remaining portfolio (₹)" fill="#059669" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}