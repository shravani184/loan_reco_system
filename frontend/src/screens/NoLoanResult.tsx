import type {
  MismatchReason,
  Recommendation,
} from "../types";
import { rupees, yearsMonths, percent } from "../lib/format";
import CoverageFunnel from "../components/CoverageFunnel";

const TITLES: Record<string, string> = {
  NO_ELIGIBLE_PRODUCTS: "No catalogue product matches your profile",
  NO_FEASIBLE_CANDIDATES: "No financing arrangement could be built",
  ALL_CANDIDATES_BLOCKED: "Every candidate was blocked by a safety rule",
  NO_SUITABLE_LOAN: "None of the available loans is a good fit for you",
};

export default function NoLoanResult({ result }: { result: Recommendation }) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-paper-line bg-brand-tint p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand/10 text-brand-dark">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 9v3.75m0 3.25h.008v.008H12V16z" />
              <circle cx="12" cy="12" r="9" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-ink">
              {TITLES[result.status] ?? result.status}
            </h3>
            <p className="mt-1 text-sm text-ink-soft">
              We went through every option in the catalogue. Here's how far your request
              got, and why nothing was recommended.
            </p>
          </div>
        </div>
      </div>

      <div className="card card-pad">
        <CoverageFunnel coverage={result.coverage} />
      </div>

      {result.mismatch_reasons.length ? (
        <div className="card card-pad">
          <h4 className="text-base font-semibold text-ink">Why no loan was recommended</h4>
          <ul className="mt-3 space-y-2">
            {result.mismatch_reasons.map((reason, i) => (
              <MismatchLine key={i} reason={reason} />
            ))}
          </ul>
        </div>
      ) : null}

      <OutcomeAdvice result={result} />
    </div>
  );
}

function MismatchLine({ reason }: { reason: MismatchReason }) {
  return (
    <li className="flex items-start gap-2 rounded-md bg-paper px-3 py-2 text-sm">
      <span className="mt-0.5 text-ink-faint">·</span>
      <span className="text-ink-soft">
        {reading(reason)}
      </span>
    </li>
  );
}

function reading(reason: MismatchReason): string {
  switch (reason.code) {
    case "CREDIT_SCORE_BELOW_MINIMUM":
      return `This option requires a credit score of ${reason.threshold_value} (yours: ${reason.observed_value}).`;
    case "INCOME_BELOW_MINIMUM":
      return `This option requires monthly income of ${rupees(reason.threshold_value)} (your income: ${rupees(reason.observed_value)}).`;
    case "AMOUNT_ABOVE_PRODUCT_MAX":
      return `Your requested amount exceeds this product's maximum of ${rupees(reason.threshold_value)}.`;
    case "AMOUNT_BELOW_PRODUCT_MIN":
      return `Your requested amount is below this product's minimum of ${rupees(reason.threshold_value)}.`;
    case "TENURE_OUT_OF_RANGE":
      return `Your preferred tenure exceeds this product's limit (max ${yearsMonths(reason.threshold_value)}).`;
    case "PURPOSE_NOT_SUPPORTED":
      return `This product does not support your loan purpose.`;
    case "EMI_EXCEEDS_AFFORDABILITY":
      return `The EMI exceeds what you can afford each month.`;
    case "LIQUIDATION_EXCEEDS_PORTFOLIO":
      return `The strategy would liquidate more than your portfolio holds.`;
    case "REQUIRED_AMOUNT_UNREACHABLE":
      return `No combination of borrowing and liquidation reaches your requested amount.`;
    case "DEBT_BURDEN_CAP_EXCEEDED":
      return `Your debt burden would exceed the safety cap of ${percent(reason.threshold_value)} (this option: ${percent(reason.observed_value)}).`;
    case "LOAN_TO_INCOME_CAP_EXCEEDED":
      return `Your loan-to-income would exceed the safety cap (this option: ${percent(reason.observed_value)}).`;
    case "LIQUIDATION_SHARE_CAP_EXCEEDED":
      return `It would liquidate more of your portfolio than your risk profile allows (cap ${percent(reason.threshold_value)}, this option ${percent(reason.observed_value)}).`;
    case "VOLATILE_ASSET_LIQUIDATION_PROHIBITED":
      return `It relies on liquidating volatile assets, which your risk profile avoids.`;
    case "SUITABILITY_BELOW_THRESHOLD":
      return `The remaining eligible options scored below the suitability threshold (best ${percent(reason.observed_value)}, threshold ${percent(reason.threshold_value)}).`;
    default:
      return `This option was not a fit (${reason.code}).`;
  }
}

function OutcomeAdvice({ result }: { result: Recommendation }) {
  const suggestions: string[] = [];
  const reasons = result.mismatch_reasons;
  const has = (codes: string[]) =>
    reasons.some((r) => codes.includes(r.code));

  if (has(["AMOUNT_ABOVE_PRODUCT_MAX", "REQUIRED_AMOUNT_UNREACHABLE"])) {
    suggestions.push("a smaller loan amount");
  }
  if (has(["TENURE_OUT_OF_RANGE"])) {
    suggestions.push("a shorter tenure");
  }
  if (has(["CREDIT_SCORE_BELOW_MINIMUM"])) {
    suggestions.push("a higher credit score");
  }
  if (has(["INCOME_BELOW_MINIMUM", "EMI_EXCEEDS_AFFORDABILITY"])) {
    suggestions.push("higher income or lower existing commitments");
  }
  if (has(["PURPOSE_NOT_SUPPORTED"])) {
    suggestions.push("a loan purpose supported by more of the catalogue");
  }
  if (has(["LIQUIDATION_SHARE_CAP_EXCEEDED", "VOLATILE_ASSET_LIQUIDATION_PROHIBITED"])) {
    suggestions.push("a different risk appetite");
  }
  if (has(["SUITABILITY_BELOW_THRESHOLD"])) {
    suggestions.push("options closer to your preferred amount and tenure");
  }

  if (!suggestions.length) {
    return (
      <div className="card card-pad border-l-2 border-l-ink-faint">
        <h5 className="text-sm font-semibold text-ink">What would change the outcome</h5>
        <p className="mt-1 text-sm text-ink-soft">
          None of the reasons here points to a single change. Adjusting your details and
          re-running may surface a suitable option.
        </p>
      </div>
    );
  }

  return (
    <div className="card card-pad border-l-2 border-l-brand">
      <h5 className="text-sm font-semibold text-ink">What would change the outcome</h5>
      <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
        {suggestions.map((s, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-0.5 text-brand">→</span>
            {s.charAt(0).toUpperCase() + s.slice(1)}.
          </li>
        ))}
      </ul>
    </div>
  );
}