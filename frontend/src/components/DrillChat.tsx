import { useState, useRef, useEffect } from "react";
import { X } from "lucide-react";
import { api, type ChatResponse, type Message } from "../lib/api";
import { isRtl } from "../lib/rtl";
import { ChatMessage } from "./ChatMessage";
import { AssistantResponseCard } from "./AssistantResponseCard";
import { ChatInput } from "./ChatInput";

// The focused context passed when a widget (KPI / chart) is clicked. `title`
// is the display name; `contextBlock` is the pre-seeded instruction sent to
// the agent so it scopes every answer to this widget.
export interface DrillContext {
  title: string;
  contextBlock: string;
}

interface Turn {
  question: string;
  response: ChatResponse | null;
  dir: "rtl" | "ltr";
  stopped?: boolean;
}

const STARTERS = ["Why did this change?", "Break this down by segment.", "What should I do about it?"];

// A slide-in sub-chat scoped to one widget. Its conversation state is entirely
// local, so it never mixes into the main chat's history. Reuses the same
// api.chat call as the main chat -- it just prefixes the widget context onto
// each question so the agent answers only in that widget's context.
export function DrillChat({
  widget,
  clientId,
  onClose,
}: {
  widget: DrillContext;
  clientId: string;
  onClose: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function stop() {
    abortRef.current?.abort();
  }

  async function send(question: string) {
    if (loading) return;
    const dir = isRtl(question) ? "rtl" : "ltr";
    setTurns((t) => [...t, { question, response: null, dir }]);
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    // Scope this turn to the widget; history stays plain so the block isn't
    // duplicated across turns.
    const scoped = `${widget.contextBlock}\n\nUser question: ${question}`;
    try {
      const resp = await api.chat(scoped, history, clientId, controller.signal);
      setTurns((t) => {
        const c = [...t];
        c[c.length - 1] = { question, response: resp, dir };
        return c;
      });
      setHistory((h) => [...h, { role: "user", content: question }, { role: "assistant", content: resp.answer }]);
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      setTurns((t) => {
        const c = [...t];
        c[c.length - 1] = aborted
          ? { question, dir, response: null, stopped: true }
          : {
              question,
              dir,
              response: { answer: "", kpis: [], chart: null, table: null, actions: [], sql_used: null, confidence: null, status: "error", error: String(e) },
            };
        return c;
      });
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-ink/20 z-40" onClick={onClose} />
      <aside className="fixed top-0 right-0 h-full w-[440px] max-w-[92vw] bg-bg border-l border-line shadow-pop z-50 flex flex-col">
        <header className="flex items-center justify-between px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="min-w-0">
            <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Drill-down</div>
            <div className="text-sm font-semibold text-ink truncate">{widget.title}</div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            <X size={18} />
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-auto sema-scroll px-5 py-4">
          {turns.length === 0 && (
            <div className="mt-6 text-center">
              <div className="text-sm text-muted">
                Ask a follow-up about <span className="font-medium text-ink">{widget.title}</span>.
              </div>
              <div className="mt-3 flex flex-col gap-1.5">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-start text-[0.82rem] rounded-lg border border-lineSoft bg-primary/[0.06] text-primary-dark px-3 py-2 hover:bg-surface hover:border-primary transition"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i} className={i > 0 ? "border-t border-line pt-3 mt-3" : ""}>
              <ChatMessage text={t.question} dir={t.dir} />
              {t.response ? (
                <AssistantResponseCard response={t.response} dir={t.dir} />
              ) : t.stopped ? (
                <div className="text-sm text-muted px-1 py-3 italic">Response stopped.</div>
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted px-1 py-3">
                  <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  SEMA is analyzing…
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="px-5 py-4 border-t border-line bg-bg shrink-0">
          <ChatInput onSend={send} onStop={stop} loading={loading} placeholder={`Ask about ${widget.title}...`} />
        </div>
      </aside>
    </>
  );
}
