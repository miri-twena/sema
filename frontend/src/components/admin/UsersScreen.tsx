import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import type { AdminRole, AdminUser } from "../../lib/api";
import { useAdminUsers } from "../../hooks/useAdminUsers";
import { useT } from "../../locales";
import { UserRow } from "./UserRow";
import { InviteModal } from "./InviteModal";
import { UserDetailDrawer } from "./UserDetailDrawer";
import { Pager } from "./Pager";
import { RoleLegend, type RoleCatalog } from "./RoleTooltip";
import { DataScopeLegend } from "./DataScopeControl";
import { CHART_PALETTE } from "../../lib/tokens";

/** Rows shown while the roster loads. */
function SkeletonRows() {
  return (
    <div aria-busy="true" className="flex flex-col">
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2.5">
          <div className="w-8 h-8 rounded-full bg-surfaceAlt animate-pulse" />
          <div className="flex-1 flex flex-col gap-1.5">
            <div className="h-3 w-40 rounded bg-surfaceAlt animate-pulse" />
            <div className="h-2.5 w-56 rounded bg-surfaceAlt animate-pulse" />
          </div>
          <div className="w-28 h-6 rounded bg-surfaceAlt animate-pulse" />
          <div className="w-28 h-6 rounded-full bg-surfaceAlt animate-pulse" />
          <div className="w-32 h-3 rounded bg-surfaceAlt animate-pulse" />
          <div className="w-24" />
        </div>
      ))}
    </div>
  );
}

/**
 * The "Users and permissions" screen (spec §6.1). Breadcrumb + title + invite
 * CTA, a search/role toolbar, a paged table of user rows (25/page,
 * users_pagination_prompt.md), and a pager hidden when everything fits on
 * one page. Search+role filtering are SERVER-SIDE and combine with paging;
 * member/pending/active-admin counts come from the server as whole-org
 * figures so the subtitle and the last-active-admin rule stay correct
 * regardless of the current page/filter.
 */
export function UsersScreen({ clientLabel }: { clientLabel: string }) {
  const {
    users,
    total,
    page,
    pageSize,
    setPage,
    memberCount,
    pendingCount,
    activeAdminCount,
    search,
    setSearch,
    roleFilter,
    setRoleFilter,
    filtering,
    roles,
    dataScopes,
    loading,
    error,
    changeRole,
    changeStatus,
    changeDataScope,
    remove,
    resend,
    invite,
  } = useAdminUsers();
  const t = useT();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  // Keyed by role id for RoleTooltip's O(1) per-row lookup.
  const roleCatalog: RoleCatalog = useMemo(
    () => Object.fromEntries(roles.map((r) => [r.id, r])) as RoleCatalog,
    [roles],
  );

  // The last active admin: their mutating controls are disabled (the server
  // guards it too). activeAdminCount is whole-org (from the server), so this
  // stays correct regardless of the current page/filter.
  const isLastActiveAdmin = (id: string) => {
    const u = users.find((x) => x.id === id);
    return (
      activeAdminCount === 1 && !!u && u.role === "client_admin" && u.status === "active"
    );
  };

  // Re-resolve against the live list (not the snapshot captured on click) so
  // a role/status change made elsewhere while the drawer is open is
  // reflected immediately -- and the drawer self-closes if the user is removed.
  const liveSelectedUser = selectedUser
    ? (users.find((u) => u.id === selectedUser.id) ?? null)
    : null;

  return (
    <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-8 py-8">
      {/* Breadcrumb */}
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || t.workspace.fallbackLabel} <span className="text-faint">›</span> {t.admin.users.breadcrumb}
      </div>

      {/* Title + primary CTA */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t.admin.users.title}</h1>
          <p className="text-[0.82rem] text-muted mt-1">{t.admin.users.subtitle(memberCount, pendingCount)}</p>
        </div>
        <button
          onClick={() => setInviteOpen(true)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-3.5 py-2 shadow-bubble hover:bg-primary/90 transition"
        >
          <Plus size={15} /> {t.admin.users.inviteUser}
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 mt-5">
        <div className="relative flex-1 max-w-xs">
          <Search
            size={15}
            className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-faint"
            aria-hidden
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t.admin.users.searchPlaceholder}
            aria-label={t.admin.users.searchPlaceholder}
            className="w-full rounded-lg border border-line bg-surface ps-8 pe-3 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as AdminRole | "")}
          aria-label={t.admin.users.allRoles}
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        >
          <option value="">{t.admin.users.allRoles}</option>
          <option value="client_admin">{t.common.roles.client_admin}</option>
          <option value="analyst">{t.common.roles.analyst}</option>
          <option value="viewer">{t.common.roles.viewer}</option>
        </select>
      </div>

      {/* Table */}
      <div className="mt-4">
        <div className="rounded-xl border border-line bg-surface overflow-hidden">
          <span className="block h-[3px] w-full" style={{ background: CHART_PALETTE[0] }} aria-hidden />
          {/* Column header */}
          <div className="flex items-center gap-3 px-2 pt-2 pb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
            <span className="w-8" aria-hidden />
            <span className="flex-1">{t.admin.users.columnUser}</span>
            <span className="w-28 flex items-center gap-1">
              {t.admin.users.columnRole}
              {roles.length > 0 && <RoleLegend roles={roles} />}
            </span>
            <span className="w-28 flex items-center gap-1">
              {t.admin.users.columnDataAccess}
              {dataScopes.length > 0 && <DataScopeLegend scopes={dataScopes} />}
            </span>
            <span className="w-32">{t.admin.users.columnLastActive}</span>
            <span className="w-24" aria-hidden />
          </div>

          {loading ? (
            <SkeletonRows />
          ) : error ? (
            <div className="px-2 py-10 text-center text-sm text-muted">{t.admin.users.couldNotLoad}</div>
          ) : users.length === 0 ? (
            <div className="px-2 py-10 text-center text-sm text-muted">
              {filtering ? t.admin.users.noUsersMatch : t.admin.users.noUsersYet}
            </div>
          ) : (
            <div className="flex flex-col divide-y divide-lineSoft">
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isLastActiveAdmin={isLastActiveAdmin(u.id)}
                  roles={roleCatalog}
                  dataScopes={dataScopes}
                  onChangeRole={changeRole}
                  onChangeDataScope={changeDataScope}
                  onSuspend={(id) => changeStatus(id, "suspended")}
                  onReactivate={(id) => changeStatus(id, "active")}
                  onRemove={remove}
                  onResend={resend}
                  onOpenDetail={setSelectedUser}
                />
              ))}
            </div>
          )}
        </div>

        {!loading && !error && (
          <Pager page={page} total={total} pageSize={pageSize} onPageChange={setPage} hideWhenSinglePage />
        )}

        {/* Last-admin info line (spec §6.1) */}
        {!loading && activeAdminCount === 1 && (
          <p className="mt-3 text-[0.75rem] text-muted">{t.admin.users.lastAdminNotice}</p>
        )}
      </div>

      {inviteOpen && (
        <InviteModal onClose={() => setInviteOpen(false)} onInvite={invite} />
      )}

      {liveSelectedUser && (
        <UserDetailDrawer
          user={liveSelectedUser}
          isLastActiveAdmin={isLastActiveAdmin(liveSelectedUser.id)}
          roles={roleCatalog}
          dataScopes={dataScopes}
          onClose={() => setSelectedUser(null)}
          onChangeRole={changeRole}
          onChangeDataScope={changeDataScope}
          onSuspend={(id) => changeStatus(id, "suspended")}
          onReactivate={(id) => changeStatus(id, "active")}
        />
      )}
    </div>
  );
}
