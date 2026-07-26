/**
 * A question rendered as a pill: neutral surface, optional count badge in the
 * accent tint. Used by the home screen's "Trending in your company".
 *
 * `dir="auto"` because a question may be Hebrew or English regardless of the
 * surrounding card's direction.
 */
export function QuestionChip({
  question,
  count,
  onPick,
}: {
  question: string;
  /** Times asked; omitted where a count would be noise. */
  count?: number;
  onPick: (q: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(question)}
      title={question}
      dir="auto"
      className="group inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-surface ps-3.5 pe-2.5 py-1.5 text-sm text-ink hover:border-primary hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
    >
      <span className="truncate">{question}</span>
      {typeof count === "number" && (
        <span className="shrink-0 rounded-full bg-primary/10 text-primary-dark text-[0.68rem] font-semibold px-1.5 py-0.5 tabular-nums">
          {count}×
        </span>
      )}
    </button>
  );
}
