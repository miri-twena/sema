import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ThreadSummary } from "../lib/api";
import type { DrillContext } from "../components/DrillChat";

function anchorKey(turnIndex: number, kind: string, title: string): string {
  return `${turnIndex}::${kind}::${title}`;
}

/**
 * Thread summaries for the currently open conversation -- fetched once per
 * conversation and kept fresh. `find` looks up whether a widget's anchor
 * already has a thread (used both to badge it and to resolve which thread to
 * open); `refresh` re-fetches after a drill turn completes.
 *
 * Conversations with no parent (nothing opened yet) simply have no threads:
 * `find`/`getThreadCount` return undefined, `refresh` is a no-op.
 *
 * `find` and `getThreadCount` are STABLE across renders (only their identity
 * changes when the underlying summaries actually change) -- TurnView receives
 * them as props and relies on that stability to avoid re-rendering every past
 * turn whenever something unrelated changes in App.tsx.
 */
export function useThreads(clientId: string, conversationId: string | null) {
  const [summaries, setSummaries] = useState<ThreadSummary[]>([]);
  const reqIdRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!conversationId) {
      setSummaries([]);
      return;
    }
    const reqId = ++reqIdRef.current;
    try {
      const list = await api.threads(conversationId, clientId);
      if (reqId === reqIdRef.current) setSummaries(list);
    } catch {
      if (reqId === reqIdRef.current) setSummaries([]);
    }
  }, [clientId, conversationId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const byAnchor = useMemo(() => {
    const m = new Map<string, ThreadSummary>();
    for (const t of summaries) m.set(anchorKey(t.turn_index, t.widget_kind, t.widget_title), t);
    return m;
  }, [summaries]);

  const find = useCallback(
    (turnIndex: number, kind: DrillContext["kind"], title: string): ThreadSummary | undefined =>
      byAnchor.get(anchorKey(turnIndex, kind, title)),
    [byAnchor],
  );

  const getThreadCount = useCallback(
    (turnIndex: number, kind: DrillContext["kind"], title: string): number | undefined =>
      find(turnIndex, kind, title)?.turn_count,
    [find],
  );

  return { find, getThreadCount, refresh };
}
