import { useCallback, useState } from "react";
import { Info } from "lucide-react";
import type { AdminDataScope } from "../../lib/api";
import { useDismiss } from "../../hooks/useDismiss";
import { useFocusTrap } from "../../hooks/useFocusTrap";

/** Minimal shape this module needs from api.ts's DataScopeInfo -- avoids a
 * circular re-export and keeps this file usable with any object shaped like
 * the catalog entry. */
export interface ScopeInfo {
  id: AdminDataScope;
  label: string;
  description: string;
  included_domains: string[];
  excluded_domains: string[];
  selectable: boolean;
}

/** Distinct muted pill tint per scope (spec: "distinct muted tints") -- the
 * app's pastel accents (mint/sky/sun), not semantic error/warning colors,
 * since a scope is a normal setting, not a status. `custom` (unselectable,
 * V2) uses the plain neutral tint since no user can actually be on it yet. */
const PILL_TINT: Record<AdminDataScope, string> = {
  full: "bg-primary/10 text-primary-dark",
  no_financials: "bg-sky/25 text-ink",
  sales_only: "bg-sun/50 text-ink",
  custom: "bg-surfaceAlt text-faint",
};

function scopeLabel(scopeId: AdminDataScope, scopes: ScopeInfo[]): string {
  return scopes.find((s) => s.id === scopeId)?.label ?? scopeId;
}

/** The "Data access" pill -- same shape whether it's read-only or the
 * trigger for the editor popover below. */
function Pill({ scopeId, scopes }: { scopeId: AdminDataScope; scopes: ScopeInfo[] }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.7rem] font-medium whitespace-nowrap ${PILL_TINT[scopeId] ?? PILL_TINT.custom}`}
    >
      {scopeLabel(scopeId, scopes)}
    </span>
  );
}

/** Included (highlighted) / excluded (muted) domain chips -- shown only for
 * a scope that's genuinely PARTIAL (some domains in, some out): `full` needs
 * no chips (everything's included) and `custom` has no domains to show, so
 * this naturally targets sales_only today without hardcoding its id. */
function DomainChips({ included, excluded }: { included: string[]; excluded: string[] }) {
  if (included.length === 0 && excluded.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {included.map((d) => (
        <span
          key={d}
          className="rounded-full bg-primary/10 text-primary-dark px-1.5 py-0.5 text-[0.62rem] font-medium capitalize"
        >
          {d}
        </span>
      ))}
      {excluded.map((d) => (
        <span
          key={d}
          className="rounded-full bg-surfaceAlt text-faint px-1.5 py-0.5 text-[0.62rem] capitalize"
        >
          {d}
        </span>
      ))}
    </div>
  );
}

/**
 * The "Data access" column header's ⓘ affordance (spec item 8): a compact
 * legend listing every scope with its description -- same click-to-open
 * popover pattern as RoleTooltip's RoleLegend, built from
 * GET /api/admin/data-scopes so the copy is never hardcoded here.
 */
export function DataScopeLegend({ scopes }: { scopes: ScopeInfo[] }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss<HTMLDivElement>(open, close);

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="What is data access?"
        className="w-4 h-4 rounded-full flex items-center justify-center text-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <Info size={12} />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Data access levels"
          className="absolute top-full mt-1.5 start-0 z-30 w-72 max-w-[85vw] rounded-xl border border-line bg-surface shadow-pop p-3 normal-case tracking-normal"
        >
          <div className="flex flex-col gap-2.5">
            {scopes.map((s) => (
              <div key={s.id}>
                <div className="flex items-center gap-1.5 text-[0.78rem] font-semibold text-ink">
                  {s.label}
                  {!s.selectable && (
                    <span className="rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
                      V2
                    </span>
                  )}
                </div>
                <div className="text-[0.72rem] text-muted leading-snug mt-0.5">{s.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}

/**
 * The "Data access" cell (spec items 8-9): a pill that's either a static
 * read-only label (own row, admin rows -- "always full, no edit affordance")
 * or the trigger for a focus-trapped editor popover listing every scope as a
 * radio choice, with domain chips on a partial scope and a disabled "V2" row
 * for `custom`. Mutation is the caller's job (`onChange`) so this component
 * stays presentation-only; UsersScreen/UserDetailDrawer both wire it to the
 * same optimistic-PATCH mutation useAdminUsers exposes.
 */
export function DataScopeControl({
  scopeId,
  scopes,
  readOnly,
  onChange,
}: {
  scopeId: AdminDataScope;
  scopes: ScopeInfo[];
  readOnly: boolean;
  onChange: (scope: AdminDataScope) => void;
}) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss<HTMLDivElement>(open, close);
  useFocusTrap(ref, open);

  if (readOnly) {
    return <Pill scopeId={scopeId} scopes={scopes} />;
  }

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Data access: ${scopeLabel(scopeId, scopes)}. Change`}
        className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <Pill scopeId={scopeId} scopes={scopes} />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Change data access"
          className="absolute top-full mt-1.5 start-0 z-30 w-72 max-w-[85vw] rounded-xl border border-line bg-surface shadow-pop p-2"
        >
          <div role="radiogroup" aria-label="Data access" className="flex flex-col gap-0.5">
            {scopes.map((s) => {
              const selected = s.id === scopeId;
              const isPartial = s.selectable && s.included_domains.length > 0 && s.excluded_domains.length > 0;
              return (
                <label
                  key={s.id}
                  className={`flex items-start gap-2 rounded-lg px-2.5 py-2 text-start transition ${
                    s.selectable ? "cursor-pointer hover:bg-surfaceAlt" : "cursor-not-allowed opacity-60"
                  }`}
                >
                  <input
                    type="radio"
                    name="data-scope"
                    className="mt-0.5 accent-primary"
                    checked={selected}
                    disabled={!s.selectable}
                    onChange={() => {
                      if (!s.selectable) return;
                      onChange(s.id);
                      close();
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[0.8rem] font-medium text-ink">
                      {s.label}
                      {!s.selectable && (
                        <span className="rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
                          V2
                        </span>
                      )}
                    </div>
                    <div className="text-[0.72rem] text-muted leading-snug mt-0.5">{s.description}</div>
                    {isPartial && (
                      <DomainChips included={s.included_domains} excluded={s.excluded_domains} />
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
