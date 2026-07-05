import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { useMemo } from "react";
import type { DataTableModel } from "../lib/api";

type Row = Record<string, unknown>;

function prettify(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DataTable({ table }: { table: DataTableModel }) {
  const helper = createColumnHelper<Row>();
  const columns = useMemo(
    () =>
      table.columns.map((col) =>
        helper.accessor((row) => row[col], {
          id: col,
          header: prettify(col),
          cell: (info) => {
            const v = info.getValue();
            return v === null || v === undefined ? "" : String(v);
          },
        }),
      ),
    [table.columns],
  );

  const instance = useReactTable({
    data: table.rows as Row[],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="mt-3">
      {table.title && <div className="text-sm font-semibold text-ink mb-1.5">{table.title}</div>}
      <div className="overflow-auto sema-scroll rounded-xl border border-line max-h-80">
        <table className="w-full text-sm">
          <thead>
            {instance.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    className="bg-surfaceAlt text-[#475569] font-semibold text-start px-3 py-2 border-b border-line whitespace-nowrap"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
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
