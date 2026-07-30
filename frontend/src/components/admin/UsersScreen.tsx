import { useEffect, useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import type { AdminRole, AdminUser } from "../../lib/api";
import { useAdminUsers } from "../../hooks/useAdminUsers";
import { UserRow } from "./UserRow";
import { InviteModal } from "./InviteModal";
import { UserDetailDrawer } from "./UserDetailDrawer";
import { RoleLegend, type RoleCatalog } from "./RoleTooltip";
import { DataScopeLegend } from "./DataScopeControl";

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
 * CTA, a search/role toolbar, and a flat table of user rows. Search is
 * debounced and filters name/email client-side (the org is small); the counts
 * and the last-active-admin rule derive from the full roster so they stay
 * correct regardless of the current filter.
 */
export function UsersScreen({ clientLabel }: { clientLabel: string }) {
  const {
    users,
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

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState(""); // debounced copy that actually filters
  const [roleFilter, setRoleFilter] = useState<AdminRole | "">("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  // Keyed by role id for RoleTooltip's O(1) per-row lookup.
  const roleCatalog: RoleCatalog = useMemo(
    () => Object.fromEntries(roles.map((r) => [r.id, r])) as RoleCatalog,
    [roles],
  );

  // Debounce the search term (spec §8) -- 200ms is imperceptible but keeps
  // filtering off every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setQuery(search.trim().toLowerCase()), 200);
    return () => window.clearTimeout(id);
  }, [search]);

  // Whole-org counts (not the filtered view), so the subtitle stays steady.
  const pendingCount = users.filter((u) => u.status === "invited").length;
  const memberCount = users.length - pendingCount;

  // The last active admin: their mutating controls are disabled (the server
  // guards it too). Only relevant when exactly one active admin remains.
  const activeAdminCount = users.filter(
    (u) => u.role === "client_admin" && u.status === "active",
  ).length;
  const isLastActiveAdmin = (id: string) => {
    const u = users.find((x) => x.id === id);
    return (
      activeAdminCount === 1 && !!u && u.role === "client_admin" && u.status === "active"
    );
  };

  const filtered = useMemo(() => {
    return users.filter((u) => {
      if (roleFilter && u.role !== roleFilter) return false;
      if (!query) return true;
      const hay = `${u.name ?? ""} ${u.email}`.toLowerCase();
      return hay.includes(query);
    });
  }, [users, query, roleFilter]);

  const filtering = query !== "" || roleFilter !== "";

  // Re-resolve against the live list (not the snapshot captured on click) so
  // a role/status change made elsewhere while the drawer is open is
  // reflected immediately -- and the drawer self-closes if the user is removed.
  const liveSelectedUser = selectedUser
    ? (users.find((u) => u.id === selectedUser.id) ?? null)
    : null;

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      {/* Breadcrumb */}
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>

      {/* Title + primary CTA */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Users and permissions</h1>
          <p className="text-[0.82rem] text-muted mt-1">
            {memberCount} member{memberCount === 1 ? "" : "s"}
            {" · "}
            {pendingCount} pending invite{pendingCount === 1 ? "" : "s"}
          </p>
        </div>
        <button
          onClick={() => setInviteOpen(true)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-3.5 py-2 shadow-bubble hover:bg-primary/90 transition"
        >
          <Plus size={15} /> Invite user
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
            placeholder="Search by name or email"
            aria-label="Search users"
            className="w-full rounded-lg border border-line bg-surface ps-8 pe-3 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as AdminRole | "")}
          aria-label="Filter by role"
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        >
          <option value="">All roles</option>
          <option value="client_admin">Admin</option>
          <option value="analyst">Analyst</option>
          <option value="viewer">Viewer</option>
        </select>
      </div>

      {/* Table */}
      <div className="mt-4">
        {/* Column header */}
        <div className="flex items-center gap-3 px-2 pb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
          <span className="w-8" aria-hidden />
          <span className="flex-1">User</span>
          <span className="w-28 flex items-center gap-1">
            Role
            {roles.length > 0 && <RoleLegend roles={roles} />}
          </span>
          <span className="w-28 flex items-center gap-1">
            Data access
            {dataScopes.length > 0 && <DataScopeLegend scopes={dataScopes} />}
          </span>
          <span className="w-32">Last active</span>
          <span className="w-24" aria-hidden />
        </div>

        {loading ? (
          <SkeletonRows />
        ) : error ? (
          <div className="px-2 py-10 text-center text-sm text-muted">
            Couldn't load users. Please try again.
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-2 py-10 text-center text-sm text-muted">
            {filtering ? "No users match your search." : "No users yet."}
          </div>
        ) : (
          <div className="flex flex-col divide-y divide-lineSoft">
            {filtered.map((u) => (
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

        {/* Last-admin info line (spec §6.1) */}
        {!loading && activeAdminCount === 1 && (
          <p className="mt-3 text-[0.75rem] text-muted">
            Your organization must keep at least one active admin, so that admin can't be
            removed, suspended, or downgraded.
          </p>
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
