import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, Send, Sparkles, Square } from "lucide-react";
import { useT } from "../locales";
import { useUiLang } from "../lib/useUiLang";

// Collapsed auto-grow cap: 6 lines of text-sm (20px leading) + py-1.5 padding.
const MAX_COLLAPSED_PX = 6 * 20 + 12;

export const ChatInput = forwardRef<HTMLTextAreaElement, {
  onSend: (text: string) => void;
  onStop?: () => void;
  loading?: boolean;
  placeholder?: string;
  /** Overrides the empty-input direction for `placeholder` specifically --
   * dir="auto" doesn't reliably apply to placeholder text (see the textarea's
   * own dir comment below), so a caller cycling through content in a
   * language OTHER than the org's chrome language (home_ask_bar_top_prompt.md
   * item 3: real suggested questions, which may be Hebrew in an
   * English-chrome org or vice versa) needs to say so explicitly. Ignored
   * once there's real input (dir="auto" takes over, as always). */
  placeholderDir?: "rtl" | "ltr";
  /** Optional contextual follow-up shown as gray ghost text in the empty
   * input. Never part of the message unless the user accepts it (click/Tab). */
  suggestion?: string | null;
  /** Show the expand/collapse toggle (drill panel, where suggestions are long). */
  expandable?: boolean;
  /** "hero" is the home screen's prominent top-of-page entry point
   * (home_ask_bar_top_prompt.md) -- larger type/padding and a leading
   * sparkles icon. Behavior is byte-for-byte identical to "default" (the
   * in-conversation composer); only sizing/chrome differ. */
  variant?: "default" | "hero";
  /** Focus on mount -- the caller decides WHEN to ask for it; this component
   * decides whether to actually honor it (never on a touch-primary device,
   * to avoid popping the virtual keyboard on load). */
  autoFocus?: boolean;
  /** Fires once the textarea gains focus -- home_ask_bar_top_prompt.md's
   * "cycling pauses permanently once focused" needs to know this without
   * the parent reaching into the DOM. */
  onFocus?: () => void;
}>(function ChatInput(
  { onSend, onStop, loading, placeholder, placeholderDir, suggestion, expandable, variant = "default", autoFocus, onFocus },
  forwardedRef,
) {
  const [value, setValue] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const ghostRef = useRef<HTMLDivElement>(null);
  // Set right before the autoFocus effect below calls .focus(), so the
  // textarea's onFocus handler can tell "this is the mount-time autofocus"
  // apart from a REAL user-initiated focus -- see that handler's own comment.
  const suppressNextFocus = useRef(false);
  useImperativeHandle(forwardedRef, () => taRef.current as HTMLTextAreaElement, []);
  // Org-language default, used only when the caller doesn't pass its own
  // placeholder (e.g. DrillChat always does, with its own interpolated text).
  const lang = useUiLang();
  const t = useT();
  const defaultPlaceholder = t.chat.placeholder;
  const hero = variant === "hero";

  // A new suggestion re-enables the ghost even if a previous one was dismissed.
  useEffect(() => setDismissed(false), [suggestion]);

  // Never autofocus on a touch-primary device -- popping the virtual
  // keyboard the instant the home screen loads is worse than a manual tap.
  useEffect(() => {
    if (!autoFocus) return;
    const isTouch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
    if (!isTouch) {
      // A browser dispatches `focus` synchronously inside .focus(), so this
      // flag is read-and-cleared by the handler below before this line returns.
      suppressNextFocus.current = true;
      taRef.current?.focus();
    }
    // Mount-only: re-focusing on every prop change would steal focus back
    // from wherever the user moved it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    const cap = hero ? MAX_COLLAPSED_PX + 8 : MAX_COLLAPSED_PX; // hero's larger line-height needs a touch more room
    ta.style.height = `${Math.min(Math.max(ta.scrollHeight, ghostHeight), cap)}px`;
  }, [value, expanded, showGhost, suggestion, hero]);

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
    <div
      // The row itself (icon/textarea/buttons left-to-right vs right-to-left)
      // follows the ORG CHROME language, same as every other header row this
      // was just fixed for -- independent of `placeholderDir`, which only
      // ever governs the TEXT inside the textarea. A user flagged via a live
      // screenshot that this bar stayed physically left-anchored (icon left,
      // send button right) even in a Hebrew-chrome org.
      dir={lang === "he" ? "rtl" : "ltr"}
      className={
        hero
          ? "flex items-center gap-3 rounded-2xl border border-line bg-surface shadow-card px-4 py-2.5 focus-within:border-primary transition-colors"
          : "flex items-end gap-2 rounded-2xl border border-line bg-surface shadow-card px-3 py-2"
      }
    >
      {hero && <Sparkles size={18} className="text-primary shrink-0" aria-hidden />}
      <div className="relative flex-1 min-w-0">
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => {
            // The mount-time autoFocus itself must not count as "the user
            // focused it" (home_ask_bar_top_prompt.md's cycling placeholder
            // would otherwise freeze before ever cycling once on desktop,
            // where autoFocus fires immediately) -- only a REAL subsequent
            // focus (click, Tab, or the first focus on a touch device where
            // autoFocus never fires at all) reports upward.
            if (suppressNextFocus.current) {
              suppressNextFocus.current = false;
              return;
            }
            onFocus?.();
          }}
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
          // While empty, the placeholder's own language decides direction
          // (chat_placeholder_language_prompt.md item 1) -- browsers don't
          // reliably apply dir="auto" to placeholder text the way they do to
          // a real value, so this can't just be a static "auto". Once there's
          // real input, "auto" takes over and follows whatever's actually
          // typed (an English question stays LTR even with a Hebrew org).
          // `placeholderDir`, when given, wins over the org-chrome default --
          // see its own doc comment above.
          dir={value ? "auto" : placeholderDir ?? (lang === "he" ? "rtl" : "ltr")}
          // The ghost overlay is aria-hidden (it's decorative once it stopped
          // being clickable), so the suggestion is announced from here instead.
          aria-label={
            showGhost
              ? `${placeholder || defaultPlaceholder}. Suggested follow-up: ${suggestion}. Press Tab to accept.`
              : placeholder || defaultPlaceholder
          }
          // Blank the placeholder while the ghost shows so they don't overlap.
          placeholder={showGhost ? "" : placeholder || defaultPlaceholder}
          className={`w-full resize-none bg-transparent outline-none text-ink placeholder:text-faint overflow-y-auto sema-scroll ${
            hero ? "text-base leading-6 py-2" : "text-sm leading-5 py-1.5"
          } ${expanded ? "h-[40vh]" : ""}`}
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
            className={`pointer-events-none absolute inset-0 overflow-hidden ${hero ? "py-2" : "py-1.5"} ${expanded ? "overflow-y-auto" : ""}`}
          >
            <span
              dir="auto"
              className={`block w-full text-start text-faint whitespace-pre-wrap break-words pe-10 ${hero ? "text-base leading-6" : "text-sm leading-5"}`}
            >
              {suggestion}
            </span>
            <kbd className="pointer-events-none absolute top-1.5 end-0 rounded border border-line bg-surface px-1 text-[0.65rem] leading-tight text-faint">
              Tab
            </kbd>
          </div>
        )}
      </div>

      <div className={hero ? "shrink-0 flex items-center gap-1" : "shrink-0 flex flex-col items-center gap-1"}>
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
            className={`rounded-xl bg-ink text-white flex items-center justify-center hover:bg-ink/90 transition ${hero ? "w-10 h-10" : "w-9 h-9"}`}
            aria-label="Stop"
            title="Stop"
          >
            <Square size={13} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!value.trim()}
            className={`rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 transition ${hero ? "w-10 h-10" : "w-9 h-9"}`}
            aria-label="Send"
          >
            <Send size={hero ? 17 : 16} />
          </button>
        )}
      </div>
    </div>
  );
});
