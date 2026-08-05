import { useState } from "react";
import { Mail, MoreHorizontal, UserRoundCog } from "lucide-react";
import type { AdminDataScope, AdminRole, AdminUser } from "../../lib/api";
import { usePopoverMenu } from "../../hooks/usePopoverMenu";
import { initials, pastelFor } from "../../lib/avatar";
import { daysUntil, timeAgo } from "../../lib/time";
import { useT } from "../../locales";
import { PopoverMenu } from "../PopoverMenu";
import { RoleTooltip, type RoleCatalog } from "./RoleTooltip";
import { DataScopeControl, type ScopeInfo } from "./DataScopeControl";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "../../lib/tokens";

// Matches the menu's own `w-44` (11rem).
const MENU_WIDTH = 176;
const MENU_EST_HEIGHT = 190;

/** Role -> identity hue index (lavender for admin, sky for analyst, mint for
 * viewer) -- the same palette KPI cards/chart bars/tables use, so a role's
 * color carries meaning consistently across the app. */
const ROLE_HUE: Record<AdminRole, number> = { client_admin: 0, analyst: 2, viewer: 1 };

/** Small avatar: initials on a deterministic pastel for real users, an
 * envelope for pending invites (which have no name yet). 32px per the mockup. */
function Avatar({ user }: { user: AdminUser }) {
  if (user.status === "invited") {
    return (
      <span
        aria-hidden
        className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full bg-surfaceAlt text-faint"
      >
        <Mail size={15} />
      </span>
    );
  }
  const [bg, fg] = pastelFor(user.email);
  return (
    <span
      aria-hidden
      className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-[0.72rem] font-semibold"
      style={{ background: bg, color: fg }}
    >
      {initials(user.name || user.email)}
    </span>
  );
}

/** Pending badge shown on invited rows. */
function PendingBadge() {
  const t = useT();
  return (
    <span className="inline-flex items-center rounded-full bg-warning-bg px-2 py-0.5 text-[0.66rem] font-semibold text-warning-fg">
      {t.admin.users.pending}
    </span>
  );
}

/**
 * One row in the users table (spec §6.1). Flat layout, hairline divider from
 * the container. Three shapes share it:
 *  - active/suspended user: role select + last-active + kebab (suspend/remove).
 *  - the current user ("you"): role shown as static text, no select, no kebab.
 *  - invited user: invite status + Pending badge + Resend/Cancel text actions.
 * The last active admin's mutating controls are disabled (the server also
 * guards this with a 409 -- the UI just avoids offering a doomed action).
 */
export function UserRow({
  user,
  isLastActiveAdmin,
  roles,
  dataScopes,
  onChangeRole,
  onChangeDataScope,
  onSuspend,
  onReactivate,
  onRemove,
  onResend,
  onOpenDetail,
  onViewAsUser,
}: {
  user: AdminUser;
  isLastActiveAdmin: boolean;
  roles: RoleCatalog | null;
  dataScopes: ScopeInfo[];
  onChangeRole: (id: string, role: AdminRole) => void;
  onChangeDataScope: (id: string, scope: AdminDataScope) => void;
  onSuspend: (id: string) => void;
  onReactivate: (id: string) => void;
  onRemove: (id: string) => void;
  onResend: (id: string) => void;
  onOpenDetail: (user: AdminUser) => void;
  /** "View as user" (impersonation_prompt.md) -- omitted entirely on the
   * current user's own row (hidden on self, per spec); every other eligible
   * row gets it, disabled with a tooltip for suspended/invited targets. */
  onViewAsUser: (id: string) => void;
}) {
  const t = useT();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const { open: menuOpen, close: closeMenuPos, toggle, triggerRef, menuRef, pos } = usePopoverMenu<HTMLButtonElement>({
    width: MENU_WIDTH,
    estHeight: MENU_EST_HEIGHT,
  });
  const closeMenu = () => {
    closeMenuPos();
    setConfirmRemove(false);
  };

  const invited = user.status === "invited";
  const suspended = user.status === "suspended";
  const displayName = user.name || user.email;

  return (
    <div className="flex items-center gap-3 px-2 py-2.5 text-[0.82rem] hover:bg-surfaceAlt/60 transition rounded-lg">
      <Avatar user={user} />

      {/* Identity: name + muted title on one line, email below. Its own
          button (not the whole row) so it doesn't fight the role select/kebab
          for clicks -- opens the detail drawer. */}
      <button
        type="button"
        onClick={() => onOpenDetail(user)}
        className="min-w-0 flex-1 text-start rounded-lg -m-1 p-1 hover:bg-surfaceAlt/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
        aria-label={t.admin.users.viewDetailsForLabel(invited ? user.email : displayName)}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="truncate font-medium text-ink" dir="auto">
            {invited ? user.email : displayName}
          </span>
          {user.is_self && <span className="shrink-0 text-muted font-normal">{t.admin.users.youSuffix}</span>}
          {user.title && !invited && (
            <span className="truncate text-muted font-normal" dir="auto">
              · {user.title}
            </span>
          )}
        </div>
        {!invited && (
          <div className="truncate text-[0.75rem] text-muted" dir="auto">
            {user.email}
          </div>
        )}
        {invited && (
          <div className="text-[0.75rem]">
            {user.invite_expired ? (
              <span className="text-critical-fg">{t.admin.users.inviteExpired}</span>
            ) : (
              <span className="text-muted">
                {t.admin.users.inviteSentExpiresIn(daysUntil(user.invite_expires_at))}
              </span>
            )}
          </div>
        )}
      </button>

      {/* Role. Static text for the current user and for invites; an inline
          select otherwise (disabled for the last active admin -- downgrading
          would be refused). Wrapped in RoleTooltip so hovering/focusing shows
          the role's capability description (spec: column-header legend +
          per-row tooltip share the same GET /api/admin/roles copy). */}
      <div className="shrink-0 w-28">
        <RoleTooltip id={`role-desc-${user.id}`} role={user.role} roles={roles}>
          {invited ? (
            <span
              className="text-[0.75rem] text-muted"
              aria-describedby={`role-desc-${user.id}`}
              tabIndex={0}
            >
              {t.common.roles[user.role]}
            </span>
          ) : user.is_self ? (
            <span
              className="text-[0.78rem] text-ink"
              aria-describedby={`role-desc-${user.id}`}
              tabIndex={0}
            >
              {t.common.roles[user.role]}
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <span
                className="shrink-0 inline-block w-[6px] h-[6px] rounded-[2px]"
                style={{ background: CHART_PALETTE[ROLE_HUE[user.role]] }}
                aria-hidden
              />
              <select
                value={user.role}
                aria-label={t.admin.users.roleForLabel(displayName)}
                aria-describedby={`role-desc-${user.id}`}
                disabled={isLastActiveAdmin}
                title={isLastActiveAdmin ? t.admin.users.lastAdminRoleLocked : undefined}
                onChange={(e) => onChangeRole(user.id, e.target.value as AdminRole)}
                style={{
                  borderColor: `${CHART_PALETTE[ROLE_HUE[user.role]]}66`,
                  background: `${CHART_PALETTE[ROLE_HUE[user.role]]}1A`,
                  color: CHART_PALETTE_TEXT[ROLE_HUE[user.role]],
                }}
                className="flex-1 min-w-0 rounded-lg border px-2 py-1 text-[0.78rem] outline-none focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                <option value="client_admin">{t.common.roles.client_admin}</option>
                <option value="analyst">{t.common.roles.analyst}</option>
                <option value="viewer">{t.common.roles.viewer}</option>
              </select>
            </span>
          )}
        </RoleTooltip>
      </div>

      {/* Data access. Read-only for the current user and for admins (always
          full) -- otherwise an editable pill opening the scope popover. */}
      <div className="shrink-0 w-28">
        <DataScopeControl
          scopeId={user.data_scope}
          scopes={dataScopes}
          readOnly={user.is_self || user.role === "client_admin"}
          onChange={(scope) => onChangeDataScope(user.id, scope)}
        />
      </div>

      {/* Status / last active. */}
      <div className="shrink-0 w-32 text-[0.75rem]">
        {invited ? (
          <PendingBadge />
        ) : suspended ? (
          <span className="text-warning-fg font-medium">{t.admin.users.suspendedStatus}</span>
        ) : (
          <span className="text-muted">{timeAgo(user.last_active_at)}</span>
        )}
      </div>

      {/* Actions. Invited rows get inline Resend/Cancel; real users get a kebab
          (suspend/reactivate + remove). The current user gets neither. */}
      <div className="shrink-0 w-24 flex items-center justify-end gap-2">
        {invited ? (
          <>
            <button
              onClick={() => onResend(user.id)}
              className="text-[0.75rem] font-medium text-primary hover:underline"
            >
              {t.admin.users.resend}
            </button>
            <button
              onClick={() => onRemove(user.id)}
              className="text-[0.75rem] text-muted hover:text-ink"
            >
              {t.common.cancel}
            </button>
            {/* Disabled, with a tooltip -- an invited user can't sign in
                themselves yet, so there's no "their app" to view as. */}
            <button
              type="button"
              disabled
              title={t.admin.users.cannotViewAsInvited}
              aria-label={t.admin.users.viewAsUserForLabel(user.email)}
              className="text-muted/50 cursor-not-allowed"
            >
              <UserRoundCog size={15} />
            </button>
          </>
        ) : user.is_self ? null : (
          <div className="relative">
            <button
              ref={triggerRef}
              onClick={toggle}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={t.admin.users.actionsLabel(displayName)}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
            >
              <MoreHorizontal size={16} />
            </button>
            {menuOpen && (
              <PopoverMenu pos={pos} menuRef={menuRef} className="rounded-xl p-1">
                <button
                  role="menuitem"
                  disabled={suspended}
                  title={suspended ? t.admin.users.cannotViewAsSuspended : undefined}
                  onClick={() => {
                    onViewAsUser(user.id);
                    closeMenu();
                  }}
                  className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
                >
                  {t.admin.users.viewAsUser}
                </button>
                <button
                  role="menuitem"
                  onClick={() => {
                    onOpenDetail(user);
                    closeMenu();
                  }}
                  className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt transition"
                >
                  {t.admin.users.viewDetails}
                </button>
                {suspended ? (
                  <button
                    role="menuitem"
                    onClick={() => {
                      onReactivate(user.id);
                      closeMenu();
                    }}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt transition"
                  >
                    {t.admin.users.reactivateUser}
                  </button>
                ) : (
                  <button
                    role="menuitem"
                    disabled={isLastActiveAdmin}
                    title={isLastActiveAdmin ? t.admin.users.lastAdminSuspendLocked : undefined}
                    onClick={() => {
                      onSuspend(user.id);
                      closeMenu();
                    }}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
                  >
                    {t.admin.users.suspendUser}
                  </button>
                )}

                {confirmRemove ? (
                  <button
                    role="menuitem"
                    onClick={() => {
                      onRemove(user.id);
                      closeMenu();
                    }}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] font-medium text-critical-fg hover:bg-critical-bg transition"
                  >
                    {t.admin.users.clickAgainToRemove}
                  </button>
                ) : (
                  <button
                    role="menuitem"
                    disabled={isLastActiveAdmin}
                    title={isLastActiveAdmin ? t.admin.users.lastAdminRemoveLocked : undefined}
                    onClick={() => setConfirmRemove(true)}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-critical-fg hover:bg-critical-bg disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
                  >
                    {t.admin.users.removeFromOrg}
                  </button>
                )}
              </PopoverMenu>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
