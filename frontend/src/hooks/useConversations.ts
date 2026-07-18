import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ConversationSummary } from "../lib/api";

/**
 * Owns the sidebar's conversation list for one client: fetch, and optimistic
 * rename / pin / archive / delete against the server store. Optimistic so the
 * sidebar updates immediately; a failed write refetches to resync rather than
 * leaving the UI lying about server state.
 */
export function useConversations(clientId: string) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  // Guards against a slow response for a previous client overwriting a newer
  // client's list (switching clients fast).
  const reqIdRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!clientId) return;
    const reqId = ++reqIdRef.current;
    setLoading(true);
    try {
      const list = await api.conversations(clientId);
      if (reqId === reqIdRef.current) {
        setConversations(list);
        setError(false);
      }
    } catch {
      if (reqId === reqIdRef.current) setError(true);
    } finally {
      if (reqId === reqIdRef.current) setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    setConversations([]);
    void refresh();
  }, [refresh]);

  // Apply an optimistic change locally, run the server write, and refetch to
  // reconcile (re-sort by updated_at, drop archived/deleted). On error, refetch
  // rolls the optimistic guess back to server truth.
  const mutate = useCallback(
    async (optimistic: (prev: ConversationSummary[]) => ConversationSummary[], write: () => Promise<unknown>) => {
      setConversations(optimistic);
      try {
        await write();
      } catch {
        setError(false); // a transient write error shouldn't blank the list
      } finally {
        void refresh();
      }
    },
    [refresh],
  );

  const rename = useCallback(
    (id: string, title: string) =>
      mutate(
        (prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)),
        () => api.updateConversation(id, clientId, { title }),
      ),
    [clientId, mutate],
  );

  const togglePin = useCallback(
    (id: string, pinned: boolean) =>
      mutate(
        (prev) => prev.map((c) => (c.id === id ? { ...c, pinned } : c)),
        () => api.updateConversation(id, clientId, { pinned }),
      ),
    [clientId, mutate],
  );

  const archive = useCallback(
    (id: string) =>
      mutate(
        (prev) => prev.filter((c) => c.id !== id),
        () => api.updateConversation(id, clientId, { archived: true }),
      ),
    [clientId, mutate],
  );

  const remove = useCallback(
    (id: string) =>
      mutate(
        (prev) => prev.filter((c) => c.id !== id),
        () => api.deleteConversation(id, clientId),
      ),
    [clientId, mutate],
  );

  return { conversations, loading, error, refresh, rename, togglePin, archive, remove };
}
