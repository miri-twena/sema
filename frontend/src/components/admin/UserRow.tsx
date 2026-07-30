import { useCallback, useState } from "react";
import { Mail, MoreHorizontal } from "lucide-react";
import type { AdminDataScope, AdminRole, AdminUser } from "../../lib/api";
import { useDismiss } from "../../hooks/useDismiss";
import { initials, pastelFor } from "../../lib/avatar";
import { daysUntil, timeAgo } from "../../lib/time";
import { RoleTooltip, type RoleCatalog } from "./RoleTooltip";
import { ROLE_LABEL } from "./roleLabels";
import { DataScopeControl, type ScopeInfo } from "./DataScopeControl";

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
  return (
    <span className="inline-flex items-center rounded-full bg-warning-bg px-2 py-0.5 text-[0.66rem] font-semibold text-warning-fg">
      Pending
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
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const closeMenu = useCallback(() => {
    setMenuOpen(false);
    setConfirmRemove(false);
  }, []);
  const menuRef = useDismiss<HTMLDivElement>(menuOpen, closeMenu);

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
        aria-label={`View details for ${invited ? user.email : displayName}`}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="truncate font-medium text-ink" dir="auto">
            {invited ? user.email : displayName}
          </span>
          {user.is_self && <span className="shrink-0 text-muted font-normal">(you)</span>}
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
              <span className="text-critical-fg">Invite expired</span>
            ) : (
              <span className="text-muted">
                Invite sent · expires in {daysUntil(user.invite_expires_at)} day
                {daysUntil(user.invite_expires_at) === 1 ? "" : "s"}
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
              {ROLE_LABEL[user.role]}
            </span>
          ) : user.is_self ? (
            <span
              className="text-[0.78rem] text-ink"
              aria-describedby={`role-desc-${user.id}`}
              tabIndex={0}
            >
              {ROLE_LABEL[user.role]}
            </span>
          ) : (
            <select
              value={user.role}
              aria-label={`Role for ${displayName}`}
              aria-describedby={`role-desc-${user.id}`}
              disabled={isLastActiveAdmin}
              title={isLastActiveAdmin ? "The last active admin's role can't be changed." : undefined}
              onChange={(e) => onChangeRole(user.id, e.target.value as AdminRole)}
              className="w-full rounded-lg border border-line bg-surface px-2 py-1 text-[0.78rem] text-ink outline-none focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <option value="client_admin">Admin</option>
              <option value="analyst">Analyst</option>
              <option value="viewer">Viewer</option>
            </select>
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
          <span className="text-warning-fg font-medium">Suspended</span>
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
              Resend
            </button>
            <button
              onClick={() => onRemove(user.id)}
              className="text-[0.75rem] text-muted hover:text-ink"
            >
              Cancel
            </button>
          </>
        ) : user.is_self ? null : (
          <div ref={menuRef} className="relative">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={`Actions for ${displayName}`}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
            >
              <MoreHorizontal size={16} />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute end-0 top-full mt-1 w-44 z-20 rounded-xl border border-line bg-surface shadow-pop p-1"
              >
                <button
                  role="menuitem"
                  onClick={() => {
                    onOpenDetail(user);
                    closeMenu();
                  }}
                  className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt transition"
                >
                  View details
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
                    Reactivate user
                  </button>
                ) : (
                  <button
                    role="menuitem"
                    disabled={isLastActiveAdmin}
                    title={isLastActiveAdmin ? "The last active admin can't be suspended." : undefined}
                    onClick={() => {
                      onSuspend(user.id);
                      closeMenu();
                    }}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-ink hover:bg-surfaceAlt disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
                  >
                    Suspend user
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
                    Click again to remove
                  </button>
                ) : (
                  <button
                    role="menuitem"
                    disabled={isLastActiveAdmin}
                    title={isLastActiveAdmin ? "The last active admin can't be removed." : undefined}
                    onClick={() => setConfirmRemove(true)}
                    className="w-full text-start rounded-lg px-2.5 py-2 text-[0.8rem] text-critical-fg hover:bg-critical-bg disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
                  >
                    Remove from org
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
