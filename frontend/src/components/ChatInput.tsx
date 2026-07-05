import { useState } from "react";
import { Send, Square } from "lucide-react";

export function ChatInput({
  onSend,
  onStop,
  loading,
  placeholder,
  initialValue,
}: {
  onSend: (text: string) => void;
  onStop?: () => void;
  loading?: boolean;
  placeholder?: string;
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue ?? "");

  const send = () => {
    const t = value.trim();
    if (t && !loading) {
      onSend(t);
      setValue("");
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface shadow-card px-3 py-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!loading) send();
          }
        }}
        rows={1}
        placeholder={placeholder || "Ask about revenue, customers, campaigns..."}
        className="flex-1 resize-none bg-transparent outline-none text-sm text-ink placeholder:text-faint py-1.5 max-h-32"
      />
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
