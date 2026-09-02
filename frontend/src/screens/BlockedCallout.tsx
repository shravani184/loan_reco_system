import type { BlockedTopChoice } from "../types";
import { rupees, yearsMonths, strategyHuman, candidateTitle } from "../lib/format";

/**
 * The product's signature moment: the model's top choice was real, but a guardrail
 * overrode it. This must be visible, not buried. It only renders when present.
 */
export default function BlockedCallout({ blocked }: { blocked?: BlockedTopChoice | null }) {
  if (!blocked) return null;
  const c = blocked.candidate;

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-5">
      <div className="flex items-start gap-3">
        <svg
          className="mt-0.5 h-5 w-5 shrink-0 text-amber-600"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
          />
        </svg>
        <div className="flex-1">
          <div className="text-sm font-bold text-amber-900">
            The model's best match for you was adjusted by a safety rule
          </div>
          <div className="mt-2 text-sm leading-relaxed text-ink-soft">
            <span className="font-semibold text-ink">{candidateTitle(c)}</span>{" "}
            ({rupees(c.loan_amount)} · {yearsMonths(c.tenure_months)} ·{" "}
            {strategyHuman(c.strategy)}) was your model's top pick with suitability{" "}
            <span className="font-semibold">
              {blocked.suitability == null
                ? "n/a"
                : `${(blocked.suitability * 100).toFixed(1)}%`}
            </span>
            , but it exceeds your risk profile:{" "}
            <span className="font-semibold">{readingRule(blocked)}</span>{" "}
            {blocked.cap_value != null && blocked.observed_value != null ? (
              <span>
                (cap {formatCap(blocked)}, this option {capObserved(blocked)}), so we
                recommend a safer option instead.
              </span>
            ) : (
              <span>, so we recommend a safer option instead.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function readingRule(blocked: BlockedTopChoice): string {
  switch (blocked.reason_code) {
    case "DEBT_BURDEN_CAP_EXCEEDED":
      return "your debt burden would exceed the allowed cap";
    case "LOAN_TO_INCOME_CAP_EXCEEDED":
      return "your loan-to-income would exceed the allowed cap";
    case "LIQUIDATION_SHARE_CAP_EXCEEDED":
      return "it would liquidate more of your portfolio than your profile allows";
    case "VOLATILE_ASSET_LIQUIDATION_PROHIBITED":
      return "it would liquidate volatile assets your profile avoids";
    default:
      return blocked.blocking_rule || "a safety rule";
  }
}

function formatCap(blocked: BlockedTopChoice): string {
  if (blocked.reason_code === "LIQUIDATION_SHARE_CAP_EXCEEDED" || blocked.cap_value != null && blocked.cap_value <= 1) {
    return `${(blocked.cap_value ?? 0) * 100}%`;
  }
  return rupees(blocked.cap_value);
}

function capObserved(blocked: BlockedTopChoice): string {
  if (blocked.reason_code === "LIQUIDATION_SHARE_CAP_EXCEEDED" || blocked.observed_value != null && blocked.observed_value <= 1) {
    return `${(blocked.observed_value ?? 0) * 100}%`;
  }
  return rupees(blocked.observed_value);
}