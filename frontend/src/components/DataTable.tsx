import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ChevronLeft,
  ChevronRight,
  Download,
  MessageSquareText,
} from "lucide-react";
import type { DataTableModel } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { followUpsLabel, formatCell } from "../lib/format";
import { matchesHighlight } from "../lib/chart";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "../lib/tokens";
import { columnLabel } from "../lib/columnLabels";
import { CopyableBlock } from "./CopyButton";
import { copyRich, toHTMLTable, toTSV } from "../lib/clipboard";
import { ThreadBadge } from "./ThreadBadge";

type Row = Record<string, unknown>;

const PAGE_SIZE = 50;

/** RFC-4180 escaping: quote when the value contains a comma, quote or newline,
 * and double any embedded quotes. */
function csvEscape(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Export uses RAW values, not the display-formatted ones -- "10,856.1" would
 * re-import as text, and a thousands-separated id would be corrupted outright. */
function toCsv(columns: string[], rows: Row[]): string {
  const lines = [columns.map(csvEscape).join(",")];
  for (const r of rows) lines.push(columns.map((c) => csvEscape(r[c])).join(","));
  return lines.join("\r\n");
}

function downloadCsv(filename: string, csv: string): void {
  // The BOM makes Excel read it as UTF-8 (matters for Hebrew / accented names).
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function DataTable({
  table,
  dir,
  anchor,
  threadCount,
  onDrill,
  highlightValue,
}: {
  table: DataTableModel;
  dir?: "rtl" | "ltr";
  anchor?: { conversationId: string; turnIndex: number };
  threadCount?: (title: string) => number | undefined;
  onDrill?: (ctx: DrillContext) => void;
  /** The chart's own highlight_x, matched against this table's first column
   * (answer-screen redesign) -- so the chart's emphasized bar and this
   * table's emphasized row are always the SAME entity. Undefined/unmatched
   * highlights nothing, same silent-absence rule the chart follows. */
  highlightValue?: unknown;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const helper = createColumnHelper<Row>();

  const columns = useMemo(
    () =>
      table.columns.map((col) =>
        helper.accessor((row) => row[col], {
          id: col,
          header: columnLabel(col, dir),
          cell: (info) => formatCell(info.getValue(), col),
          // sort by the raw value (numbers/dates), not the formatted string
          sortingFn: "auto",
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [table.columns, dir],
  );

  const instance = useReactTable({
    data: table.rows as Row[],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
  });

  const loaded = table.rows.length;
  // Server-reported query total; older persisted turns predate the field.
  const total = table.total_rows ?? loaded;
  const { pageIndex } = instance.getState().pagination;
  const pageCount = instance.getPageCount();
  const first = loaded === 0 ? 0 : pageIndex * PAGE_SIZE + 1;
  const last = Math.min((pageIndex + 1) * PAGE_SIZE, loaded);

  const exportCsv = () => {
    // Every row in the current sort order -- not just the visible page.
    const rows = instance.getSortedRowModel().rows.map((r) => r.original);
    const name = (table.title || "sema-export").replace(/[^\w֐-׿ -]+/g, "").trim() || "sema-export";
    downloadCsv(`${name}.csv`, toCsv(table.columns, rows));
  };

  const tableTitle = table.title || "Table";
  const badge = threadCount?.(tableTitle);
  const drill = onDrill
    ? () =>
        onDrill({
          kind: "table",
          title: tableTitle,
          detail:
            `a table with columns ${table.columns.join(", ")}; ` +
            `${total} row(s), showing (JSON): ${JSON.stringify(table.rows.slice(0, 20))}`,
          dir,
          hue: CHART_PALETTE[0],
          ...anchor,
        })
    : undefined;

  // Copies the FULL sorted dataset, never just the visible page. TSV keeps
  // columns intact when pasted into Excel/Sheets; the HTML flavor gives rich
  // targets a real table.
  const copyTable = async () => {
    const rows = instance.getSortedRowModel().rows.map((r) => r.original);
    await copyRich(toTSV(table.columns, rows), toHTMLTable(table.columns, rows));
  };

  return (
    <CopyableBlock
      className="mt-3"
      title={`Copy all ${total.toLocaleString()} rows`}
      actions={[{ label: "Copy table", run: copyTable }]}
    >
      <div className="flex items-end justify-between gap-3 mb-1.5">
        {table.title && <div className="text-sm font-semibold text-ink">{table.title}</div>}
        {/* pe-9 keeps these clear of the floating copy control. */}
        <div className="shrink-0 ms-auto me-9 flex items-center gap-2">
          {typeof badge === "number" && <ThreadBadge count={badge} />}
          {drill && (
            <button
              onClick={drill}
              className="flex items-center gap-1 text-xs text-muted hover:text-primary transition"
              aria-label={`Ask about this table${followUpsLabel(badge)}`}
              title="Ask about this table"
            >
              <MessageSquareText size={14} /> Ask about this
            </button>
          )}
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs text-muted hover:text-primary hover:border-primary transition"
            title={`Download all ${total.toLocaleString()} rows as CSV`}
          >
            <Download size={13} /> Download CSV
          </button>
        </div>
      </div>
      <div className="rounded-xl border border-line overflow-hidden bg-surface">
        <span className="block h-[3px] w-full" style={{ background: CHART_PALETTE[0] }} aria-hidden />
        <div className="overflow-auto sema-scroll max-h-80">
        <table className="w-full text-sm">
          <thead>
            {instance.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h, colIndex) => {
                  const sorted = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className={`bg-surfaceAlt text-[#475569] font-semibold px-3 py-[9px] border-b border-line whitespace-nowrap cursor-pointer select-none hover:text-ink ${
                        colIndex === 0 ? "text-start" : "text-end"
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {sorted === "asc" ? (
                          <ChevronUp size={13} />
                        ) : sorted === "desc" ? (
                          <ChevronDown size={13} />
                        ) : (
                          <ChevronsUpDown size={13} className="opacity-30" />
                        )}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {instance.getRowModel().rows.map((row) => {
              const firstCell = row.getVisibleCells()[0];
              const highlighted = matchesHighlight(firstCell?.getValue(), highlightValue);
              return (
                <tr
                  key={row.id}
                  className="hover:bg-surfaceAlt/60"
                  style={highlighted ? { background: `${CHART_PALETTE[0]}14` } : undefined}
                >
                  {row.getVisibleCells().map((cell, colIndex) => {
                    const numeric = typeof cell.getValue() === "number";
                    const isMeasureCell = highlighted && colIndex === 1;
                    return (
                      <td
                        key={cell.id}
                        className={`px-3 py-[9px] border-b border-lineSoft whitespace-nowrap ${
                          numeric ? "text-end tabular-nums" : ""
                        } ${highlighted && colIndex === 0 ? "font-semibold" : ""} ${
                          isMeasureCell ? "font-semibold" : "text-ink"
                        }`}
                        style={isMeasureCell ? { color: CHART_PALETTE_TEXT[0] } : undefined}
                      >
                        {colIndex === 0 ? (
                          <span className="inline-flex items-center gap-[7px]">
                            <span
                              className="shrink-0 inline-block w-[7px] h-[7px] rounded-sm"
                              style={{ background: highlighted ? CHART_PALETTE[0] : "#CBD5E1" }}
                              aria-hidden
                            />
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </span>
                        ) : (
                          flexRender(cell.column.columnDef.cell, cell.getContext())
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 text-xs text-muted">
        <div>
          Showing <span className="font-medium text-ink">{first.toLocaleString()}</span>–
          <span className="font-medium text-ink">{last.toLocaleString()}</span> of{" "}
          <span className="font-medium text-ink">{total.toLocaleString()}</span>
          {table.truncated && (
            <span className="ms-1 text-orange-700" title={`The query returned more rows than the ${total.toLocaleString()}-row safety cap.`}>
              (capped)
            </span>
          )}
        </div>

        {pageCount > 1 && (
          // Isolated LTR: pager digits/chevrons are LTR everywhere in the app
          // (same convention as SQL/IDs), regardless of the answer's dir --
          // otherwise an RTL ancestor mirrors this row's flex order while the
          // chevron glyphs stay fixed, so "next" visually ends up on the left
          // pointing away from its own action.
          <div dir="ltr" className="flex items-center gap-1">
            <button
              onClick={() => instance.previousPage()}
              disabled={!instance.getCanPreviousPage()}
              aria-label="Previous page"
              className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-surfaceAlt hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="tabular-nums">
              Page {(pageIndex + 1).toLocaleString()} of {pageCount.toLocaleString()}
            </span>
            <button
              onClick={() => instance.nextPage()}
              disabled={!instance.getCanNextPage()}
              aria-label="Next page"
              className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-surfaceAlt hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        )}
      </div>
    </CopyableBlock>
  );
}
