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
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight, Download } from "lucide-react";
import type { DataTableModel } from "../lib/api";
import { formatCell } from "../lib/format";
import { CopyableBlock } from "./CopyButton";
import { copyRich, toHTMLTable, toTSV } from "../lib/clipboard";

type Row = Record<string, unknown>;

const PAGE_SIZE = 50;

function prettify(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

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

export function DataTable({ table }: { table: DataTableModel }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const helper = createColumnHelper<Row>();

  const columns = useMemo(
    () =>
      table.columns.map((col) =>
        helper.accessor((row) => row[col], {
          id: col,
          header: prettify(col),
          cell: (info) => formatCell(info.getValue(), col),
          // sort by the raw value (numbers/dates), not the formatted string
          sortingFn: "auto",
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [table.columns],
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
        {/* pe-9 keeps the CSV button clear of the floating copy control. */}
        <button
          onClick={exportCsv}
          className="shrink-0 ms-auto me-9 flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs text-muted hover:text-primary hover:border-primary transition"
          title={`Download all ${total.toLocaleString()} rows as CSV`}
        >
          <Download size={13} /> Download CSV
        </button>
      </div>
      <div className="overflow-auto sema-scroll rounded-xl border border-line max-h-80">
        <table className="w-full text-sm">
          <thead>
            {instance.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className="bg-surfaceAlt text-[#475569] font-semibold text-start px-3 py-2 border-b border-line whitespace-nowrap cursor-pointer select-none hover:text-ink"
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
            {instance.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-surfaceAlt/60">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 border-b border-lineSoft text-ink whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
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
          <div className="flex items-center gap-1">
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
