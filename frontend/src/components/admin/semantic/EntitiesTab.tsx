import { useEffect, useState } from "react";
import { Info, Table2 } from "lucide-react";
import { api, type DataSourceType, type SchemaResponse } from "../../../lib/api";

const SOURCE_LABEL: Record<DataSourceType, string> = {
  postgres: "PostgreSQL",
  priority: "Priority ERP",
  salesforce: "Salesforce",
};

/** A relationship entry's shape varies by source; read defensively rather
 * than assuming a fixed contract. */
function relationshipLabel(rel: Record<string, unknown>): string {
  const from = String(rel.from_table ?? rel.from ?? rel.table ?? "?");
  const fromCol = String(rel.from_column ?? rel.column ?? "");
  const to = String(rel.to_table ?? rel.to ?? rel.references ?? "?");
  const toCol = String(rel.to_column ?? "");
  return `${from}${fromCol ? `.${fromCol}` : ""} → ${to}${toCol ? `.${toCol}` : ""}`;
}

/**
 * Entities tab (spec §6.4): read-only, auto-derived entirely from the same
 * schema introspection /api/schema already exposes (tables + relationships)
 * -- no hand-authored entities.yaml to drift out of sync with the real
 * database. Editing is a later slice.
 */
export function EntitiesTab() {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .schema()
      .then((s) => !cancelled && setSchema(s))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <div className="flex items-start gap-2.5 rounded-xl border border-lineSoft bg-primary/[0.04] px-4 py-3 mb-5">
        <Info size={15} className="shrink-0 mt-0.5 text-primary" />
        <p className="text-[0.8rem] text-ink">
          Entities are derived automatically from the database schema. Editing entity
          definitions and join rules arrives in a future release.
        </p>
      </div>

      {error ? (
        <p className="text-sm text-muted py-8 text-center">Couldn't load the schema. Please try again.</p>
      ) : !schema ? (
        <p className="text-sm text-muted py-8 text-center">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {schema.tables.map((t) => {
            const joins = schema.relationships.filter(
              (r) => relationshipLabel(r).startsWith(`${t.name}.`) || relationshipLabel(r).startsWith(`${t.name} `),
            );
            return (
              <div key={t.name} className="rounded-xl2 border border-line bg-surface p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-lg bg-primary/10 text-primary">
                    <Table2 size={14} />
                  </span>
                  <span className="font-medium text-ink">{t.name}</span>
                  <span className="ms-auto inline-flex items-center rounded-full bg-surfaceAlt px-2 py-0.5 text-[0.68rem] font-medium text-muted">
                    {SOURCE_LABEL[t.source] ?? t.source}
                  </span>
                </div>
                <p className="text-[0.68rem] text-faint mb-2">{t.columns.length} columns</p>
                <p className="text-[0.72rem] text-muted mb-2">
                  {t.columns.slice(0, 6).map((c) => c.name).join(", ")}
                  {t.columns.length > 6 ? "…" : ""}
                </p>
                {joins.length > 0 && (
                  <div className="pt-2 border-t border-lineSoft">
                    <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-1">
                      Joins
                    </p>
                    <div className="flex flex-col gap-0.5" dir="ltr">
                      {joins.map((r, i) => (
                        <code key={i} className="text-[0.72rem] text-muted">
                          {relationshipLabel(r)}
                        </code>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {schema.tables.length === 0 && (
            <p className="text-sm text-muted py-8 text-center col-span-2">No tables found.</p>
          )}
        </div>
      )}
    </div>
  );
}
