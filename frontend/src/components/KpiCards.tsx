import type { Kpi } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { formatValue, followUpsLabel } from "../lib/format";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "../lib/tokens";
import { CopyButton } from "./CopyButton";
import { copyText } from "../lib/clipboard";
import { ThreadBadge } from "./ThreadBadge";

// Static class lookups so Tailwind's content scanner sees every literal
// class name in this file, even though the count picked at runtime is
// dynamic -- a template-built class string (`grid-cols-${n}`) would never be
// generated. Base stays capped at 4 (today's behavior, incl. mobile);
// 2xl gets the extra room to go up to 6.
const GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};
const GRID_COLS_2XL: Record<number, string> = {
  1: "2xl:grid-cols-1",
  2: "2xl:grid-cols-2",
  3: "2xl:grid-cols-3",
  4: "2xl:grid-cols-4",
  5: "2xl:grid-cols-5",
  6: "2xl:grid-cols-6",
};

export function KpiCards({
  kpis,
  dir,
  anchor,
  threadCount,
  onDrill,
}: {
  kpis: Kpi[];
  dir?: "rtl" | "ltr";
  /** Which conversation + turn these KPIs belong to, for persisting a drilled
   * widget's thread. Undefined for anchor-less KPIs (the home dashboard),
   * which stay ephemeral -- see the TODO where HomeDashboard renders this. */
  anchor?: { conversationId: string; turnIndex: number };
  threadCount?: (title: string) => number | undefined;
  onDrill?: (ctx: DrillContext) => void;
}) {
  if (!kpis?.length) return null;
  const cols = GRID_COLS[Math.min(kpis.length, 4)];
  const cols2xl = GRID_COLS_2XL[Math.min(kpis.length, 6)];
  return (
    <div className={`grid gap-3 ${cols} ${cols2xl}`}>
      {kpis.map((kpi, i) => {
        // Positional cycling through the chart's own palette -- true "same
        // entity, same hue across the chart/table below" would need a
        // category/entity id on Kpi, which the contract doesn't have and
        // this pass adds no new API fields for (see PROMPT_QUEUE.md evidence).
        const ruleColor = CHART_PALETTE[i % CHART_PALETTE.length];
        const labelColor = CHART_PALETTE_TEXT[i % CHART_PALETTE_TEXT.length];
        const hasDelta = kpi.delta !== undefined && kpi.delta !== null;
        const up = (kpi.delta ?? 0) >= 0;
        const valueText = formatValue(kpi.value, kpi.format);
        const deltaText = hasDelta
          ? `, ${up ? "up" : "down"} ${Math.abs(kpi.delta as number).toFixed(1)}% ${kpi.delta_label ?? ""}`.trimEnd()
          : "";
        const badge = threadCount?.(kpi.label);

        const drill = onDrill
          ? () =>
              onDrill({
                kind: "kpi",
                title: kpi.label,
                detail: `current value ${valueText}${deltaText}`,
                dir,
                hue: ruleColor,
                ...anchor,
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
            aria-label={drill ? `Ask about ${kpi.label}${followUpsLabel(badge)}` : undefined}
            className={`sema-copy-host rounded-xl border border-line bg-surface overflow-hidden flex flex-col transition ${
              drill
                ? "cursor-pointer hover:ring-2 hover:ring-primary/40 hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                : ""
            }`}
          >
            <span className="block h-[3px] w-full shrink-0" style={{ background: ruleColor }} aria-hidden />
            {/* CopyButton stops click/keydown propagation so copying a card
             * never opens its drill-down. */}
            <div className="sema-copy-affordance absolute top-1 end-1 z-20">
              <CopyButton
                title={`Copy "${kpi.label}"`}
                actions={[{ label: "Copy KPI", run: () => copyText(`${kpi.label}: ${valueText}`) }]}
              />
            </div>
            <div className="flex-1 flex flex-col gap-1 px-[15px] pt-3 pb-3.5">
              <div
                className="text-[11px] font-semibold uppercase tracking-[.03em] leading-[1.25] min-h-[2.1em] pe-8"
                style={{ color: labelColor }}
              >
                {kpi.label}
              </div>
              <div className="text-[22px] font-semibold tracking-[-.02em] tabular-nums text-ink whitespace-nowrap overflow-hidden text-ellipsis">
                {valueText}
              </div>
              {(hasDelta || typeof badge === "number") && (
                <div className="mt-0.5 flex items-center justify-between gap-2">
                  {hasDelta ? (
                    <div className={`text-sm font-medium ${up ? "text-emerald-600" : "text-orange-700"}`}>
                      {up ? "▲" : "▼"} {Math.abs(kpi.delta as number).toFixed(1)}% {kpi.delta_label ?? ""}
                    </div>
                  ) : (
                    <span />
                  )}
                  {typeof badge === "number" && <ThreadBadge count={badge} />}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
