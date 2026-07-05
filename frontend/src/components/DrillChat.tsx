import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
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
}

const STARTERS = ["Why did this change?", "Break this down by segment.", "What should I do about it?"];

const ANIM_MS = 220;

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
  const scrollRef = useRef<HTMLDivElement>(null);

  // Exit animation: the panel is on-screen by default (robust -- if animation
  // doesn't run it's still visible). Closing plays the slide-out/fade-out
  // keyframes, then unmounts via onClose.
  const [closing, setClosing] = useState(false);
  const requestClose = useCallback(() => {
    setClosing(true);
    window.setTimeout(onClose, ANIM_MS);
  }, [onClose]);

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
        className={`fixed top-0 right-0 h-full w-[440px] max-w-[92vw] bg-bg border-l border-line shadow-pop z-50 flex flex-col ${
          closing ? "animate-[sema-slide-out-right_0.2s_ease-in_forwards]" : "animate-[sema-slide-in-right_0.2s_ease-out]"
        }`}
      >
        <header className="flex items-center justify-between px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="min-w-0">
            <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Drill-down</div>
            <div className="text-sm font-semibold text-ink truncate">{widget.title}</div>
          </div>
          <button
            onClick={requestClose}
            aria-label="Close drill-down"
            className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            <X size={18} />
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-auto sema-scroll px-5 py-4">
          {chat.turns.length === 0 && (
            <div className="mt-6 text-center">
              <div className="text-sm text-muted">
                Ask a follow-up about <span className="font-medium text-ink">{widget.title}</span>.
              </div>
              {/* Recommendations arrive pre-filled in the input, so skip starters. */}
              {!widget.initialInput && (
                <div className="mt-3 flex flex-col gap-1.5">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      onClick={() => chat.send(s)}
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
            placeholder={`Ask about ${widget.title}...`}
          />
        </div>
      </aside>
    </>
  );
}
