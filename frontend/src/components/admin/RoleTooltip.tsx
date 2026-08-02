import { useState, type ReactNode } from "react";
import { Info } from "lucide-react";
import type { AdminRole, RoleInfo } from "../../lib/api";
import { usePopoverMenu } from "../../hooks/usePopoverMenu";
import { PopoverMenu } from "../PopoverMenu";

const LEGEND_WIDTH = 288; // w-72
const LEGEND_EST_HEIGHT = 220;

/** Roles keyed by id, for O(1) lookup from a row's current role. */
export type RoleCatalog = Partial<Record<AdminRole, RoleInfo>>;

/**
 * Wraps a role control (select or static label) with an accessible
 * description bubble shown on hover OR keyboard focus -- native `title`
 * isn't reliably announced by screen readers and can't be styled, so this is
 * a small custom tooltip. `onFocus`/`onBlur` on the wrapper catch focus
 * bubbling from the child control (React's synthetic focus/blur events
 * bubble), so one pair of handlers covers both hover and keyboard focus. The
 * bubble is ALWAYS mounted (never conditionally rendered) so
 * `aria-describedby` on the child never points at a momentarily-missing id;
 * `pointer-events-none` keeps it out of the way since it's purely
 * informational.
 */
export function RoleTooltip({
  id,
  role,
  roles,
  children,
}: {
  /** Must match the `aria-describedby` the caller sets on the actual control. */
  id: string;
  role: AdminRole;
  roles: RoleCatalog | null;
  children: ReactNode;
}) {
  const [show, setShow] = useState(false);
  const description = roles?.[role]?.description ?? "";
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {children}
      <span
        role="tooltip"
        id={id}
        className={`pointer-events-none absolute z-30 w-56 rounded-lg border border-line bg-surface shadow-pop px-2.5 py-2 text-[0.72rem] leading-snug text-ink transition-opacity bottom-full mb-1.5 start-0 ${
          show ? "opacity-100" : "opacity-0"
        }`}
      >
        {description}
      </span>
    </span>
  );
}

/**
 * The "Role" column header's ⓘ affordance: a click-to-open popover listing
 * every role with its description (spec: Analyst/Viewer parity note lives in
 * the description text itself, from GET /api/admin/roles -- never hardcoded
 * here). A click-triggered popover (vs. a hover tooltip) so it's reliably
 * reachable by touch and keyboard alike, dismissed via useDismiss the same
 * way every other popover in the admin panel is.
 */
export function RoleLegend({ roles }: { roles: RoleInfo[] }) {
  const { open, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLButtonElement>({
    width: LEGEND_WIDTH,
    estHeight: LEGEND_EST_HEIGHT,
    align: "start",
  });

  return (
    <span className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="What can each role do?"
        className="w-4 h-4 rounded-full flex items-center justify-center text-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <Info size={12} />
      </button>
      {open && (
        <PopoverMenu
          pos={pos}
          menuRef={menuRef}
          role="dialog"
          ariaLabel="Role descriptions"
          className="rounded-xl max-w-[85vw] p-3 normal-case tracking-normal"
        >
          <div className="flex flex-col gap-2.5">
            {roles.map((r) => (
              <div key={r.id}>
                <div className="text-[0.78rem] font-semibold text-ink">{r.label}</div>
                <div className="text-[0.72rem] text-muted leading-snug mt-0.5">{r.description}</div>
              </div>
            ))}
          </div>
        </PopoverMenu>
      )}
    </span>
  );
}
