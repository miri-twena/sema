import { useCallback, useEffect, useState } from "react";

const MAX_ITEMS = 15;
const keyFor = (clientId: string) => `sema:question-history:${clientId}`;

function load(clientId: string): string[] {
  if (!clientId) return [];
  try {
    const raw = localStorage.getItem(keyFor(clientId));
    if (raw) return JSON.parse(raw) as string[];
  } catch {
    /* ignore corrupt storage */
  }
  return [];
}

/**
 * This browser's own question history, scoped per client. There's no login
 * yet, so "my history" can only mean "this browser's history" -- not tied to
 * a real identity. Most-recent-first; re-asking a question moves it to the
 * front instead of duplicating it.
 */
export function useQuestionHistory(clientId: string) {
  const [items, setItems] = useState<string[]>(() => load(clientId));

  // Each client has its own list, so reload whenever the active client changes.
  useEffect(() => setItems(load(clientId)), [clientId]);

  const record = useCallback(
    (question: string) => {
      if (!clientId) return;
      setItems((prev) => {
        const next = [question, ...prev.filter((q) => q !== question)].slice(0, MAX_ITEMS);
        try {
          localStorage.setItem(keyFor(clientId), JSON.stringify(next));
        } catch {
          /* storage full / unavailable */
        }
        return next;
      });
    },
    [clientId],
  );

  return { items, record };
}
