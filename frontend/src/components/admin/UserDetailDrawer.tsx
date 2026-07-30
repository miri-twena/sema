import { useEffect } from "react";
import { X } from "lucide-react";
import type { AdminDataScope, AdminRole, AdminUser } from "../../lib/api";
import { useDismiss } from "../../hooks/useDismiss";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { initials, pastelFor } from "../../lib/avatar";
import { timeAgo } from "../../lib/time";
import { ROLE_LABEL } from "./roleLabels";
import { RoleTooltip, type RoleCatalog } from "./RoleTooltip";
import { DataScopeControl, type ScopeInfo } from "./DataScopeControl";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** "Invited by" per spec: the resolved inviter name; "Founding member" when
 * there was no inviter at all; "—" when there WAS one but they no longer
 * resolve (e.g. since removed from the org). */
function invitedByLabel(user: AdminUser): string {
  if (!user.invited_by) return "Founding member";
  return user.invited_by_name ?? "—";
}

/** "Joined on" per spec: formatted joined_at, or -- for a still-pending
 * invite -- "Not joined yet · invited {relative}". */
function joinedOnLabel(user: AdminUser): string {
  if (user.joined_at) return formatDate(user.joined_at);
  if (user.status === "invited") return `Not joined yet · invited ${timeAgo(user.invited_at)}`;
  return "—";
}

/**
 * Right-side user profile drawer (spec §6.1): full read-only profile plus
 * the same live role/status controls the row offers. Edge-anchored overlay
 * mirroring HistorySlideOver.tsx's skeleton (backdrop + useDismiss + Escape),
 * plus useFocusTrap for keyboard users -- the one thing that pattern doesn't
 * already provide.
 */
export function UserDetailDrawer({
  user,
  isLastActiveAdmin,
  roles,
  dataScopes,
  onClose,
  onChangeRole,
  onChangeDataScope,
  onSuspend,
  onReactivate,
}: {
  user: AdminUser;
  isLastActiveAdmin: boolean;
  roles: RoleCatalog | null;
  dataScopes: ScopeInfo[];
  onClose: () => void;
  onChangeRole: (id: string, role: AdminRole) => void;
  onChangeDataScope: (id: string, scope: AdminDataScope) => void;
  onSuspend: (id: string) => void;
  onReactivate: (id: string) => void;
}) {
  const ref = useDismiss<HTMLElement>(true, onClose);
  useFocusTrap(ref, true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const invited = user.status === "invited";
  const suspended = user.status === "suspended";
  const displayName = user.name || user.email;
  const [bg, fg] = pastelFor(user.email);

  return (
    <>
      <div
        className="fixed inset-0 bg-ink/20 z-40 animate-[sema-fade-in_0.2s_ease-out]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-detail-name"
        className="fixed top-0 end-0 h-full w-[380px] max-w-[92vw] bg-bg border-s border-line shadow-pop z-50 flex flex-col animate-[sema-slide-in-end_0.2s_ease-out]"
      >
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
            User profile
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-auto sema-scroll px-5 py-5">
          <div className="flex items-center gap-3">
            <span
              aria-hidden
              className="shrink-0 inline-flex items-center justify-center w-12 h-12 rounded-full text-[0.95rem] font-semibold"
              style={{ background: bg, color: fg }}
            >
              {initials(user.name || user.email)}
            </span>
            <div className="min-w-0">
              <div id="user-detail-name" className="text-base font-semibold text-ink truncate" dir="auto">
                {displayName}
                {user.is_self && <span className="ms-1.5 text-muted font-normal">(you)</span>}
              </div>
              {user.title && (
                <div className="text-[0.8rem] text-muted truncate" dir="auto">
                  {user.title}
                </div>
              )}
            </div>
          </div>

          <div className="mt-2 text-[0.82rem] text-muted truncate" dir="auto">
            {user.email}
          </div>

          <dl className="mt-5 flex flex-col gap-4">
            <div>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Role
              </dt>
              <dd>
                {user.is_self ? (
                  <span className="text-[0.85rem] text-ink">{ROLE_LABEL[user.role]}</span>
                ) : (
                  <RoleTooltip id="user-detail-role-desc" role={user.role} roles={roles}>
                    <select
                      value={user.role}
                      aria-label={`Role for ${displayName}`}
                      aria-describedby="user-detail-role-desc"
                      disabled={isLastActiveAdmin}
                      onChange={(e) => onChangeRole(user.id, e.target.value as AdminRole)}
                      className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.85rem] text-ink outline-none focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed transition"
                    >
                      <option value="client_admin">Admin</option>
                      <option value="analyst">Analyst</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </RoleTooltip>
                )}
              </dd>
            </div>

            <div>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Data access
              </dt>
              <dd>
                <DataScopeControl
                  scopeId={user.data_scope}
                  scopes={dataScopes}
                  readOnly={user.is_self || user.role === "client_admin"}
                  onChange={(scope) => onChangeDataScope(user.id, scope)}
                />
              </dd>
            </div>

            <div>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Status
              </dt>
              <dd className="flex items-center gap-2.5">
                {invited ? (
                  <span className="inline-flex items-center rounded-full bg-warning-bg px-2 py-0.5 text-[0.7rem] font-semibold text-warning-fg">
                    Pending
                  </span>
                ) : suspended ? (
                  <span className="text-[0.85rem] font-medium text-warning-fg">Suspended</span>
                ) : (
                  <span className="text-[0.85rem] text-ink">Active</span>
                )}
                {!invited && !user.is_self && (
                  <button
                    onClick={() =>
                      suspended ? onReactivate(user.id) : onSuspend(user.id)
                    }
                    disabled={!suspended && isLastActiveAdmin}
                    title={
                      !suspended && isLastActiveAdmin
                        ? "The last active admin can't be suspended."
                        : undefined
                    }
                    className="text-[0.78rem] font-medium text-primary hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline transition"
                  >
                    {suspended ? "Reactivate" : "Suspend"}
                  </button>
                )}
              </dd>
            </div>

            {!invited && (
              <div>
                <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                  Last active
                </dt>
                <dd className="text-[0.85rem] text-ink">{timeAgo(user.last_active_at)}</dd>
              </div>
            )}

            <div>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Invited by
              </dt>
              <dd className="text-[0.85rem] text-ink" dir="auto">
                {invitedByLabel(user)}
              </dd>
            </div>

            <div>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                Joined on
              </dt>
              <dd className="text-[0.85rem] text-ink">{joinedOnLabel(user)}</dd>
            </div>
          </dl>

          {isLastActiveAdmin && (
            <p className="mt-5 text-[0.72rem] text-muted">
              This is the organization's last active admin, so their role and status can't be
              changed here.
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
