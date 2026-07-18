import { useMemo, useState } from "react";
import { Copy, Check, Database } from "lucide-react";
import { formatSql, highlightLine } from "../lib/sql";

/**
 * Read-only SQL viewer: auto-formats the query, syntax-highlights it, and shows
 * it in a modern code block (toolbar + line numbers + monospace). Always LTR --
 * SQL reads left-to-right even inside an RTL answer card. Not editable.
 */
export function SqlBlock({ sql }: { sql: string }) {
  const formatted = useMemo(() => formatSql(sql), [sql]);
  const lines = useMemo(() => formatted.split("\n"), [formatted]);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(formatted);
      setCopied(true);
      setToast(true);
      window.setTimeout(() => setCopied(false), 1500);
      window.setTimeout(() => setToast(false), 1800);
    } catch {
      /* clipboard blocked (e.g. no document focus) -- nothing to show */
    }
  };

  return (
    <div dir="ltr" className="sema-sql relative mt-2 overflow-hidden rounded-xl border border-line bg-surfaceAlt">
      {/* toolbar */}
      <div className="flex items-center justify-between border-b border-line bg-surface/70 px-3 py-1.5">
        <div className="flex items-center gap-1.5 text-[0.68rem] font-semibold uppercase tracking-wide text-muted">
          <Database size={12} className="text-primary/70" /> SQL
        </div>
        <button
          onClick={copy}
          aria-label="Copy SQL"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted transition hover:bg-surfaceAlt hover:text-ink"
        >
          {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {/* code -- horizontal scroll only when a line is too wide to fit */}
      <div className="overflow-x-auto sema-scroll">
        <table className="border-collapse font-mono text-[0.75rem] leading-relaxed">
          <tbody>
            {lines.map((line, i) => (
              <tr key={i}>
                <td className="select-none border-r border-line/70 px-3 text-end align-top tabular-nums text-faint/70">
                  {i + 1}
                </td>
                <td className="whitespace-pre pl-3 pr-4 align-top text-ink">
                  {highlightLine(line).map((seg, j) =>
                    seg.cls ? (
                      <span key={j} className={seg.cls}>
                        {seg.text}
                      </span>
                    ) : (
                      <span key={j}>{seg.text}</span>
                    ),
                  )}
                  {line === "" ? "​" : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* success toast */}
      {toast && (
        <div
          role="status"
          className="pointer-events-none absolute right-3 top-2 rounded-lg bg-ink px-2.5 py-1 text-[0.7rem] text-white shadow-pop animate-[sema-fade-in_0.15s_ease-out]"
        >
          Copied to clipboard
        </div>
      )}
    </div>
  );
}
