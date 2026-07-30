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

/**
 * State + mutations for the admin Users screen.
 *
 * Loads the WHOLE org roster once (the org is small; server-side search exists
 * for future pagination but isn't needed at this size). Keeping the full list
 * client-side means search/role filtering, the member/pending counts, and the
 * last-active-admin rule are all derived from one consistent snapshot -- no
 * second request, no counts drifting from the filtered view.
 *
 * Mutations are OPTIMISTIC: the local list changes immediately and the request
 * runs in the background; on failure the snapshot is restored and a toast is
 * raised (success is silent, per the mockup). `invite` is the exception -- it
 * rethrows so the modal can show the server's message (e.g. duplicate email)
 * inline.
 */
export function useAdminUsers() {
  const toast = useToast();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  // The role catalog backs the header legend + per-row tooltip (spec item
  // 3a) -- fetched once, same load-once pattern as `users`.
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  // The data-scope catalog backs the "Data access" column's legend + editor
  // -- fetched once, same load-once pattern as `roles`.
  const [dataScopes, setDataScopes] = useState<DataScopeInfo[]>([]);

  const refresh = useCallback(async () => {
    try {
      const data = await api.admin.users();
      setUsers(data.users);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

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

  /** Optimistically patch one user, reconciling with the server row on success
   * and rolling back to `snapshot` on failure. */
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
      } catch (e) {
        setUsers(snapshot); // revert
        toast(e instanceof ApiError ? e.detail : failMessage);
      }
    },
    [users, applyUser, toast],
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
      setUsers((prev) => prev.filter((u) => u.id !== id));
      try {
        await api.admin.deleteUser(id);
      } catch (e) {
        setUsers(snapshot); // revert
        toast(e instanceof ApiError ? e.detail : "Couldn't remove user.");
      }
    },
    [users, toast],
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
  const invite = useCallback(async (email: string, role: AdminRole, dataScope?: AdminDataScope) => {
    const created = await api.admin.invite(email, role, dataScope);
    setUsers((prev) => [...prev, created]);
    return created;
  }, []);

  return {
    users,
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
