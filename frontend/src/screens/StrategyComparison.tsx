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
      <h3 className="text-base font-semibold text-ink">Strategy comparison</h3>
      <p className="mt-1 text-xs text-ink-faint">
        How borrowing vs liquidating changes your EMI, total interest and remaining
        portfolio, in the model's scored view.
      </p>
      <div className="mt-4 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e9e2da" />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#6b5f55" }} />
            <YAxis tick={{ fontSize: 11, fill: "#6b5f55" }} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
            <Tooltip
              formatter={(value: number | string, name: string) => [
                rupees(Number(value)),
                name,
              ]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="EMI (₹)" fill="#b3562b" />
            <Bar dataKey="Total interest (₹)" fill="#d1794b" />
            <Bar dataKey="Remaining portfolio (₹)" fill="#8f4322" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}