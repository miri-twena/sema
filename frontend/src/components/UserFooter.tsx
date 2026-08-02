import { useEffect, useState } from "react";
import { LogOut, MoreHorizontal } from "lucide-react";
import { api, type AdminUser } from "../lib/api";
import { usePopoverMenu } from "../hooks/usePopoverMenu";
import { initials, pastelFor } from "../lib/avatar";
import { useT } from "../locales";
import { PopoverMenu } from "./PopoverMenu";

const MENU_EST_HEIGHT = 110;

/**
 * Sidebar footer's second row (login spec v1.4 §4, approved mockup): who's
 * signed in, server-reported via the existing `/api/admin/me` (NOT
 * hardcoded), with a menu for personal settings (placeholder, real auth
 * lands in Part A) and logout (placeholder loop to /login until then).
 * Renders nothing if the mock identity doesn't resolve to an admin row for
 * this client (e.g. a client with no admin panel seeded yet) -- same
 * graceful-degradation rule the admin panel's own routes already follow.
 */
export function UserFooter() {
  const [me, setMe] = useState<AdminUser | null>(null);
  const t = useT();
  const { open, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLDivElement>({
    width: "trigger",
    estHeight: MENU_EST_HEIGHT,
    align: "start",
    placement: "above",
  });

  useEffect(() => {
    let cancelled = false;
    api.admin
      .me()
      .then((u) => !cancelled && setMe(u))
      .catch(() => !cancelled && setMe(null));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!me) return null;

  const name = me.name || me.email;
  const role = t.common.roles[me.role] ?? me.role;
  const [bg, fg] = pastelFor(me.email);

  return (
    <div ref={triggerRef} className="relative shrink-0 border-t border-line p-3">
      {open && (
        <PopoverMenu pos={pos} menuRef={menuRef} className="rounded-xl2 p-1">
          <div
            role="menuitem"
            aria-disabled="true"
            title={t.common.comingSoon}
            className="w-full flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-[0.85rem] text-faint cursor-default select-none"
          >
            {t.userMenu.personalSettings}
            <span className="shrink-0 rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
              {t.common.comingSoon}
            </span>
          </div>
          <div className="my-1 border-t border-lineSoft" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              window.location.href = "/login";
            }}
            className="w-full text-start flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.85rem] text-critical-fg hover:bg-critical-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
          >
            <LogOut size={15} className="shrink-0" />
            {t.userMenu.logOut}
          </button>
        </PopoverMenu>
      )}

      <button
        type="button"
        onClick={toggle}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${name}. ${role}`}
        className="w-full flex items-center gap-2.5 rounded-xl px-2 py-2 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <span
          aria-hidden
          className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-[0.7rem] font-semibold"
          style={{ background: bg, color: fg }}
        >
          {initials(name)}
        </span>
        <span className="min-w-0 flex-1 text-start">
          <span className="block truncate text-[0.85rem] font-medium text-ink" dir="auto">
            {name}
          </span>
          <span className="block truncate text-[0.7rem] text-muted">{role}</span>
        </span>
        <MoreHorizontal size={15} className="shrink-0 text-faint" aria-hidden />
      </button>
    </div>
  );
}
