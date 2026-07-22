import { MessageCircle } from "lucide-react";

/** How many follow-up questions have been asked about a widget -- purely
 * visual, so it is `aria-hidden`; the count is announced via the trigger's own
 * `aria-label` instead (see lib/format.ts's `followUpsLabel`) rather than
 * being read twice. */
export function ThreadBadge({ count, className = "" }: { count: number; className?: string }) {
  if (!count) return null;
  return (
    <span
      aria-hidden="true"
      className={`inline-flex items-center gap-1 shrink-0 rounded-full bg-primary/10 text-primary-dark text-[0.68rem] font-semibold px-1.5 py-0.5 ${className}`}
    >
      <MessageCircle size={11} />
      {count}
    </span>
  );
}
