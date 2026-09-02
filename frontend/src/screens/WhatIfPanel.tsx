import { useState } from "react";
import type { Recommendation, RecommendRequest } from "../types";
import { rupees, candidateTitle } from "../lib/format";
import LoadingPanel from "../components/LoadingPanel";
import ErrorPanel from "../components/ErrorPanel";

export default function WhatIfPanel({
  base,
  request,
  scenario,
  loading,
  error,
  onRun,
}: {
  base: Recommendation;
  request: RecommendRequest;
  scenario: Recommendation | null;
  loading: boolean;
  error: string | null;
  onRun: (next: RecommendRequest) => void;
}) {
  const [amount, setAmount] = useState(request.requirement.required_amount);
  const [tenure, setTenure] = useState(request.requirement.preferred_tenure_months);
  const [income, setIncome] = useState(request.customer.monthly_income);

  if (base.status !== "RECOMMENDED") return null;

  const run = () => {
    const next: RecommendRequest = {
      ...request,
      customer: { ...request.customer, monthly_income: Number(income) },
      requirement: {
        ...request.requirement,
        required_amount: Number(amount),
        preferred_tenure_months: Math.round(Number(tenure)),
      },
    };
    onRun(next);
  };

  return (
    <div className="card card-pad">
      <h3 className="text-base font-semibold text-slate-900">What if…?</h3>
      <p className="text-xs text-slate-500">
        Re-run the full model on modified inputs to see how suitability moves. This is a
        fresh recommendation, not a manual tweak of the current one.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className="field-label" htmlFor="wf_amount">Required amount (₹)</label>
          <input
            id="wf_amount"
            className="field-input"
            type="number"
            min={1}
            value={amount || ""}
            onChange={(e) => setAmount(Number(e.target.value))}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="wf_tenure">Tenure (months)</label>
          <input
            id="wf_tenure"
            className="field-input"
            type="number"
            min={1}
            value={tenure || ""}
            onChange={(e) => setTenure(Number(e.target.value))}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="wf_income">Monthly income (₹)</label>
          <input
            id="wf_income"
            className="field-input"
            type="number"
            min={0}
            value={income || ""}
            onChange={(e) => setIncome(Number(e.target.value))}
          />
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <button className="btn-primary" onClick={run} disabled={loading}>
          {loading ? "Re-scoring…" : "Re-run what-if"}
        </button>
      </div>

      {loading ? <div className="mt-4"><LoadingPanel label="Running the scenario…" /></div> : null}
      {error ? <div className="mt-4"><ErrorPanel message={error} /></div> : null}
      {scenario ? <ScenarioResult base={base} scenario={scenario} /> : null}
    </div>
  );
}

function ScenarioResult({
  base,
  scenario,
}: {
  base: Recommendation;
  scenario: Recommendation;
}) {
  const b = base.selected_candidate;
  const s = scenario.selected_candidate;
  return (
    <div className="mt-4 rounded-xl border border-brand/20 border-l-4 border-l-brand bg-gradient-to-br from-white to-blue-50 p-4">
      <div className="text-sm font-semibold text-slate-800">How suitability moved</div>
      {base.status === "RECOMMENDED" && scenario.status === "RECOMMENDED" && b && s ? (
        <div className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <Row
            label="Now"
            text={`${candidateTitle(b)} · ${rupees(b.loan_amount)}`}
            score={base.ml_suitability}
          />
          <Row
            label="What-if"
            text={`${candidateTitle(s)} · ${rupees(s.loan_amount)}`}
            score={scenario.ml_suitability}
            delta={delta(base.ml_suitability, scenario.ml_suitability)}
          />
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-600">
          With those inputs the result is{" "}
          <span className="font-semibold">{scenario.status}</span>.
        </p>
      )}
    </div>
  );
}

function delta(a: number | null | undefined, b: number | null | undefined): number | null {
  if (a == null || b == null) return null;
  return b - a;
}

function Row({
  label,
  text,
  score,
  delta,
}: {
  label: string;
  text: string;
  score?: number | null;
  delta?: number | null;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium">{text}</div>
      <div className="mt-1 flex items-center gap-2 text-sm">
        <span className="font-semibold text-brand">
          {score == null ? "n/a" : `${(score * 100).toFixed(1)}%`}
        </span>
        {delta != null ? (
          <span
            className={`text-xs ${delta > 0 ? "text-emerald-600" : delta < 0 ? "text-red-600" : "text-slate-400"}`}
          >
            {delta > 0 ? "▲" : delta < 0 ? "▼" : "•"} {Math.abs(delta * 100).toFixed(1)}%
          </span>
        ) : null}
      </div>
    </div>
  );
}