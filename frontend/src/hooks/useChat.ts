import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ChatResponse,
  type ConversationDetail,
  type DrillContextPayload,
  type Message,
} from "../lib/api";
import { dirOf, isRtl } from "../lib/rtl";
import { UNDERSTANDING, type ProgressEvent } from "../lib/progress";

export interface ChatTurn {
  question: string;
  response: ChatResponse | null; // null while loading / stopped
  dir: "rtl" | "ltr";
  stopped?: boolean;
  /** REAL backend progress stages, in the order the server emitted them.
   * Every entry corresponds to an actual tool dispatch -- there are no
   * timer-driven or invented stages. Drives the live ProgressPanel shown while
   * the answer is streaming (cleared from view once the answer lands). */
  progress?: ProgressEvent[];
}

interface UseChatOptions {
  clientId: string;
  /** Structured widget reference sent with every question from a drill-down
   * panel. The SERVER builds the prompt framing from it -- the client never
   * concatenates context text into the question (prompt-injection surface). */
  drillContext?: DrillContextPayload;
  /** localStorage key to persist the transcript across refreshes; null disables. */
  persistKey?: string | null;
  /** Called when a turn establishes or continues a server conversation, so the
   * sidebar can refresh its list (new title, new position). */
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

/** An answer stored before payloads were persisted (or whose payload failed to
 * parse) -> a minimal renderable response. `response: null` means "still
 * loading" to TurnView, so returning null for a turn that HAS an answer leaves
 * it spinning forever; degrading to text-only is the correct fallback. */
function textOnlyResponse(text: string): ChatResponse {
  return {
    answer: text,
    kpis: [],
    chart: null,
    table: null,
    actions: [],
    follow_up_questions: [],
    sql_used: null,
    confidence: null,
    evidence: null,
    status: "ok",
    error: null,
  };
}

/** A stored conversation -> the in-memory shapes the chat view renders. Pairs
 * each user turn with the assistant turn that follows it; a user turn with no
 * answer yet still renders as pending. */
function turnsFromDetail(detail: ConversationDetail): { turns: ChatTurn[]; history: Message[] } {
  const turns: ChatTurn[] = [];
  const history: Message[] = [];
  const msgs = detail.messages;
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (m.role !== "user") continue;
    const next = msgs[i + 1];
    const answer = next && next.role === "assistant" ? next : null;
    turns.push({
      question: m.content,
      response: answer ? (answer.payload ?? textOnlyResponse(answer.content)) : null,
      dir: dirOf(m.content),
    });
    history.push({ role: "user", content: m.content });
    if (answer) history.push({ role: "assistant", content: answer.content });
  }
  return { turns, history };
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

// Backstop for the follow-up suggestion: SEMA can analyze data, but it cannot
// send email, launch campaigns, spend money, or contact people. The agent is
// already told to keep such actions out of follow_up_questions, but a stray one
// must never reach the composer -- when accepted it would just get "I can't do
// that". Any candidate mentioning real-world execution is dropped (safe: no
// suggestion beats an un-answerable one). Covers English and Hebrew.
const NOT_ANSWERABLE = [
  "launch", "send", "email", "e-mail", "campaign", "contact", "call ", "phone",
  "offer", "discount", "coupon", "promo", "invest", "budget", "spend", "hire",
  "advertise", "retarget", "notify", "reach out", "outreach", "onboard",
  "incentiv", "roll out", "deploy", "negotiate", "text ", "sms", "newsletter",
  "שלח", "שיגור", "מייל", "אימייל", "קמפיין", "השק", "השיק", "צור קשר",
  "התקשר", "הצע", "הנחה", "קופון", "השקע", "תקציב", "הוצא", "גייס",
  "פרסם", "רימרקטינג", "פנה", "מבצע", "מסר",
];

function isAnswerable(q: string): boolean {
  const s = q.toLowerCase();
  return !NOT_ANSWERABLE.some((w) => s.includes(w));
}

/** The contextual follow-up to offer after an answer: the first of the agent's
 * dedicated follow-up QUESTIONS (things it can answer from the data), filtered
 * so nothing un-answerable slips through. Returns null when nothing qualifies,
 * so the composer shows no suggestion rather than one SEMA can't act on. */
function pickFollowUp(resp: ChatResponse): string | null {
  const q = resp.follow_up_questions?.find((x) => x.trim().length > 0 && isAnswerable(x));
  return q ? q.trim() : null;
}

export function useChat({ clientId, drillContext, persistKey, onConversationChanged }: UseChatOptions) {
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
  const conversationIdRef = useRef<string | null>(initial.current.conversationId ?? null);
  const [conversationId, setConversationIdState] = useState<string | null>(
    initial.current.conversationId ?? null,
  );
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
    [history, clientId, drillContext],
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

  return { turns, loading, followUp, conversationId, send, stop, retry, reset, openConversation };
}
