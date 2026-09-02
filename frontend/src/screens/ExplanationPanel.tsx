import { useEffect, useState } from "react";
import type {
  ExplanationResponse,
  FeatureContribution,
  Recommendation,
  RecommendRequest,
} from "../types";
import { explain } from "../api/client";
import LoadingPanel from "../components/LoadingPanel";
import ErrorPanel from "../components/ErrorPanel";

export default function ExplanationPanel({
  result,
  request,
}: {
  result: Recommendation;
  request: RecommendRequest;
}) {
  const [data, setData] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setData(null);
    explain({ ...request, question: null })
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "Explanation unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [result, request]);

  return (
    <div className="card card-pad card-accent">
      <h3 className="text-base font-semibold text-ink">Why this loan</h3>
      {loading ? (
        <LoadingPanel label="Building your explanation…" />
      ) : error ? (
        <ErrorPanel message={error} />
      ) : data ? (
        <div className="mt-3 space-y-4">
          <p className="text-sm leading-relaxed text-ink-soft">{data.explanation.text}</p>
          <div className="text-xs text-ink-faint">
            Explanation:{" "}
            <span className="font-medium text-ink-soft">
              {data.explanation.source}{" "}
              {data.explanation.degraded_reason ? `(${data.explanation.degraded_reason})` : ""}
            </span>
          </div>
          <TopFactors xai={data.xai} />
        </div>
      ) : null}
    </div>
  );
}

function TopFactors({ xai }: { xai: ExplanationResponse["xai"] }) {
  const positive = xai.contributions
    .filter((c) => c.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, 3);
  const negative = xai.contributions
    .filter((c) => c.contribution < 0)
    .sort((a, b) => a.contribution - b.contribution)
    .slice(0, 3);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {positive.length ? (
        <FactorGroup title="What is pushing toward it" tone="good" items={positive} />
      ) : null}
      {negative.length ? (
        <FactorGroup title="What is pulling against it" tone="bad" items={negative} />
      ) : null}
    </div>
  );
}

function FactorGroup({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "good" | "bad";
  items: FeatureContribution[];
}) {
  const sign = (v: number) => (v >= 0 ? "+" : "");
  const maxAbs = Math.max(...items.map((i) => Math.abs(i.contribution)), 0.0001);
  return (
    <div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      <ul className="mt-2 space-y-1.5">
        {items.map((c) => (
          <li key={c.feature} className="text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="truncate text-ink-soft">{prettyFeature(c.feature)}</span>
              <span
                className={`shrink-0 font-mono text-xs font-medium ${
                  tone === "good" ? "text-emerald-700" : "text-red-600"
                }`}
              >
                {sign(c.contribution)}
                {c.contribution.toFixed(3)}
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-paper">
              <div
                className={`h-full rounded-full ${
                  tone === "good" ? "bg-emerald-500" : "bg-red-400"
                }`}
                style={{ width: `${(Math.abs(c.contribution) / maxAbs) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function prettyFeature(feature: string): string {
  return feature.replace(/_/g, " ").toLowerCase();
}