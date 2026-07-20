import { useState } from "react";
import { Copy, Check, RotateCw } from "lucide-react";
import { copyText } from "../lib/clipboard";

/**
 * Action row shown under a completed answer. This is the "copy the WHOLE
 * answer" escape hatch -- per-block copy (CopyButton/CopyableBlock, floated
 * into each block) is the primary interaction, so there is no chart-image
 * button here any more; the chart owns that action itself.
 */
export function MessageActions({ text, onRetry }: { text: string; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  const copyAll = async () => {
    try {
      await copyText(text);
      setFailed(false);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setFailed(true);
    }
  };

  const btn =
    "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-surfaceAlt hover:text-ink transition";

  return (
    <div dir="ltr" className="mt-3 pt-2.5 border-t border-line flex items-center gap-1">
      <button onClick={copyAll} className={btn} title="Copy the entire answer" aria-label="Copy entire answer">
        {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
        {copied ? "Copied" : "Copy answer"}
      </button>

      {onRetry && (
        <button onClick={onRetry} className={btn} title="Ask this question again" aria-label="Retry question">
          <RotateCw size={14} /> Retry
        </button>
      )}

      {failed && <span className="text-xs text-muted ms-1">Copy failed</span>}
    </div>
  );
}
