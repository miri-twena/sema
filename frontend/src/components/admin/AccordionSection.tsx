import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Collapsible section for the admin editor's settings column (Home-config
 * screen, spec item 11's "four accordion areas"). Same pure-CSS grid
 * collapse technique as SidebarSection (no rAF/height measurement, truly
 * collapses to zero, survives a backgrounded tab), styled for the main
 * content area instead of the sidebar: a real card with a border, a larger
 * heading, and an optional subtitle. `id` is exposed on the header so a
 * caller can scroll/highlight this section (opening an area scrolls the
 * matching preview region, per the spec) by targeting `#home-config-{id}`.
 */
export function AccordionSection({
  id,
  title,
  subtitle,
  open,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div id={`home-config-${id}`} className="rounded-xl border border-line bg-surface overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-start hover:bg-surfaceAlt transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <span className="flex-1 min-w-0">
          <span className="block text-[0.88rem] font-semibold text-ink">{title}</span>
          {subtitle && <span className="block text-[0.75rem] text-muted mt-0.5">{subtitle}</span>}
        </span>
        <ChevronDown
          size={16}
          aria-hidden
          className={`shrink-0 text-faint transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
        />
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: open ? "minmax(0, 1fr)" : "minmax(0, 0fr)" }}
      >
        <div className="overflow-hidden min-h-0" inert={open ? undefined : true} aria-hidden={!open}>
          <div className="px-4 pb-4 pt-1 border-t border-lineSoft">{children}</div>
        </div>
      </div>
    </div>
  );
}
