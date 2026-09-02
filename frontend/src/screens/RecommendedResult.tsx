import { useState } from "react";
import type {
  Candidate,
  CatalogueCoverage,
  Recommendation,
  RecommendRequest,
  ScoredCandidate,
} from "../types";
import { rupees, yearsMonths, strategyHuman, candidateTitle } from "../lib/format";
import CoverageFunnel from "../components/CoverageFunnel";
import ExplanationPanel from "./ExplanationPanel";
import StrategyComparison from "./StrategyComparison";
import BlockedCallout from "./BlockedCallout";

export default function RecommendedResult({
  result,
  request,
}: {
  result: Recommendation;
  request: RecommendRequest;
}) {
  const winner = result.selected_candidate;
  if (!winner) {
    return <div className="card card-pad">No candidate was selected.</div>;
  }

  return (
    <div className="space-y-6">
      <BlockedCallout blocked={result.ml_top_choice_blocked} />

      <Headline winner={winner} suitability={result.ml_suitability} />

      <ExplanationPanel result={result} request={request} />

      <Alternatives alternatives={result.alternatives} winnerId={winner.candidate_id} />

      <StrategyComparison traceCounts={result.decision_trace} winner={winner} />

      <div className="card card-pad card-accent">
        <CoverageFunnel coverage={result.coverage} />
      </div>

      <EliminatedOptions
        coverage={result.coverage}
        ranked={result.decision_trace.ranked_candidates}
        winnerId={winner.candidate_id}
      />
    </div>
  );
}

function Headline({
  winner,
  suitability,
}: {
  winner: Candidate;
  suitability?: number | null;
}) {
  return (
    <div className="card card-pad overflow-hidden">
      <div className="relative -mx-6 -mt-6 mb-5 border-b border-paper-line bg-brand-tint px-6 pb-5 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-brand-dark">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand" />
              Recommended for you
            </div>
            <h3 className="mt-1 text-2xl font-bold text-ink">{candidateTitle(winner)}</h3>
          </div>
          {suitability != null ? (
            <div className="text-right">
              <div className="text-xs text-ink-faint">ML suitability</div>
              <div className="text-3xl font-bold text-ink">
                {(suitability * 100).toFixed(1)}%
              </div>
            </div>
          ) : null}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <HeadlineStat label="Loan amount" value={rupees(winner.loan_amount)} />
          <HeadlineStat label="Tenure" value={yearsMonths(winner.tenure_months)} />
          <HeadlineStat label="Monthly EMI" value={rupees(winner.emi)} />
          <HeadlineStat label="Financing" value={strategyHuman(winner.strategy)} />
        </div>
      </div>

      {suitability == null ? (
        <p className="text-sm text-ink-faint">
          This option was selected by the fallback because the ML model is unavailable,
          so no suitability score is shown.
        </p>
      ) : (
        <SuitabilityBar value={suitability} />
      )}
    </div>
  );
}

function SuitabilityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const pctClamped = Math.min(100, Math.max(0, pct));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-ink-faint">
        <span>How well this fits your profile, scored by the model</span>
        <span className="font-semibold text-brand">{pct}%</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-paper">
        <div
          className="h-full rounded-full bg-brand transition-all"
          style={{ width: `${pctClamped}%` }}
        />
      </div>
    </div>
  );
}

function HeadlineStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-ink-faint">{label}</div>
      <div className="text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}

function Alternatives({
  alternatives,
  winnerId,
}: {
  alternatives: ScoredCandidate[];
  winnerId: string;
}) {
  const next = alternatives.filter(
    (a) => a.candidate.candidate_id !== winnerId,
  );
  if (!next.length) return null;
  return (
    <div className="card card-pad">
      <h3 className="text-base font-semibold text-ink">Alternatives worth a look</h3>
      <p className="text-xs text-ink-faint">
        The next best options, in the model's order.
      </p>
      <ul className="mt-3 space-y-2">
        {next.slice(0, 4).map((a) => (
          <li
            key={a.candidate.candidate_id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-paper-line bg-white px-3 py-2.5"
          >
            <div className="text-sm">
              <span className="font-medium text-ink">{candidateTitle(a.candidate)}</span>{" "}
              <span className="text-ink-faint">
                · {rupees(a.candidate.loan_amount)} ·{" "}
                {yearsMonths(a.candidate.tenure_months)} · EMI {rupees(a.candidate.emi)}
              </span>
            </div>
            <span className="text-sm font-semibold text-brand">
              {a.suitability == null ? "—" : `${(a.suitability * 100).toFixed(1)}%`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EliminatedOptions({
  ranked,
  coverage,
  winnerId,
}: {
  ranked: ScoredCandidate[];
  coverage: CatalogueCoverage;
  winnerId: string;
}) {
  const [open, setOpen] = useState(false);
  // Two visually separate groups:
  //  - those at/above the suitability threshold but not chosen (missed the walk)
  //  - those below the suitability threshold (qualified but not a good fit)
  const others = ranked
    .filter((s) => s.candidate.candidate_id !== winnerId)
    .filter((s) => s.candidate.feasible !== false);
  const above = others.filter(
    (s) => s.suitability != null && s.suitability > 0.5,
  );
  const below = others.filter(
    (s) => s.suitability == null || s.suitability <= 0.5,
  );

  return (
    <div className="card card-pad">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-base font-semibold text-ink"
      >
        <span>Eliminated options</span>
        <span className="text-sm text-ink-faint">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div className="mt-4 space-y-6">
          <EliminatedGroup
            title="You don't qualify for these"
            note="This product needs a detail your profile doesn't meet."
            items={[]}
            categories={groupIneligible(coverage)}
            color="bg-paper"
          />
          <EliminatedGroup
            title="You qualify, but it isn't a good fit"
            note="These cleared eligibility and feasibility but scored below the suitability threshold."
            items={below}
            color="bg-brand-tint"
          />
          {above.length ? (
            <EliminatedGroup
              title="Scored well but not selected"
              note="These were eligible and above threshold but lost to the winner in the model's ranking."
              items={above}
              color="bg-paper"
            />
          ) : null}
        </div>
      ) : (
        <div className="mt-1 text-xs text-ink-faint">
          Products filtered out at eligibility, and options that cleared it but scored
          below the suitability threshold.
        </div>
      )}
    </div>
  );
}

function EliminatedGroup({
  title,
  note,
  items,
  categories,
  color,
}: {
  title: string;
  note: string;
  items: ScoredCandidate[];
  categories?: Array<{ label: string; count: number }>;
  color: string;
}) {
  return (
    <div className={`rounded-md p-4 ${color}`}>
      <div className="text-sm font-semibold text-ink">{title}</div>
      <div className="mt-0.5 text-xs text-ink-faint">{note}</div>
      {categories ? (
        <ul className="mt-2 space-y-1 text-xs text-ink-soft">
          {categories.map((c) => (
            <li key={c.label}>
              {c.count} product{c.count === 1 ? "" : "s"} — {c.label}
            </li>
          ))}
        </ul>
      ) : null}
      {items.length ? (
        <ul className="mt-2 space-y-1 text-xs text-ink-soft">
          {items.map((s) => (
            <li key={s.candidate.candidate_id}>
              {candidateTitle(s.candidate)} —{" "}
              {s.suitability == null ? "no score" : `${(s.suitability * 100).toFixed(1)}%`}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function groupIneligible(coverage: CatalogueCoverage): Array<{ label: string; count: number }> {
  // Numbers beyond catalogue to eligibility are the ineligible tail.
  const ineligible = coverage.catalogue_products - coverage.products_passing_eligibility;
  const infeasible = coverage.products_passing_eligibility - coverage.products_with_feasible_candidates;
  const counts: Array<{ label: string; count: number }> = [];
  if (ineligible > 0) counts.push({ label: "failed eligibility checks", count: ineligible });
  if (infeasible > 0) counts.push({ label: "no feasible candidate (amount/tenure/EMI)", count: infeasible });
  return counts;
}