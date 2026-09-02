import { useState } from "react";
import type { Recommendation, RecommendRequest } from "../types";
import { RECOMMENDATION_STATUS } from "../types";
import { runScenario } from "../api/client";
import SourceBadge from "../components/SourceBadge";
import SyntheticDataLabel from "../components/SyntheticDataLabel";
import RecommendedResult from "./RecommendedResult";
import NoLoanResult from "./NoLoanResult";
import WhatIfPanel from "./WhatIfPanel";

export default function ResultsScreen({
  result,
  request,
  onEdit,
}: {
  result: Recommendation;
  request: RecommendRequest;
  onEdit: () => void;
}) {
  const [scenario, setScenario] = useState<Recommendation | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  const runWhatIf = async (next: RecommendRequest) => {
    setScenarioLoading(true);
    setScenarioError(null);
    try {
      setScenario(await runScenario(next));
    } catch (e) {
      setScenarioError(
        e instanceof Error ? e.message : "Could not run the what-if comparison.",
      );
    } finally {
      setScenarioLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-paper-line bg-white px-6 py-5 shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-ink">Your recommendation</h2>
            <SourceBadge source={result.source} />
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-md border border-paper-line bg-white px-4 py-2 text-sm font-semibold text-ink-soft transition hover:border-ink-faint/40 hover:text-ink"
            onClick={onEdit}
          >
            Change my details
          </button>
        </div>
      </div>

      {renderStatus(result, request)}

      {result.source === "DETERMINISTIC_FALLBACK" ? (
        <p className="text-xs text-amber-700">
          This result was produced by the fallback because the recommendation model is
          unavailable. Suitability scores are not shown, since only the model computes
          them.
        </p>
      ) : null}

      <WhatIfPanel
        base={result}
        request={request}
        scenario={scenario}
        loading={scenarioLoading}
        error={scenarioError}
        onRun={runWhatIf}
      />

      <SyntheticDataLabel />
      <Footer />
    </div>
  );
}

function renderStatus(result: Recommendation, request: RecommendRequest) {
  // Exhaustive over all five statuses — no silent default.
  switch (result.status) {
    case RECOMMENDATION_STATUS.RECOMMENDED:
      return <RecommendedResult result={result} request={request} />;
    case RECOMMENDATION_STATUS.NO_ELIGIBLE_PRODUCTS:
    case RECOMMENDATION_STATUS.NO_FEASIBLE_CANDIDATES:
    case RECOMMENDATION_STATUS.ALL_CANDIDATES_BLOCKED:
    case RECOMMENDATION_STATUS.NO_SUITABLE_LOAN:
      return <NoLoanResult result={result} />;
  }
}

function Footer() {
  return (
    <footer className="mt-2 border-t border-paper-line pt-4 text-xs text-ink-faint">
      This is an illustrative tool, not financial advice, a credit decision, or an offer
      of credit. It runs on synthetic data and the details you enter.
    </footer>
  );
}