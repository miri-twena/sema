import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronsLeft, X } from "lucide-react";
import { useChat } from "../hooks/useChat";
import { useChatScroll } from "../hooks/useChatScroll";
import { drillPlaceholder } from "../lib/chatCopy";
import { useUiLang } from "../lib/useUiLang";
import { ChatInput } from "./ChatInput";
import { ScrollToLatest } from "./ScrollToLatest";
import { TurnView } from "./TurnView";

// The focused context passed when a widget (KPI / chart) or a recommended
// action is clicked. Structured DATA fields only (kind/title/detail) -- the
// SERVER builds the prompt framing from them; the client never assembles
// context text itself (that was a prompt-injection surface). `initialInput`
// (recommendations) pre-fills the input instead of showing generic starters.
export interface DrillContext {
  kind: "kpi" | "chart" | "table" | "action";
  title: string;
  /** Widget data summary (value text, chart axes + data preview, action text). */
  detail: string;
  initialInput?: string;
  /** Direction of the ORIGINAL question that produced this widget (KPI/chart/
   * action). Drives which language the drill panel's static UI (suggested
   * follow-ups, labels) uses -- a Hebrew question should get a Hebrew
   * follow-up panel, not just Hebrew-rendered answer text. */
  dir?: "rtl" | "ltr";
  /** Anchor for a PERSISTED thread: which conversation + turn this widget's
   * answer belongs to. Set by the leaf widget (KpiCards/ChartRenderer/
   * DataTable/RecommendedActions) from the anchor it was handed; undefined
   * for a widget with no parent conversation (the home-screen dashboard),
   * which stays ephemeral -- never persisted, never badged. */
  conversationId?: string;
  turnIndex?: number;
  /** The anchor's EXISTING thread id, if any -- resolved by App.tsx's onDrill
   * (via useThreads) before the panel opens, so DrillChat can load prior
   * turns without a second round-trip to discover it. Undefined when this
   * will be the anchor's first turn. */
  threadId?: string;
}

/** Looks up how many follow-up questions have already been asked about one
 * widget, for its thread badge -- `turnIndex` + `kind` + `title` identify the
 * widget. Stable across renders (backed by useThreads' useCallback) so
 * passing it down through TurnView does not defeat its memoization;
 * AssistantResponseCard bakes in its own turnIndex to build the simpler
 * per-kind `(title) => count` closures each leaf widget actually takes. */
export type ThreadCountLookup = (
  turnIndex: number,
  kind: DrillContext["kind"],
  title: string,
) => number | undefined;

const STARTERS: Record<"ltr" | "rtl", string[]> = {
  ltr: ["Why did this change?", "Break this down by segment.", "What should I do about it?"],
  rtl: ["למה זה השתנה?", "פרט/י לפי פלח.", "מה כדאי לעשות בנידון?"],
};

const ANIM_MS = 220;
const EXPANDED_KEY = "sema.drill.expanded";

// A slide-in sub-chat scoped to one widget / action -- now a first-class,
// PERSISTENT thread when the widget has a parent conversation (see
// DrillContext.conversationId/turnIndex): every turn is saved server-side via
// the SAME chat endpoint the main chat uses, just anchored to this widget
// instead of appended to the main transcript. Reopening the same widget
// resumes its thread. A widget with no parent conversation (the home-screen
// dashboard) still runs ephemeral, exactly as before threads existed.
export function DrillChat({
  widget,
  clientId,
  onClose,
  onThreadUpdated,
}: {
  widget: DrillContext;
  clientId: string;
  onClose: () => void;
  /** Called after a turn completes in a PERSISTED thread, so the opener
   * (App.tsx) can refresh its thread-summary badges. Never fires for an
   * anchor-less (ephemeral) drill. */
  onThreadUpdated?: () => void;
}) {
  const drillContext = useMemo(
    () => ({ kind: widget.kind, title: widget.title, detail: widget.detail }),
    [widget.kind, widget.title, widget.detail],
  );
  // Only a widget with BOTH a parent conversation and a turn index gets a
  // persisted thread -- matches the server's own rule for when a request
  // resolves to a thread rather than an ordinary (and here, unwanted)
  // conversation. Memoized so its identity is stable for the lifetime of this
  // panel, same reasoning as drillContext above.
  const threadAnchor = useMemo(
    () =>
      widget.conversationId !== undefined && widget.turnIndex !== undefined
        ? { conversationId: widget.conversationId, turnIndex: widget.turnIndex }
        : undefined,
    [widget.conversationId, widget.turnIndex],
  );
  const chat = useChat({
    clientId,
    drillContext,
    threadAnchor,
    persistKey: null,
    // Fires after EVERY successful turn in a persisted thread (the parent
    // conversation_id is echoed back on each response) -- exactly the "a
    // drill turn completed" signal the caller needs to refresh badges.
    onConversationChanged: onThreadUpdated,
  });
  const dir = widget.dir ?? "ltr";
  // The header shows the title in full; the placeholder still needs a short
  // form so it stays readable on one line.
  const shortTitle = widget.title.length > 40 ? widget.title.slice(0, 40) + "…" : widget.title;
  // The input's ghost placeholder follows the ORG's language (same source as
  // the main chat input) -- distinct from `dir` above, which mirrors the
  // ORIGINAL question's language for the rest of this panel's static UI.
  const lang = useUiLang();
  const { scrollRef, lastAnswerRef, onScroll, showScrollToLatest, scrollToLatest, reattach } =
    useChatScroll(chat.turns);

  // Load the anchor's EXISTING thread, if one was already found (see
  // DrillContext.threadId) -- once, on mount. Empty-dep effect is deliberate:
  // this panel is remounted per drill-down (App.tsx keys it by widget via
  // conditional render), never reused across a different anchor.
  const openThreadRef = useRef(chat.openThread);
  openThreadRef.current = chat.openThread;
  useEffect(() => {
    if (widget.threadId) void openThreadRef.current(widget.threadId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Exit animation: the panel is on-screen by default (robust -- if animation
  // doesn't run it's still visible). Closing plays the slide-out/fade-out
  // keyframes, then unmounts via onClose.
  const [closing, setClosing] = useState(false);

  const close = useCallback(() => {
    setClosing(true);
    window.setTimeout(onClose, ANIM_MS);
  }, [onClose]);

  // Every turn is either persisted (a real thread) or ephemeral by explicit
  // design (the home dashboard) -- either way there is nothing to warn about,
  // so closing is always immediate. (Superseded the discard-confirmation flow
  // this used to have: with real persistence, "you'll lose this" is simply no
  // longer true.)
  const requestClose = close;

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
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && requestClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [requestClose]);

  const send = useCallback(
    (q: string) => {
      reattach();
      chat.send(q);
    },
    [chat, reattach],
  );

  return (
    <>
      {/* No backdrop at 2xl+: the panel docks beside the chat as a static
          column there (see the aside below), so nothing needs dimming and
          the main chat stays clickable. */}
      <div
        className={`fixed inset-0 bg-ink/20 z-40 2xl:hidden ${
          closing ? "animate-[sema-fade-out_0.2s_ease-in_forwards]" : "animate-[sema-fade-in_0.2s_ease-out]"
        }`}
        onClick={requestClose}
      />
      <aside
        className={`fixed top-0 end-0 h-full 2xl:static 2xl:h-auto ${expanded ? "w-[75vw] xl:w-[960px]" : "w-[440px]"} max-w-[92vw] bg-bg border-s border-line shadow-pop 2xl:shadow-none z-50 flex flex-col ${
          hasMounted ? "transition-[width] duration-200" : ""
        } ${
          closing ? "animate-[sema-slide-out-end_0.2s_ease-in_forwards]" : "animate-[sema-slide-in-end_0.2s_ease-out]"
        }`}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-line bg-surface shrink-0">
          <div className="min-w-0">
            <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Drill-down</div>
            {/* No truncation: the full action/widget title wraps to 2-3 lines.
             * The header is shrink-0 in a flex column, so the panel below just
             * shifts down. */}
            <div className="text-sm font-semibold text-ink break-words leading-snug">{widget.title}</div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "Collapse panel" : "Expand panel"}
              title={expanded ? "Collapse panel" : "Expand panel"}
              className="hidden sm:flex 2xl:hidden shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink items-center justify-center transition"
            >
              {/* One icon, rotated: the chevrons point toward the inline-start
                  edge to expand and back again to collapse, which reverses in
                  RTL. Two physical icons would each be wrong in one direction. */}
              <ChevronsLeft
                size={18}
                className={`transition-transform ${expanded ? "rotate-180" : ""} rtl:-scale-x-100`}
              />
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

        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="relative flex-1 overflow-auto sema-scroll px-5 py-4"
        >
          {/* An existing thread is loading (openThread on mount): turns.length
              is still 0 here since loading a thread never pushes a placeholder
              turn the way send() does -- so this combination is unambiguous. */}
          {chat.turns.length === 0 && chat.loading ? (
            <div className="mt-6 flex flex-col gap-2" aria-busy="true">
              <div className="h-4 w-2/3 rounded bg-surfaceAlt animate-pulse" />
              <div className="h-16 w-full rounded-xl bg-surfaceAlt animate-pulse" />
            </div>
          ) : (
            chat.turns.length === 0 && (
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
                        onClick={() => send(s)}
                        dir={dir}
                        className="text-start text-[0.82rem] rounded-lg border border-lineSoft bg-primary/[0.06] text-primary-dark px-3 py-2 hover:bg-surface hover:border-primary transition"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          )}

          {chat.turns.map((turn, i) => (
            <TurnView
              key={i}
              turn={turn}
              index={i}
              isFirst={i === 0}
              answerRef={i === chat.turns.length - 1 ? lastAnswerRef : undefined}
              onRetry={(idx) => {
                reattach();
                chat.retry(idx);
              }}
              onAsk={send}
            />
          ))}
          {showScrollToLatest && <ScrollToLatest onClick={scrollToLatest} />}
        </div>

        <div className="px-5 py-4 border-t border-line bg-bg shrink-0">
          <ChatInput
            onSend={send}
            onStop={chat.stop}
            loading={chat.loading}
            expandable
            // Ghost text, not a pre-filled value -- a pre-filled input blocked
            // the user from just typing their own question.
            suggestion={widget.initialInput}
            placeholder={drillPlaceholder(lang, shortTitle)}
          />
        </div>
      </aside>
    </>
  );
}
