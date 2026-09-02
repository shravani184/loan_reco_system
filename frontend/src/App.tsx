import { useState } from "react";
import type {
  CustomerProfile,
  Holding,
  LoanRequirement,
  Portfolio,
  Recommendation,
  RecommendRequest,
} from "./types";
import { LOAN_PURPOSE, RISK_APPETITE } from "./types";
import { recommend } from "./api/client";
import ProfileForm from "./screens/ProfileForm";
import PortfolioForm from "./screens/PortfolioForm";
import RequirementForm from "./screens/RequirementForm";
import ResultsScreen from "./screens/ResultsScreen";
import LoadingPanel from "./components/LoadingPanel";
import ErrorPanel from "./components/ErrorPanel";

type Step = "profile" | "portfolio" | "requirement" | "results";

const DEFAULT_PROFILE: CustomerProfile = {
  user_id: null,
  monthly_income: 120000,
  monthly_expenses: 45000,
  existing_emi: 8000,
  credit_score: 780,
  employment_type: "SALARIED",
  employment_years: 8,
  age: 34,
  dependents: 1,
};

const DEFAULT_REQUIREMENT: LoanRequirement = {
  purpose: LOAN_PURPOSE.HOME,
  required_amount: 1500000,
  preferred_tenure_months: 120,
  risk_appetite: RISK_APPETITE.MODERATE,
};

export default function App() {
  const [step, setStep] = useState<Step>("profile");
  const [profile, setProfile] = useState<CustomerProfile>(DEFAULT_PROFILE);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [requirement, setRequirement] = useState<LoanRequirement>(DEFAULT_REQUIREMENT);
  const [result, setResult] = useState<Recommendation | null>(null);
  const [submitted, setSubmitted] = useState<RecommendRequest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const skip = () => {
    setHoldings([]);
    setStep("requirement");
  };

  const submit = async () => {
    const portfolio: Portfolio = { holdings };
    const request: RecommendRequest = {
      customer: profile,
      portfolio,
      requirement,
      user_id: profile.user_id,
    };
    setLoading(true);
    setError(null);
    try {
      const res = await recommend(request);
      setResult(res);
      setSubmitted(request);
      setStep("results");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not reach the recommendation service.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-white shadow-md shadow-brand/30">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 21h18" />
              <path d="M6 18V10" />
              <path d="M10 18V5" />
              <path d="M14 18V8" />
              <path d="M18 18V11" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              Recommended <span className="text-brand">Loan</span>
            </h1>
            <p className="text-xs text-slate-500">
              A model-driven loan recommendation — ML picks, safety rules and your
              finances decide feasibility.
            </p>
          </div>
        </div>
        <div className="h-1 bg-gradient-to-r from-brand via-brand-light to-brand-dark" />
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8">
        {step !== "results" ? (
          <StepIndicator current={step} />
        ) : null}

        {step === "profile" && (
          <ProfileForm
            value={profile}
            onChange={setProfile}
            onNext={() => setStep("portfolio")}
          />
        )}

        {step === "portfolio" && (
          <PortfolioForm
            holdings={holdings}
            onChange={setHoldings}
            onContinue={() => setStep("requirement")}
            onSkip={skip}
            onBack={() => setStep("profile")}
          />
        )}

        {step === "requirement" && (
          <RequirementForm
            value={requirement}
            onChange={setRequirement}
            onBack={() => setStep("portfolio")}
            onSubmit={submit}
            submitting={loading}
          />
        )}

        {step === "results" && result && submitted && (
          <>
            {error ? <div className="mb-4"><ErrorPanel message={error} /></div> : null}
            <ResultsScreen
              result={result}
              request={submitted}
              onEdit={() => setStep("profile")}
            />
          </>
        )}

        {loading && step !== "results" ? (
          <LoadingPanel label="Scoring your options…" />
        ) : null}
      </main>
    </div>
  );
}

const STEPS: Array<{ key: Step; label: string }> = [
  { key: "profile", label: "Your finances" },
  { key: "portfolio", label: "Your investments" },
  { key: "requirement", label: "Your loan" },
];

function StepIndicator({ current }: { current: Step }) {
  const activeIndex = STEPS.findIndex((s) => s.key === current);
  return (
    <ol className="mb-6 flex items-center gap-2 sm:gap-3">
      {STEPS.map((s, i) => {
        const done = i < activeIndex;
        const active = i === activeIndex;
        return (
          <li key={s.key} className="flex flex-1 items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition ${
                  done
                    ? "bg-brand text-white"
                    : active
                    ? "bg-brand text-white shadow-md shadow-brand/30 ring-4 ring-brand/15"
                    : "bg-slate-200 text-slate-500"
                }`}
              >
                {done ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                  </svg>
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={`hidden text-sm font-medium sm:inline ${
                  active || done ? "text-slate-800" : "text-slate-400"
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 ? (
              <div
                className={`h-0.5 flex-1 rounded-full transition ${
                  done ? "bg-brand" : "bg-slate-200"
                }`}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}