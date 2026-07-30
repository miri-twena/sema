import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ChatResponse,
  type DrillContextPayload,
  type Message,
  type TurnFeedback,
} from "../lib/api";
import { type ChatTurn, turnsFromDetail } from "../lib/conversations";
import { pickFollowUp } from "../lib/questions";
import { isRtl } from "../lib/rtl";
// `type ProgressEvent` must stay imported: without it the name silently
// resolves to the DOM's global ProgressEvent instead of ours.
import { UNDERSTANDING, type ProgressEvent } from "../lib/progress";

// Re-exported so existing importers (TurnView) keep working -- the type's home
// is lib/conversations.ts, next to the logic that builds it.
export type { ChatTurn };

interface UseChatOptions {
  clientId: string;
  /** Structured widget reference sent with every question from a drill-down
   * panel. The SERVER builds the prompt framing from it -- the client never
   * concatenates context text into the question (prompt-injection surface). */
  drillContext?: DrillContextPayload;
  /** For a drill-down THREAD: the parent conversation + turn this widget's
   * answer belongs to. Sent on every request from this hook instance so the
   * server resolves (creating on the first turn) the SAME thread every time --
   * "one thread per anchor." Undefined for the main chat and for anchor-less
   * drills (the home dashboard), both of which use the ordinary conversation
   * flow unchanged. */
  threadAnchor?: { conversationId: string; turnIndex: number };
  /** localStorage key to persist the transcript across refreshes; null disables. */
  persistKey?: string | null;
  /** Called when a turn establishes or continues a server conversation, so the
   * sidebar can refresh its list (new title, new position). Also fires after a
   * drill-thread turn (the parent conversation_id is echoed back unchanged),
   * which DrillChat uses to tell its opener to refresh thread badges. */
  onConversationChanged?: (conversationId: string) => void;
}

interface Persisted {
  turns: ChatTurn[];
  history: Message[];
  conversationId?: string | null;
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
    follow_up_questions: [],
    sql_used: null,
    confidence: null,
    evidence: null,
    status: "error",
    error: e instanceof Error ? e.message : String(e),
  };
}

export function useChat({
  clientId,
  drillContext,
  threadAnchor,
  persistKey,
  onConversationChanged,
}: UseChatOptions) {
  const initial = useRef(load(persistKey));
  const [turns, setTurns] = useState<ChatTurn[]>(initial.current.turns);
  const [history, setHistory] = useState<Message[]>(initial.current.history);
  const [loading, setLoading] = useState(false);
  // Contextual follow-up suggestion for the composer. Set ONLY when a fresh
  // answer completes successfully this session; cleared on every other
  // transition (new send, reset, reopen, error, cancel) so a stale suggestion
  // never lingers.
  const [followUp, setFollowUp] = useState<string | null>(null);
  // The server conversation this chat is appending to. Held in a ref (not just
  // state) so a rapid second send within the same tick still sees the id the
  // first response established, instead of minting a duplicate conversation.
  // A thread-anchored chat seeds this with the PARENT conversation id up
  // front (never null), so even its FIRST request already carries the anchor
  // -- there is no "adopt the id from the response" step to wait for, unlike
  // the main chat's first turn.
  const initialConversationId = initial.current.conversationId ?? threadAnchor?.conversationId ?? null;
  const conversationIdRef = useRef<string | null>(initialConversationId);
  const [conversationId, setConversationIdState] = useState<string | null>(initialConversationId);
  const setConversationId = useCallback((id: string | null) => {
    conversationIdRef.current = id;
    setConversationIdState(id);
  }, []);

  const abortRef = useRef<AbortController | null>(null);

  // Latest callback without making it a dependency of runRequest (which would
  // rebuild the request identity on every render of the parent).
  const onConversationChangedRef = useRef(onConversationChanged);
  useEffect(() => {
    onConversationChangedRef.current = onConversationChanged;
  }, [onConversationChanged]);

  // Persist only completed turns (never a mid-flight/stopped one) + history +
  // the conversation id, so a refresh reopens the same server conversation.
  useEffect(() => {
    if (!persistKey) return;
    const done = turns.filter((t) => t.response && t.response.status === "ok");
    try {
      localStorage.setItem(
        persistKey,
        JSON.stringify({ turns: done, history, conversationId }),
      );
    } catch {
      /* storage full / unavailable */
    }
  }, [turns, history, conversationId, persistKey]);

  // Append one real server stage to the in-flight turn.
  const pushProgress = (e: ProgressEvent) =>
    setTurns((t) => {
      if (!t.length || t[t.length - 1].response) return t;
      const copy = [...t];
      const last = copy[copy.length - 1];
      copy[copy.length - 1] = { ...last, progress: [...(last.progress ?? []), e] };
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
      setFollowUp(null); // a new/retried question retires the previous suggestion
      const controller = new AbortController();
      abortRef.current = controller;
      // Captured so the finished turn keeps the stages it actually went through.
      const seen: ProgressEvent[] = [UNDERSTANDING];
      try {
        const resp = await api.chatStream(
          question,
          history,
          clientId,
          (e) => {
            seen.push(e);
            pushProgress(e);
          },
          controller.signal,
          drillContext,
          conversationIdRef.current,
          threadAnchor?.turnIndex,
        );
        replaceLast({ question, response: resp, dir, progress: seen });
        if (resp.status === "ok") {
          setHistory((h) => [...h, { role: "user", content: question }, { role: "assistant", content: resp.answer }]);
          // Offer the agent's top recommendation as the next follow-up.
          setFollowUp(pickFollowUp(resp));
          // Adopt (or confirm) the server conversation id, then let the
          // sidebar refresh -- a brand-new chat now has a title and a row.
          if (resp.conversation_id) {
            setConversationId(resp.conversation_id);
            onConversationChangedRef.current?.(resp.conversation_id);
          }
        }
      } catch (e) {
        const aborted = e instanceof DOMException && e.name === "AbortError";
        replaceLast(
          aborted
            ? { question, dir, response: null, stopped: true, progress: seen }
            : { question, dir, response: errorResponse(e), progress: seen },
        );
      } finally {
        abortRef.current = null;
        setLoading(false);
      }
    },
    // history/clientId/drillContext captured per call; identity kept stable enough
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [history, clientId, drillContext, threadAnchor?.conversationId, threadAnchor?.turnIndex],
  );

  const send = useCallback(
    (question: string) => {
      const q = question.trim();
      if (!q || loading) return;
      const dir = isRtl(q) ? "rtl" : "ltr";
      setTurns((t) => [...t, { question: q, response: null, dir, progress: [UNDERSTANDING] }]);
      void runRequest(q, dir);
    },
    [loading, runRequest],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  // Optimistic local update after a feedback POST -- the request itself
  // (and its silent-revert-on-failure) is MessageActions' concern; this just
  // keeps the turn's state in sync so it survives this component staying
  // mounted across re-renders (and round-trips through persistKey's
  // localStorage cache alongside the rest of a completed turn).
  const setFeedback = useCallback((index: number, feedback: TurnFeedback | null) => {
    setTurns((t) => {
      if (!t[index]) return t;
      const copy = [...t];
      copy[index] = { ...copy[index], feedback };
      return copy;
    });
  }, []);

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

  // New chat: clear the view AND the conversation id, so the next question
  // starts a fresh server conversation. Previous conversations are untouched
  // (they live server-side); only this browser's active view resets.
  const reset = useCallback(() => {
    abortRef.current?.abort();
    setTurns([]);
    setHistory([]);
    setConversationId(null);
    setFollowUp(null);
    if (persistKey) localStorage.removeItem(persistKey);
  }, [persistKey, setConversationId]);

  // Reopen an existing conversation: fetch its transcript and adopt its id so
  // the next question continues it. Cancels any in-flight request first.
  const openConversation = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      setLoading(true);
      setFollowUp(null); // a restored chat shows no suggestion until a new answer
      try {
        const detail = await api.conversation(id, clientId);
        const { turns: loaded, history: loadedHistory } = turnsFromDetail(detail);
        setTurns(loaded);
        setHistory(loadedHistory);
        setConversationId(id);
      } finally {
        setLoading(false);
      }
    },
    [clientId, setConversationId],
  );

  // Reopen an EXISTING thread: fetch its transcript and continue it. Only
  // meaningful for a thread-anchored chat -- conversationId is already the
  // anchor's parent id (seeded above), so unlike openConversation there is
  // nothing to adopt, only turns to load.
  const openThread = useCallback(
    async (threadId: string) => {
      if (!threadAnchor) return;
      abortRef.current?.abort();
      setLoading(true);
      setFollowUp(null);
      try {
        const detail = await api.thread(threadAnchor.conversationId, threadId, clientId);
        const { turns: loaded, history: loadedHistory } = turnsFromDetail(detail);
        setTurns(loaded);
        setHistory(loadedHistory);
      } finally {
        setLoading(false);
      }
    },
    [clientId, threadAnchor],
  );

  return {
    turns,
    loading,
    followUp,
    conversationId,
    send,
    stop,
    retry,
    reset,
    openConversation,
    openThread,
    setFeedback,
  };
}
