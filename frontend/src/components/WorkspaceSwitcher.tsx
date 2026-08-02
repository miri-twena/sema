import { Building2, Check, ChevronsUpDown, Settings } from "lucide-react";
import type { Client } from "../lib/api";
import { usePopoverMenu } from "../hooks/usePopoverMenu";
import { initials } from "../lib/avatar";
import { useT } from "../locales";
import { PopoverMenu } from "./PopoverMenu";

const SWITCHER_EST_HEIGHT = 140;
const GEAR_MENU_WIDTH = 208; // min-w-[13rem]
const GEAR_MENU_EST_HEIGHT = 110;

/**
 * The sidebar's bottom block: which workspace (client) you're in, whether its
 * database is reachable, and a popover to switch. Replaces the header's
 * `<select>` + status dot -- identity and connection now live together at the
 * bottom of the nav, the shape most tools use.
 *
 * A gear beside the switcher opens the organization admin panel (spec §4's
 * entry point). Present in the mobile drawer too, since the drawer renders the
 * same sidebar.
 */
export function WorkspaceSwitcher({
  clients,
  activeId,
  dbConnected,
  logoUrl,
  onSwitch,
  onOpenAdmin,
}: {
  clients: Client[];
  activeId: string;
  dbConnected: boolean;
  /** The active client's uploaded logo (org settings §2), or null/undefined
   * to fall back to the initials avatar. */
  logoUrl?: string | null;
  onSwitch: (id: string) => void;
  /** Open the client admin panel (spec §6.1). */
  onOpenAdmin?: () => void;
}) {
  const { open, close, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLDivElement>({
    width: "trigger",
    estHeight: SWITCHER_EST_HEIGHT,
    align: "start",
    placement: "above",
  });

  const {
    open: gearOpen,
    close: closeGear,
    toggle: toggleGear,
    triggerRef: gearTriggerRef,
    menuRef: gearMenuRef,
    pos: gearPos,
  } = usePopoverMenu<HTMLButtonElement>({
    width: GEAR_MENU_WIDTH,
    estHeight: GEAR_MENU_EST_HEIGHT,
    placement: "above",
  });

  const t = useT();

  const active = clients.find((c) => c.id === activeId);
  const label = active?.label ?? t.workspace.fallbackLabel;

  return (
    <div ref={triggerRef} className="relative shrink-0 border-t border-line p-3">
      {open && (
        <PopoverMenu
          pos={pos}
          menuRef={menuRef}
          role="listbox"
          ariaLabel={t.workspace.switchWorkspace}
          className="rounded-xl2 p-1"
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
        </PopoverMenu>
      )}

      {/* Switcher trigger + a gear that enters the admin panel, side by side. */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={toggle}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t.workspace.switchWorkspaceLabel(label)}
          className="flex-1 min-w-0 flex items-center gap-2.5 rounded-xl px-2 py-2 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
        >
          {logoUrl ? (
            <img
              src={logoUrl}
              alt=""
              aria-hidden
              className="shrink-0 w-8 h-8 rounded-lg object-contain bg-surfaceAlt"
            />
          ) : (
            <span
              aria-hidden
              className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary-dark text-[0.7rem] font-semibold"
            >
              {initials(label)}
            </span>
          )}
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
              {dbConnected ? t.workspace.connected : t.workspace.disconnected}
            </span>
          </span>
          <ChevronsUpDown size={15} className="shrink-0 text-faint" aria-hidden />
        </button>

        {onOpenAdmin && (
          <div className="relative shrink-0">
            {gearOpen && (
              <PopoverMenu
                pos={gearPos}
                menuRef={gearMenuRef}
                ariaLabel={t.workspace.adminMenuAriaLabel}
                className="rounded-xl2 p-1"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    closeGear();
                    onOpenAdmin();
                  }}
                  className="w-full text-start flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.85rem] text-ink hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
                >
                  <Building2 size={15} className="shrink-0 text-muted" />
                  {t.workspace.gear.manageOrg}
                </button>
                <div
                  role="menuitem"
                  aria-disabled="true"
                  title={t.common.comingSoon}
                  className="w-full flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-[0.85rem] text-faint cursor-default select-none"
                >
                  {t.workspace.gear.platformConsole}
                  <span className="shrink-0 rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
                    {t.common.comingSoon}
                  </span>
                </div>
              </PopoverMenu>
            )}
            <button
              ref={gearTriggerRef}
              type="button"
              onClick={toggleGear}
              aria-haspopup="menu"
              aria-expanded={gearOpen}
              aria-label={t.workspace.adminMenuLabel}
              title={t.workspace.adminMenuLabel}
              className="w-9 h-9 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
            >
              <Settings size={17} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
