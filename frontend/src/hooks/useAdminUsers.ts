import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type AdminDataScope,
  type AdminRole,
  type AdminStatus,
  type AdminUser,
  type DataScopeInfo,
  type RoleInfo,
} from "../lib/api";
import { useToast } from "../components/admin/toast-context";

const PAGE_SIZE = 25;

/**
 * State + mutations for the admin Users screen.
 *
 * Search and role filtering are SERVER-SIDE, combined with paging (25/page,
 * spec §8 -- same "search log can grow unbounded" reasoning useAuditLog
 * already documents applies here too once an org has more than a handful of
 * people). `search` is debounced the same way the audit log debounces its
 * own search (200ms); any filter change jumps back to page 1, so a narrower
 * filter never lands on a now-nonexistent page.
 *
 * member_count/pending_count/active_admin_count come from the server and
 * reflect the WHOLE org, not the current page/filter -- the subtitle and the
 * last-active-admin guard both need the true org-wide picture regardless of
 * what's currently paged in.
 *
 * Mutations are OPTIMISTIC on the current page: the local list changes
 * immediately and the request runs in the background; on failure the
 * snapshot is restored and a toast is raised (success is silent, per the
 * mockup). Every mutation that could shift pagination or the filtered total
 * (role change, remove) also refreshes from the server once the request
 * settles, so the page/total reconcile shortly after -- e.g. deleting the
 * last user on the last page jumps back a page once the refresh lands.
 * `invite` is the exception -- it rethrows so the modal can show the
 * server's message (e.g. duplicate email) inline.
 */
export function useAdminUsers() {
  const toast = useToast();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [memberCount, setMemberCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [activeAdminCount, setActiveAdminCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  // The role catalog backs the header legend + per-row tooltip (spec item
  // 3a) -- fetched once, same load-once pattern as `roles`.
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  // The data-scope catalog backs the "Data access" column's legend + editor
  // -- fetched once, same load-once pattern as `dataScopes`.
  const [dataScopes, setDataScopes] = useState<DataScopeInfo[]>([]);

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState(""); // debounced copy that actually filters
  const [roleFilter, setRoleFilter] = useState<AdminRole | "">("");

  // Debounce the search term (spec §8) -- 200ms is imperceptible but keeps
  // filtering off every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setQuery(search.trim()), 200);
    return () => window.clearTimeout(id);
  }, [search]);

  // Any filter change (not a page change by itself) jumps back to page 1.
  useEffect(() => {
    setPage(1);
  }, [query, roleFilter]);

  const filtering = query !== "" || roleFilter !== "";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.admin.users({
        q: query || undefined,
        role: roleFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setUsers(data.users);
      setTotal(data.total);
      setPage(data.page);
      setMemberCount(data.member_count);
      setPendingCount(data.pending_count);
      setActiveAdminCount(data.active_admin_count);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [query, roleFilter, page]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    api.admin.roles().then(setRoles).catch(() => setRoles([]));
  }, []);

  useEffect(() => {
    api.admin.dataScopes().then(setDataScopes).catch(() => setDataScopes([]));
  }, []);

  // Replace one user in place from a server response (role/status/resend).
  const applyUser = useCallback((updated: AdminUser) => {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
  }, []);

  /** Optimistically patch one user on the CURRENT PAGE, reconciling with the
   * server row on success (then refreshing in the background, since a role
   * change can move a row out of a role-filtered view) and rolling back to
   * `snapshot` on failure. */
  const optimisticPatch = useCallback(
    async (
      id: string,
      change: Partial<AdminUser>,
      run: () => Promise<AdminUser>,
      failMessage: string,
    ) => {
      const snapshot = users;
      setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...change } : u)));
      try {
        applyUser(await run());
        void refresh();
      } catch (e) {
        setUsers(snapshot); // revert
        toast(e instanceof ApiError ? e.detail : failMessage);
      }
    },
    [users, applyUser, toast, refresh],
  );

  const changeRole = useCallback(
    (id: string, role: AdminRole) =>
      optimisticPatch(id, { role }, () => api.admin.updateUser(id, { role }), "Couldn't change role."),
    [optimisticPatch],
  );

  const changeStatus = useCallback(
    (id: string, status: AdminStatus) =>
      optimisticPatch(
        id,
        { status },
        () => api.admin.updateUser(id, { status }),
        "Couldn't update user.",
      ),
    [optimisticPatch],
  );

  const changeDataScope = useCallback(
    (id: string, data_scope: AdminDataScope) =>
      optimisticPatch(
        id,
        { data_scope },
        () => api.admin.updateUser(id, { data_scope }),
        "Couldn't change data access.",
      ),
    [optimisticPatch],
  );

  const remove = useCallback(
    async (id: string) => {
      const snapshot = users;
      const next = users.filter((u) => u.id !== id);
      setUsers(next);
      try {
        await api.admin.deleteUser(id);
        // Empty page (e.g. the last row on the last page) -- jump back a
        // page; the effect on `page` re-fetches automatically. Otherwise
        // just refresh in place to reconcile total/pagination (a row from
        // the next page slides into this one server-side).
        if (next.length === 0 && page > 1) setPage((p) => p - 1);
        else void refresh();
      } catch (e) {
        setUsers(snapshot); // revert
        toast(e instanceof ApiError ? e.detail : "Couldn't remove user.");
      }
    },
    [users, page, refresh, toast],
  );

  const resend = useCallback(
    async (id: string) => {
      try {
        applyUser(await api.admin.resendInvite(id));
      } catch (e) {
        toast(e instanceof ApiError ? e.detail : "Couldn't resend the invite.");
      }
    },
    [applyUser, toast],
  );

  /** Invite a new user. Rethrows on failure so the modal shows the server's
   * message inline (duplicate email, bad address) rather than a toast. */
  const invite = useCallback(
    async (email: string, role: AdminRole, dataScope?: AdminDataScope) => {
      const created = await api.admin.invite(email, role, dataScope);
      void refresh();
      return created;
    },
    [refresh],
  );

  return {
    users,
    total,
    page,
    pageSize: PAGE_SIZE,
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
    refresh,
    changeRole,
    changeStatus,
    changeDataScope,
    remove,
    resend,
    invite,
  };
}
