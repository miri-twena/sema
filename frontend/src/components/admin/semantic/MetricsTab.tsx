import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { SemanticMetricItem, SemanticModelResponse } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { MetricEditor } from "./MetricEditor";

const STATUS_DOT: Record<string, string> = {
  certified: "bg-emerald-500",
  draft: "bg-sun",
  deprecated: "bg-faint",
};

/**
 * Two-pane Metrics tab (spec §6.4 mockup): a searchable list on the left
 * (draft dot indicator), the selected metric's editor on the right.
 */
export function MetricsTab({
  model,
  semantic,
}: {
  model: SemanticModelResponse;
  semantic: SemanticModelHook;
}) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(model.metrics[0]?.name ?? null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return model.metrics;
    return model.metrics.filter(
      (m) => m.name.toLowerCase().includes(q) || m.label.toLowerCase().includes(q),
    );
  }, [model.metrics, search]);

  const selectedMetric: SemanticMetricItem | undefined = model.metrics.find(
    (m) => m.name === selected,
  );

  return (
    <div className="flex gap-6">
      {/* List pane */}
      <div className="w-64 shrink-0">
        <div className="relative mb-3">
          <Search
            size={14}
            className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-faint"
            aria-hidden
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search metrics"
            aria-label="Search metrics"
            className="w-full rounded-lg border border-line bg-surface ps-8 pe-3 py-1.5 text-[0.8rem] text-ink outline-none focus:border-primary transition"
          />
        </div>
        <div className="flex flex-col gap-0.5">
          {filtered.map((m) => (
            <button
              key={m.name}
              onClick={() => setSelected(m.name)}
              aria-current={selected === m.name ? "page" : undefined}
              className={`w-full text-start flex items-center gap-2 rounded-lg px-2.5 py-2 text-[0.82rem] transition ${
                selected === m.name
                  ? "bg-primary/10 text-primary-dark font-medium"
                  : "text-ink hover:bg-surfaceAlt"
              }`}
            >
              {m.is_draft && (
                <span
                  className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary"
                  aria-label="Has unpublished draft"
                  title="Has unpublished draft"
                />
              )}
              <span
                className={`shrink-0 w-1.5 h-1.5 rounded-full ${STATUS_DOT[m.status] ?? "bg-faint"}`}
                aria-hidden
              />
              <span className="truncate flex-1">{m.label}</span>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-2.5 py-4 text-[0.78rem] text-muted">No metrics match your search.</p>
          )}
        </div>
      </div>

      {/* Editor pane */}
      <div className="flex-1 min-w-0">
        {selectedMetric ? (
          <MetricEditor key={selectedMetric.name} metric={selectedMetric} semantic={semantic} />
        ) : (
          <p className="text-sm text-muted">Select a metric to view or edit its definition.</p>
        )}
      </div>
    </div>
  );
}
