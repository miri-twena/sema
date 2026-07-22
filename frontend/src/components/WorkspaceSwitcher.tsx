import { useCallback, useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import type { Client } from "../lib/api";
import { useDismiss } from "../hooks/useDismiss";

/** First letters of the first two words: "Auto Insurance" -> "AI". Falls back
 * to the first character so a single-word label still renders something. */
function initials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

/**
 * The sidebar's bottom block: which workspace (client) you're in, whether its
 * database is reachable, and a popover to switch. Replaces the header's
 * `<select>` + status dot -- identity and connection now live together at the
 * bottom of the nav, the shape most tools use.
 *
 * Present in the mobile drawer too, since the drawer renders the same sidebar.
 */
export function WorkspaceSwitcher({
  clients,
  activeId,
  dbConnected,
  onSwitch,
}: {
  clients: Client[];
  activeId: string;
  dbConnected: boolean;
  onSwitch: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss<HTMLDivElement>(open, close);

  const active = clients.find((c) => c.id === activeId);
  const label = active?.label ?? "Workspace";

  return (
    <div ref={ref} className="relative shrink-0 border-t border-line p-3">
      {open && (
        <div
          role="listbox"
          aria-label="Switch workspace"
          className="absolute bottom-[calc(100%-4px)] start-3 end-3 z-30 rounded-xl2 border border-line bg-surface shadow-pop p-1"
        >
          {clients.map((c) => (
            <button
              key={c.id}
              type="button"
              role="option"
              aria-selected={c.id === activeId}
              onClick={() => {
                if (c.id !== activeId) onSwitch(c.id);
                close();
              }}
              className="w-full text-start flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.85rem] text-ink hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
            >
              <span className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-md bg-primary/10 text-primary-dark text-[0.65rem] font-semibold">
                {initials(c.label)}
              </span>
              <span className="truncate flex-1" dir="auto">
                {c.label}
              </span>
              {c.id === activeId && <Check size={14} className="shrink-0 text-primary" aria-hidden />}
            </button>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Workspace: ${label}. Switch workspace`}
        className="w-full flex items-center gap-2.5 rounded-xl px-2 py-2 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <span
          aria-hidden
          className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary-dark text-[0.7rem] font-semibold"
        >
          {initials(label)}
        </span>
        <span className="min-w-0 flex-1 text-start">
          <span className="block truncate text-[0.85rem] font-medium text-ink" dir="auto">
            {label}
          </span>
          {/* Status is a dot PLUS a word -- colour alone would not be readable
              for a colour-blind user. */}
          <span className="flex items-center gap-1.5 text-[0.7rem] text-muted">
            <span
              aria-hidden
              className={`w-1.5 h-1.5 rounded-full ${dbConnected ? "bg-emerald-500" : "bg-red-500"}`}
            />
            {dbConnected ? "Connected" : "Disconnected"}
          </span>
        </span>
        <ChevronsUpDown size={15} className="shrink-0 text-faint" aria-hidden />
      </button>
    </div>
  );
}
