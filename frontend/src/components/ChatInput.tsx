import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, Send, Square } from "lucide-react";

// Collapsed auto-grow cap: 6 lines of text-sm (20px leading) + py-1.5 padding.
const MAX_COLLAPSED_PX = 6 * 20 + 12;

export function ChatInput({
  onSend,
  onStop,
  loading,
  placeholder,
  suggestion,
  expandable,
}: {
  onSend: (text: string) => void;
  onStop?: () => void;
  loading?: boolean;
  placeholder?: string;
  /** Optional contextual follow-up shown as gray ghost text in the empty
   * input. Never part of the message unless the user accepts it (click/Tab). */
  suggestion?: string | null;
  /** Show the expand/collapse toggle (drill panel, where suggestions are long). */
  expandable?: boolean;
}) {
  const [value, setValue] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const ghostRef = useRef<HTMLDivElement>(null);

  // A new suggestion re-enables the ghost even if a previous one was dismissed.
  useEffect(() => setDismissed(false), [suggestion]);

  // The ghost only shows for an empty, idle input with an undismissed suggestion.
  const showGhost = !!suggestion && !value && !loading && !dismissed;

  // Auto-grow. Expanded mode is a fixed 40vh box, so only size in collapsed
  // mode. The ghost is absolutely positioned (no layout height of its own), so
  // its content height has to be folded in explicitly -- otherwise a
  // multi-line suggestion would overflow a one-row textarea.
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    if (expanded) {
      // Clear the auto-grow height, or the stale inline style would beat the
      // h-[40vh] class and the box wouldn't actually expand.
      ta.style.height = "";
      return;
    }
    ta.style.height = "0px";
    const ghostHeight = showGhost ? (ghostRef.current?.scrollHeight ?? 0) : 0;
    ta.style.height = `${Math.min(Math.max(ta.scrollHeight, ghostHeight), MAX_COLLAPSED_PX)}px`;
  }, [value, expanded, showGhost, suggestion]);

  const send = () => {
    const t = value.trim();
    if (t && !loading) {
      onSend(t);
      setValue("");
    }
  };

  // Accept the suggestion into the input as normal, editable text -- does NOT
  // send. Cursor goes to the end so the user can keep typing onto it.
  const accept = () => {
    if (!suggestion) return;
    setValue(suggestion);
    requestAnimationFrame(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(suggestion.length, suggestion.length);
    });
  };

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface shadow-card px-3 py-2">
      <div className="relative flex-1 min-w-0">
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!loading) send(); // sends actual input only; empty is a no-op
            } else if (e.key === "Tab" && showGhost) {
              // Accept the ghost with Tab only when the input is empty, so
              // normal focus-tabbing is preserved once the user has typed.
              e.preventDefault();
              accept();
            } else if (e.key === "Escape" && showGhost) {
              e.preventDefault();
              // Don't let Escape reach the drill panel's window listener, which
              // would close the whole panel instead of just dropping the ghost.
              e.stopPropagation();
              setDismissed(true);
            }
          }}
          rows={1}
          // The ghost overlay is aria-hidden (it's decorative once it stopped
          // being clickable), so the suggestion is announced from here instead.
          aria-label={
            showGhost
              ? `${placeholder || "Ask about revenue, customers, campaigns..."}. Suggested follow-up: ${suggestion}. Press Tab to accept.`
              : placeholder || "Ask about revenue, customers, campaigns..."
          }
          // Blank the placeholder while the ghost shows so they don't overlap.
          placeholder={showGhost ? "" : placeholder || "Ask about revenue, customers, campaigns..."}
          className={`w-full resize-none bg-transparent outline-none text-sm leading-5 text-ink placeholder:text-faint py-1.5 overflow-y-auto sema-scroll ${
            expanded ? "h-[40vh]" : ""
          }`}
        />

        {showGhost && (
          // Fully pointer-events-none: clicking anywhere -- including ON the
          // suggestion -- must land on the textarea and just place the caret,
          // leaving the ghost gray so the user can type straight over it.
          // Tab is the ONLY way to commit it. Font/leading/padding mirror the
          // textarea so the ghost lines up exactly.
          <div
            ref={ghostRef}
            aria-hidden="true"
            className={`pointer-events-none absolute inset-0 py-1.5 overflow-hidden ${expanded ? "overflow-y-auto" : ""}`}
          >
            <span
              dir="auto"
              className="block w-full text-start text-sm leading-5 text-faint whitespace-pre-wrap break-words pe-10"
            >
              {suggestion}
            </span>
            <kbd className="pointer-events-none absolute top-1.5 end-0 rounded border border-line bg-surface px-1 text-[0.65rem] leading-tight text-faint">
              Tab
            </kbd>
          </div>
        )}
      </div>

      <div className="shrink-0 flex flex-col items-center gap-1">
        {expandable && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Collapse input" : "Expand input"}
            title={expanded ? "Collapse input" : "Expand input"}
            className="w-9 h-7 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        )}
        {loading ? (
          <button
            onClick={onStop}
            className="w-9 h-9 rounded-xl bg-ink text-white flex items-center justify-center hover:bg-ink/90 transition"
            aria-label="Stop"
            title="Stop"
          >
            <Square size={13} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!value.trim()}
            className="w-9 h-9 rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 transition"
            aria-label="Send"
          >
            <Send size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
