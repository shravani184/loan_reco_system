export default function LoadingPanel({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 rounded-md border border-paper-line bg-white p-10 shadow-soft">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-paper-line border-t-brand" aria-hidden="true" />
      <span className="text-sm text-ink-soft">{label}</span>
    </div>
  );
}