import type { CatalogueCoverage } from "../types";

/**
 * Compact catalogue coverage funnel. Each stage is a bar whose width scales with how
 * far the request survived, and the count labels the step. Shown on both result shapes.
 */
export default function CoverageFunnel({ coverage }: { coverage: CatalogueCoverage }) {
  const steps: Array<{ key: string; label: string; value: number }> = [
    { key: "eligible", label: "Eligible", value: coverage.products_passing_eligibility },
    {
      key: "feasible",
      label: "Feasible",
      value: coverage.products_with_feasible_candidates,
    },
    { key: "scored", label: "Scored", value: coverage.candidates_scored },
    {
      key: "above",
      label: "Above threshold",
      value: coverage.candidates_above_suitability_threshold,
    },
    {
      key: "guardrails",
      label: "Pass guardrails",
      value: coverage.candidates_passing_guardrails,
    },
  ];

  // The funnel mixes product counts (Eligible/Feasible, each out of catalogue size) and
  // candidate counts (Scored/Above/Guardrails, potentially far larger than the number of
  // products). Scaling every stage against catalogue_products lets candidate stages exceed
  // 100% and overflow the bar track. Normalise against the largest stage value instead so
  // every bar stays within its track while the relative survival is still visible.
  const maxStep = Math.max(...steps.map((s) => s.value), 1);

  return (
    <div className="w-full min-w-0 overflow-hidden">
      <div className="text-sm font-semibold text-ink">How the options narrowed down</div>
      <div className="mt-2 space-y-1.5">
        {steps.map((s) => {
          const width = Math.max(4, Math.min(100, (s.value / maxStep) * 100));
          return (
            <div key={s.key} className="flex items-center gap-2">
              <div className="w-40 shrink-0 text-right text-xs text-ink-faint">
                {s.label}
              </div>
              <div className="h-4 flex-1 rounded-full bg-paper">
                <div
                  className="flex h-full items-center rounded-full bg-brand px-1 transition-all"
                  style={{ width: `${width}%` }}
                />
              </div>
              <div className="flex w-8 shrink-0 justify-end">
                <span className="inline-flex min-w-6 items-center justify-center rounded-md bg-brand-tint px-1.5 py-0.5 text-xs font-semibold text-brand-dark">
                  {s.value}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}