import type { CustomerProfile, EmploymentType } from "../types";

const EMPLOYMENT_TYPES: EmploymentType[] = [
  "SALARIED",
  "SELF_EMPLOYED",
  "CONTRACT",
  "RETIRED",
];

interface Props {
  value: CustomerProfile;
  onChange: (next: CustomerProfile) => void;
  onNext: () => void;
}

export default function ProfileForm({ value, onChange, onNext }: Props) {
  const set = (patch: Partial<CustomerProfile>) => onChange({ ...value, ...patch });

  return (
    <section className="card card-pad card-accent">
      <h2 className="section-heading">Your financial profile</h2>
      <p className="section-sub">
        How much you earn, spend and owe each month. This drives affordability and
        eligibility.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="field-label" htmlFor="monthly_income">
            Monthly income (₹)
          </label>
          <input
            id="monthly_income"
            className="field-input"
            type="number"
            min={0}
            value={value.monthly_income}
            onChange={(e) => set({ monthly_income: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="monthly_expenses">
            Monthly expenses (₹)
          </label>
          <input
            id="monthly_expenses"
            className="field-input"
            type="number"
            min={0}
            value={value.monthly_expenses}
            onChange={(e) => set({ monthly_expenses: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="existing_emi">
            Existing EMI (₹)
          </label>
          <input
            id="existing_emi"
            className="field-input"
            type="number"
            min={0}
            value={value.existing_emi}
            onChange={(e) => set({ existing_emi: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="credit_score">
            Credit score
          </label>
          <input
            id="credit_score"
            className="field-input"
            type="number"
            min={300}
            max={900}
            value={value.credit_score}
            onChange={(e) => set({ credit_score: Math.round(Number(e.target.value)) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="employment_type">
            Employment type
          </label>
          <select
            id="employment_type"
            className="field-input"
            value={value.employment_type}
            onChange={(e) => set({ employment_type: e.target.value as EmploymentType })}
          >
            {EMPLOYMENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ").toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="employment_years">
            Employment years
          </label>
          <input
            id="employment_years"
            className="field-input"
            type="number"
            min={0}
            value={value.employment_years}
            onChange={(e) => set({ employment_years: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="age">
            Age
          </label>
          <input
            id="age"
            className="field-input"
            type="number"
            min={18}
            max={100}
            value={value.age}
            onChange={(e) => set({ age: Math.round(Number(e.target.value)) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="dependents">
            Dependents
          </label>
          <input
            id="dependents"
            className="field-input"
            type="number"
            min={0}
            value={value.dependents}
            onChange={(e) => set({ dependents: Math.max(0, Math.round(Number(e.target.value))) })}
          />
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button className="btn-primary" onClick={onNext} disabled={value.credit_score < 300 || value.credit_score > 900}>
          Next: how will you fund it?
        </button>
      </div>
    </section>
  );
}