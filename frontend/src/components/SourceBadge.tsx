import type { RecommendationSource } from "../types";

export default function SourceBadge({ source }: { source: RecommendationSource }) {
  if (source === "ML_RANKER") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-tint px-2.5 py-1 text-xs font-medium text-brand-dark">
        <span aria-hidden="true">ML</span>
        model matched your profile
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800">
      <span aria-hidden="true">~</span>
      used the fallback — model unavailable
    </span>
  );
}
