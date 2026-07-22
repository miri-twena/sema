import { ArrowDown } from "lucide-react";

/**
 * Floating "back to latest" affordance, shown once the reader has scrolled away
 * from the newest content. Absolutely positioned, so its scroll container must
 * be `relative`.
 */
export function ScrollToLatest({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Scroll to latest"
      title="Scroll to latest"
      className="absolute bottom-4 start-1/2 -translate-x-1/2 rtl:translate-x-1/2 z-20 w-9 h-9 rounded-full bg-surface border border-line shadow-pop text-muted hover:text-ink hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 flex items-center justify-center transition"
    >
      <ArrowDown size={16} />
    </button>
  );
}
