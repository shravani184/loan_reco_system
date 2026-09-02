export default function SyntheticDataLabel({
  text = "Showing synthetic/example data — not a live credit decision.",
}: {
  text?: string;
}) {
  return (
    <p className="mt-4 text-xs text-ink-faint">
      {text}
    </p>
  );
}