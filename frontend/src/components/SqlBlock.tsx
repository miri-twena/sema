import { useMemo } from "react";
import { Database } from "lucide-react";
import { formatSql, highlightLine } from "../lib/sql";
import { copyText } from "../lib/clipboard";
import { CopyableBlock } from "./CopyButton";

/**
 * Read-only SQL viewer: auto-formats the query, syntax-highlights it, and shows
 * it in a modern code block (toolbar + line numbers + monospace). Always LTR --
 * SQL reads left-to-right even inside an RTL answer card. Not editable.
 */
export function SqlBlock({ sql }: { sql: string }) {
  const formatted = useMemo(() => formatSql(sql), [sql]);
  const lines = useMemo(() => formatted.split("\n"), [formatted]);

  return (
    // dir="ltr" on the host both isolates the SQL from surrounding RTL text and
    // pins the copy button to the visual right (see CopyableBlock).
    <CopyableBlock
      dir="ltr"
      className="sema-sql mt-2 overflow-hidden rounded-xl border border-line bg-surfaceAlt"
      title="Copy SQL"
      // Copies the formatted SQL exactly as displayed -- plain text, without the
      // line-number column or any highlighting markup.
      actions={[{ label: "Copy SQL", run: () => copyText(formatted) }]}
    >
      {/* toolbar */}
      <div className="flex items-center justify-between border-b border-line bg-surface/70 px-3 py-1.5">
        <div className="flex items-center gap-1.5 text-[0.68rem] font-semibold uppercase tracking-wide text-muted">
          <Database size={12} className="text-primary/70" /> SQL
        </div>
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
    </CopyableBlock>
  );
}
