import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import type { DataTableModel } from "../lib/api";
import { formatCell } from "../lib/format";

type Row = Record<string, unknown>;

function prettify(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
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
          cell: (info) => formatCell(info.getValue()),
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
  });

  return (
    <div className="mt-3">
      {table.title && <div className="text-sm font-semibold text-ink mb-1.5">{table.title}</div>}
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
    </div>
  );
}
