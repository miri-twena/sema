import type { Kpi } from "../lib/api";

// (bg, label color) tints cycled across the cards -- matches theme.py KPI_TINTS.
const TINTS: [string, string][] = [
  ["#FBEEEA", "#9A6A58"],
  ["#EAF5FF", "#5A7894"],
  ["#EEF0FF", "#5B5F9F"],
  ["#EAFBF4", "#1B7A5E"],
];

function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (a >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatValue(value: number | string, fmt: string): string {
  if (typeof value !== "number") return String(value);
  switch (fmt) {
    case "currency":
      return `$${compact(value)}`;
    case "percent":
      return `${value.toFixed(1)}%`;
    case "number":
      return compact(value);
    case "ratio":
      return `${value.toFixed(2)}x`;
    default:
      return String(value);
  }
}

export function KpiCards({ kpis }: { kpis: Kpi[] }) {
  if (!kpis?.length) return null;
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(kpis.length, 4)}, minmax(0, 1fr))` }}>
      {kpis.map((kpi, i) => {
        const [bg, labelColor] = TINTS[i % TINTS.length];
        const hasDelta = kpi.delta !== undefined && kpi.delta !== null;
        const up = (kpi.delta ?? 0) >= 0;
        return (
          <div key={i} className="rounded-xl p-4 flex flex-col justify-between" style={{ background: bg }}>
            <div className="text-[0.68rem] font-semibold uppercase tracking-wide leading-tight min-h-[2.2em]" style={{ color: labelColor }}>
              {kpi.label}
            </div>
            <div className="mt-1 text-2xl font-semibold text-ink whitespace-nowrap">
              {formatValue(kpi.value, kpi.format)}
            </div>
            {hasDelta && (
              <div className={`mt-1 text-sm font-medium ${up ? "text-emerald-600" : "text-orange-700"}`}>
                {up ? "▲" : "▼"} {Math.abs(kpi.delta as number).toFixed(1)}% {kpi.delta_label ?? ""}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
