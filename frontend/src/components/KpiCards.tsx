import type { Kpi } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { formatValue } from "../lib/format";
import { KPI_TINTS } from "../lib/tokens";

export function KpiCards({
  kpis,
  dir,
  onDrill,
}: {
  kpis: Kpi[];
  dir?: "rtl" | "ltr";
  onDrill?: (ctx: DrillContext) => void;
}) {
  if (!kpis?.length) return null;
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(kpis.length, 4)}, minmax(0, 1fr))` }}>
      {kpis.map((kpi, i) => {
        const [bg, labelColor] = KPI_TINTS[i % KPI_TINTS.length];
        const hasDelta = kpi.delta !== undefined && kpi.delta !== null;
        const up = (kpi.delta ?? 0) >= 0;
        const valueText = formatValue(kpi.value, kpi.format);
        const deltaText = hasDelta
          ? `, ${up ? "up" : "down"} ${Math.abs(kpi.delta as number).toFixed(1)}% ${kpi.delta_label ?? ""}`.trimEnd()
          : "";

        const drill = onDrill
          ? () =>
              onDrill({
                kind: "kpi",
                title: kpi.label,
                detail: `current value ${valueText}${deltaText}`,
                dir,
              })
          : undefined;

        return (
          <div
            key={i}
            onClick={drill}
            onKeyDown={
              drill
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      drill();
                    }
                  }
                : undefined
            }
            role={drill ? "button" : undefined}
            tabIndex={drill ? 0 : undefined}
            aria-label={drill ? `Ask about ${kpi.label}` : undefined}
            className={`rounded-xl p-4 flex flex-col justify-between transition ${
              drill
                ? "cursor-pointer hover:ring-2 hover:ring-primary/40 hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                : ""
            }`}
            style={{ background: bg }}
          >
            <div className="text-[0.68rem] font-semibold uppercase tracking-wide leading-tight min-h-[2.2em]" style={{ color: labelColor }}>
              {kpi.label}
            </div>
            <div className="mt-1 text-2xl font-semibold text-ink whitespace-nowrap">{valueText}</div>
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
