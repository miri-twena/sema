import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

/**
 * A collapsible sidebar category (accordion): a clickable header with the
 * section title, an optional item count, and a chevron on the trailing edge
 * that rotates to indicate open/closed. The body expands/collapses smoothly by
 * animating the grid row between minmax(0,1fr) and minmax(0,0fr) -- a pure-CSS
 * technique (no rAF/height measurement) that truly collapses to zero. A bare
 * `0fr` track floors at the content's min-content and stays open, and a
 * measured-height + requestAnimationFrame approach stalls whenever the tab is
 * backgrounded (rAF pauses); minmax on a grid row has neither problem.
 * Presentational only: the PARENT owns the open state and its persistence, so
 * this one component keeps all three categories (Suggested, Popular, Recent
 * Chats) visually and behaviourally identical.
 *
 * Accessibility: a real <button> header carries aria-expanded and gets Enter/
 * Space + a visible focus ring for free; the collapsed body is marked inert +
 * aria-hidden so its controls leave the tab order and a11y tree, and state is
 * signalled by the rotating chevron (not colour alone).
 */
export function SidebarSection({
  title,
  count,
  open,
  onToggle,
  children,
}: {
  title: string;
  /** Optional item count shown as a subtle badge before the chevron. */
  count?: number;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-1 py-1 rounded-lg text-[0.72rem] font-semibold uppercase tracking-wide text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <span className="truncate text-start">{title}</span>
        {typeof count === "number" && (
          <span className="ms-auto shrink-0 text-[0.68rem] font-medium text-faint tabular-nums">
            {count}
          </span>
        )}
        <ChevronDown
          size={14}
          aria-hidden
          className={`shrink-0 text-faint transition-transform duration-200 ${
            open ? "" : "-rotate-90"
          } ${typeof count === "number" ? "" : "ms-auto"}`}
        />
      </button>
      {/* minmax(0,1fr) <-> minmax(0,0fr) animates the row height smoothly and
          truly collapses to zero; overflow-hidden clips the body (padding
          included) so a collapsed section leaves no empty gap. */}
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: open ? "minmax(0, 1fr)" : "minmax(0, 0fr)" }}
      >
        <div className="overflow-hidden min-h-0" inert={open ? undefined : true} aria-hidden={!open}>
          <div className="pt-1.5">{children}</div>
        </div>
      </div>
    </div>
  );
}
