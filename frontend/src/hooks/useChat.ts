import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ChatResponse, type Message } from "../lib/api";
import { isRtl } from "../lib/rtl";

export interface ChatTurn {
  question: string;
  response: ChatResponse | null; // null while loading / stopped
  dir: "rtl" | "ltr";
  stopped?: boolean;
  phase?: string; // staged progress label while loading
}

// Staged "thinking" progress so a long request feels responsive instead of a
// silent spinner (no server streaming yet). Labels advance on a timer.
const PHASES = ["Understanding your question", "Querying the data", "Analyzing the results", "Composing the answer"];
const PHASE_AT_MS = [1500, 5000, 11000];

interface UseChatOptions {
  clientId: string;
  /** Transform the question before sending (drill-down prefixes widget context). */
  buildPrompt?: (question: string) => string;
  /** localStorage key to persist the transcript across refreshes; null disables. */
  persistKey?: string | null;
}

interface Persisted {
  turns: ChatTurn[];
  history: Message[];
}

function load(key: string | null | undefined): Persisted {
  if (!key) return { turns: [], history: [] };
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw) as Persisted;
  } catch {
    /* ignore corrupt storage */
  }
  return { turns: [], history: [] };
}

function errorResponse(e: unknown): ChatResponse {
  return {
    answer: "",
    kpis: [],
    chart: null,
    table: null,
    actions: [],
    sql_used: null,
    confidence: null,
    status: "error",
    error: e instanceof Error ? e.message : String(e),
  };
}

export function useChat({ clientId, buildPrompt, persistKey }: UseChatOptions) {
  const initial = useRef(load(persistKey));
  const [turns, setTurns] = useState<ChatTurn[]>(initial.current.turns);
  const [history, setHistory] = useState<Message[]>(initial.current.history);
  const [loading, setLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const timersRef = useRef<number[]>([]);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };

  // Persist only completed turns (never a mid-flight/stopped one) + history.
  useEffect(() => {
    if (!persistKey) return;
    const done = turns.filter((t) => t.response && t.response.status === "ok");
    try {
      localStorage.setItem(persistKey, JSON.stringify({ turns: done, history }));
    } catch {
      /* storage full / unavailable */
    }
  }, [turns, history, persistKey]);

  const setLastPhase = (phase: string) =>
    setTurns((t) => {
      if (!t.length || t[t.length - 1].response) return t;
      const copy = [...t];
      copy[copy.length - 1] = { ...copy[copy.length - 1], phase };
      return copy;
    });

  const replaceLast = (turn: ChatTurn) =>
    setTurns((t) => {
      const copy = [...t];
      copy[copy.length - 1] = turn;
      return copy;
    });

  const runRequest = useCallback(
    async (question: string, dir: "rtl" | "ltr") => {
      setLoading(true);
      clearTimers();
      timersRef.current = PHASE_AT_MS.map((ms, i) =>
        window.setTimeout(() => setLastPhase(PHASES[i + 1]), ms),
      );
      const controller = new AbortController();
      abortRef.current = controller;
      const prompt = buildPrompt ? buildPrompt(question) : question;
      try {
        const resp = await api.chat(prompt, history, clientId, controller.signal);
        replaceLast({ question, response: resp, dir });
        if (resp.status === "ok") {
          setHistory((h) => [...h, { role: "user", content: question }, { role: "assistant", content: resp.answer }]);
        }
      } catch (e) {
        const aborted = e instanceof DOMException && e.name === "AbortError";
        replaceLast(aborted ? { question, dir, response: null, stopped: true } : { question, dir, response: errorResponse(e) });
      } finally {
        clearTimers();
        abortRef.current = null;
        setLoading(false);
      }
    },
    // history/clientId/buildPrompt captured per call; identity kept stable enough
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [history, clientId],
  );

  const send = useCallback(
    (question: string) => {
      const q = question.trim();
      if (!q || loading) return;
      const dir = isRtl(q) ? "rtl" : "ltr";
      setTurns((t) => [...t, { question: q, response: null, dir, phase: PHASES[0] }]);
      void runRequest(q, dir);
    },
    [loading, runRequest],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  // Retry a failed turn: drop it and resend its question.
  const retry = useCallback(
    (index: number) => {
      if (loading) return;
      const failed = turns[index];
      if (!failed) return;
      setTurns((t) => t.filter((_, i) => i !== index));
      send(failed.question);
    },
    [loading, turns, send],
  );

  const reset = useCallback(() => {
    clearTimers();
    abortRef.current?.abort();
    setTurns([]);
    setHistory([]);
    if (persistKey) localStorage.removeItem(persistKey);
  }, [persistKey]);

  return { turns, loading, send, stop, retry, reset };
}
