import type { LoanPurpose, LoanRequirement, RiskAppetite } from "../types";

const PURPOSES: LoanPurpose[] = [
  "HOME",
  "VEHICLE",
  "EDUCATION",
  "PERSONAL",
  "BUSINESS",
  "MEDICAL",
];

const APPETITES: Array<{ value: RiskAppetite; hint: string }> = [
  {
    value: "CONSERVATIVE",
    hint: "Prefer stable, lower-risk financing; avoids aggressive strategies.",
  },
  {
    value: "MODERATE",
    hint: "A balanced approach between borrowing and investing.",
  },
  {
    value: "AGGRESSIVE",
    hint: "Comfortable with higher leverage and liquidation to reach the goal.",
  },
];

interface Props {
  value: LoanRequirement;
  onChange: (next: LoanRequirement) => void;
  onBack: () => void;
  onSubmit: () => void;
  submitting: boolean;
}

export default function RequirementForm({
  value,
  onChange,
  onBack,
  onSubmit,
  submitting,
}: Props) {
  const set = (patch: Partial<LoanRequirement>) => onChange({ ...value, ...patch });

  return (
    <section className="card card-pad card-accent">
      <h2 className="section-heading">Your loan requirement</h2>
      <p className="section-sub">
        What you're borrowing for, how much, over what term, and how much risk you're
        comfortable with.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div>
          <label className="field-label" htmlFor="purpose">Purpose</label>
          <select
            id="purpose"
            className="field-input"
            value={value.purpose}
            onChange={(e) => set({ purpose: e.target.value as LoanPurpose })}
          >
            {PURPOSES.map((p) => (
              <option key={p} value={p}>
                {p.toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="amount">Required amount (₹)</label>
          <input
            id="amount"
            className="field-input"
            type="number"
            min={1}
            value={value.required_amount || ""}
            onChange={(e) => set({ required_amount: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="tenure">Preferred tenure (months)</label>
          <input
            id="tenure"
            className="field-input"
            type="number"
            min={1}
            value={value.preferred_tenure_months || ""}
            onChange={(e) => set({ preferred_tenure_months: Math.round(Number(e.target.value)) })}
          />
        </div>
      </div>

      <div className="mt-6">
        <span className="field-label">How much risk feels okay?</span>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {APPETITES.map((a) => (
            <button
              key={a.value}
              type="button"
              onClick={() => set({ risk_appetite: a.value })}
              className={`rounded-md border p-3 text-left transition ${
                value.risk_appetite === a.value
                  ? "border-brand bg-brand-tint"
                  : "border-paper-line bg-white hover:border-ink-faint/40"
              }`}
            >
              <div className="text-sm font-semibold text-ink">
                {a.value.charAt(0) + a.value.slice(1).toLowerCase()}
              </div>
              <div className="mt-1 text-xs text-ink-faint">{a.hint}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <button className="btn-secondary" onClick={onBack}>
          Back
        </button>
        <button
          className="btn-primary"
          onClick={onSubmit}
          disabled={submitting || value.required_amount <= 0 || value.preferred_tenure_months <= 0}
        >
          {submitting ? "Scoring your options…" : "Get my loan recommendation"}
        </button>
      </div>
    </section>
  );
}