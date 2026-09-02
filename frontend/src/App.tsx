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
      <header className="sticky top-0 z-10 border-b border-paper-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-4">
          <span className="text-2xl leading-none text-brand" aria-hidden="true">
            ⟡
          </span>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-ink">Loan Match</h1>
            <p className="text-xs text-ink-faint">
              A quick check of which loan fits your finances — no jargon, no judgement.
            </p>
          </div>
        </div>
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
                className={`text-sm font-medium ${
                  done
                    ? "text-ink-soft"
                    : active
                    ? "text-brand"
                    : "text-ink-faint"
                }`}
              >
                {done ? "✓" : `${i + 1}.`}
              </span>
              <span
                className={`hidden text-sm sm:inline ${
                  active ? "text-ink" : "text-ink-faint"
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 ? (
              <div
                className={`h-px flex-1 transition ${
                  done ? "bg-brand/40" : "bg-paper-line"
                }`}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}