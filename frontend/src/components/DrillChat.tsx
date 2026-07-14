import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronsLeft, ChevronsRight, X } from "lucide-react";
import { useChat } from "../hooks/useChat";
import { ChatInput } from "./ChatInput";
import { TurnView } from "./TurnView";

// The focused context passed when a widget (KPI / chart) or a recommended
// action is clicked. `title` is the display name; `contextBlock` is the
// pre-seeded instruction sent to the agent so it scopes every answer.
// `initialInput` (recommendations) pre-fills the input instead of showing
// generic starters.
export interface DrillContext {
  title: string;
  contextBlock: string;
  initialInput?: string;
  /** Direction of the ORIGINAL question that produced this widget (KPI/chart/
   * action). Drives which language the drill panel's static UI (suggested
   * follow-ups, labels) uses -- a Hebrew question should get a Hebrew
   * follow-up panel, not just Hebrew-rendered answer text. */
  dir?: "rtl" | "ltr";
}

const STARTERS: Record<"ltr" | "rtl", string[]> = {
  ltr: ["Why did this change?", "Break this down by segment.", "What should I do about it?"],
  rtl: ["למה זה השתנה?", "פרט/י לפי פלח.", "מה כדאי לעשות בנידון?"],
};

const ANIM_MS = 220;
const EXPANDED_KEY = "sema.drill.expanded";

// A slide-in sub-chat scoped to one widget / action. Its conversation lives in
// its own useChat instance (no persistence), so it never mixes into the main
// chat. Same engine, just prefixing the context onto every question.
export function DrillChat({
  widget,
  clientId,
  onClose,
}: {
  widget: DrillContext;
  clientId: string;
  onClose: () => void;
}) {
  const buildPrompt = useCallback(
    (q: string) => `${widget.contextBlock}\n\nUser question: ${q}`,
    [widget.contextBlock],
  );
  const chat = useChat({ clientId, buildPrompt, persistKey: null });
  const dir = widget.dir ?? "ltr";
  const scrollRef = useRef<HTMLDivElement>(null);

  // Exit animation: the panel is on-screen by default (robust -- if animation
  // doesn't run it's still visible). Closing plays the slide-out/fade-out
  // keyframes, then unmounts via onClose.
  const [closing, setClosing] = useState(false);
  const requestClose = useCallback(() => {
    setClosing(true);
    window.setTimeout(onClose, ANIM_MS);
  }, [onClose]);

  // Expand/collapse width, remembered across drill-downs. Read lazily so a
  // remembered "expanded" panel opens at full width immediately, no flash.
  const [expanded, setExpanded] = useState(() => {
    try {
      return localStorage.getItem(EXPANDED_KEY) === "true";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(EXPANDED_KEY, String(expanded));
    } catch {
      // Storage disabled (e.g. private browsing) -- the toggle still works,
      // it just won't be remembered next time.
    }
  }, [expanded]);

  // The width transition is applied only after mount, so an initial expanded
  // state (from localStorage) renders at full width immediately instead of
  // animating in alongside the slide-in keyframe.
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => setHasMounted(true), []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chat.turns, chat.loading]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && requestClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [requestClose]);

  return (
    <>
      <div
        className={`fixed inset-0 bg-ink/20 z-40 ${
          closing ? "animate-[sema-fade-out_0.2s_ease-in_forwards]" : "animate-[sema-fade-in_0.2s_ease-out]"
        }`}
        onClick={requestClose}
      />
      <aside
        className={`fixed top-0 right-0 h-full ${expanded ? "w-[75vw] xl:w-[960px]" : "w-[440px]"} max-w-[92vw] bg-bg border-l border-line shadow-pop z-50 flex flex-col ${
          hasMounted ? "transition-[width] duration-200" : ""
        } ${
          closing ? "animate-[sema-slide-out-right_0.2s_ease-in_forwards]" : "animate-[sema-slide-in-right_0.2s_ease-out]"
        }`}
      >
        <header className="flex items-center justify-between px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="min-w-0">
            <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Drill-down</div>
            <div className="text-sm font-semibold text-ink truncate">{widget.title}</div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "Collapse panel" : "Expand panel"}
              title={expanded ? "Collapse panel" : "Expand panel"}
              className="hidden sm:flex shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink items-center justify-center transition"
            >
              {expanded ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
            </button>
            <button
              onClick={requestClose}
              aria-label="Close drill-down"
              className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-auto sema-scroll px-5 py-4">
          {chat.turns.length === 0 && (
            <div className="mt-6 text-center" dir={dir} style={{ textAlign: "center" }}>
              <div className="text-sm text-muted">
                {dir === "rtl" ? (
                  <>
                    שאל/י שאלת המשך לגבי <span className="font-medium text-ink">{widget.title}</span>.
                  </>
                ) : (
                  <>
                    Ask a follow-up about <span className="font-medium text-ink">{widget.title}</span>.
                  </>
                )}
              </div>
              {/* Recommendations arrive pre-filled in the input, so skip starters. */}
              {!widget.initialInput && (
                <div className="mt-3 flex flex-col gap-1.5">
                  {STARTERS[dir].map((s) => (
                    <button
                      key={s}
                      onClick={() => chat.send(s)}
                      dir={dir}
                      className="text-start text-[0.82rem] rounded-lg border border-lineSoft bg-primary/[0.06] text-primary-dark px-3 py-2 hover:bg-surface hover:border-primary transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {chat.turns.map((turn, i) => (
            <TurnView key={i} turn={turn} index={i} isFirst={i === 0} onRetry={chat.retry} />
          ))}
        </div>

        <div className="px-5 py-4 border-t border-line bg-bg shrink-0">
          <ChatInput
            onSend={chat.send}
            onStop={chat.stop}
            loading={chat.loading}
            initialValue={widget.initialInput}
            placeholder={dir === "rtl" ? `שאל/י לגבי ${widget.title}...` : `Ask about ${widget.title}...`}
          />
        </div>
      </aside>
    </>
  );
}
