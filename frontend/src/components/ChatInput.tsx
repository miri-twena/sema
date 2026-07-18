import { useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";

export function ChatInput({
  onSend,
  onStop,
  loading,
  placeholder,
  initialValue,
  suggestion,
}: {
  onSend: (text: string) => void;
  onStop?: () => void;
  loading?: boolean;
  placeholder?: string;
  initialValue?: string;
  /** Optional contextual follow-up shown as gray ghost text in the empty
   * input. Never part of the message unless the user accepts it (click/Tab). */
  suggestion?: string | null;
}) {
  const [value, setValue] = useState(initialValue ?? "");
  const [dismissed, setDismissed] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // A new suggestion re-enables the ghost even if a previous one was dismissed.
  useEffect(() => setDismissed(false), [suggestion]);

  // The ghost only shows for an empty, idle input with an undismissed suggestion.
  const showGhost = !!suggestion && !value && !loading && !dismissed;

  const send = () => {
    const t = value.trim();
    if (t && !loading) {
      onSend(t);
      setValue("");
    }
  };

  // Accept the suggestion into the input as normal, editable text -- does NOT
  // send. The user can then edit it or press Enter to send.
  const accept = () => {
    if (!suggestion) return;
    setValue(suggestion);
    taRef.current?.focus();
  };

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface shadow-card px-3 py-2">
      <div className="relative flex-1">
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
              setDismissed(true);
            }
          }}
          rows={1}
          aria-label={placeholder || "Ask about revenue, customers, campaigns..."}
          // Blank the placeholder while the ghost shows so they don't overlap.
          placeholder={showGhost ? "" : placeholder || "Ask about revenue, customers, campaigns..."}
          className="w-full resize-none bg-transparent outline-none text-sm text-ink placeholder:text-faint py-1.5 max-h-32"
        />

        {showGhost && (
          // pointer-events-none lets clicks on the empty area reach the textarea
          // (to type custom text); only the suggestion + hint are interactive.
          <div className="pointer-events-none absolute inset-0 py-1.5 flex items-center gap-2">
            <button
              type="button"
              onClick={accept}
              tabIndex={-1}
              dir="auto"
              aria-label={`Suggested follow-up: ${suggestion}. Press Tab or click to use.`}
              className="pointer-events-auto min-w-0 truncate text-start text-sm text-faint hover:text-muted transition"
            >
              {suggestion}
            </button>
            <kbd className="pointer-events-none shrink-0 rounded border border-line px-1 text-[0.65rem] leading-tight text-faint">
              Tab
            </kbd>
          </div>
        )}
      </div>

      {loading ? (
        <button
          onClick={onStop}
          className="shrink-0 w-9 h-9 rounded-xl bg-ink text-white flex items-center justify-center hover:bg-ink/90 transition"
          aria-label="Stop"
          title="Stop"
        >
          <Square size={13} fill="currentColor" />
        </button>
      ) : (
        <button
          onClick={send}
          disabled={!value.trim()}
          className="shrink-0 w-9 h-9 rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 transition"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
      )}
    </div>
  );
}
