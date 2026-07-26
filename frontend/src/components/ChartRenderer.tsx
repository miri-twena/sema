import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceDot,
} from "recharts";
import { useRef } from "react";
import { MessageSquareText, Image as ImageIcon, Table2 } from "lucide-react";
import type { Chart } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { followUpsLabel, formatX, makeAxisTickFormatter } from "../lib/format";
import {
  highlightPoint,
  periodSubtitle,
  pivot,
  prefersReducedMotion,
  tooltipContent,
  xAxisTickStyle,
  type TooltipShape,
} from "../lib/chart";
import { CHART_PALETTE as PALETTE } from "../lib/tokens";
import { CopyableBlock } from "./CopyButton";
import { copyPng, copyRich, svgToPngBlob, toHTMLTable, toTSV } from "../lib/clipboard";
import { ThreadBadge } from "./ThreadBadge";

type Row = Record<string, unknown>;

/** Recharts calls this with its own (loosely-typed) tooltip props; the actual
 * label/value/series shaping lives in lib/chart.ts#tooltipContent so it's
 * testable without mounting a chart. Forced dir="ltr": a tooltip over an
 * otherwise-LTR chart must not mirror even inside a Hebrew answer. */
function ChartTooltip({
  active,
  label,
  payload,
  fmt,
}: {
  active?: boolean;
  label?: unknown;
  payload?: Array<{ name?: string | number; dataKey?: string | number; value?: unknown; color?: string }>;
  fmt: (v: unknown) => string;
}) {
  if (!active || !payload?.length) return null;
  const { label: fullLabel, entries }: TooltipShape = tooltipContent(label, payload, fmt);
  return (
    <div dir="ltr" className="rounded-lg border border-line bg-surface px-3 py-2 shadow-pop text-xs max-w-[220px]">
      <div className="font-medium text-ink mb-1">{fullLabel}</div>
      <div className="flex flex-col gap-0.5">
        {entries.map((e, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: e.color }} />
            {entries.length > 1 && <span className="text-muted truncate">{e.name}</span>}
            <span className="font-medium text-ink ms-auto">{e.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Compact legend: Recharts' default icon/font read a bit heavy for a card
// this size.
const legendStyle = { fontSize: 12, paddingTop: 6 };

export function ChartRenderer({
  chart,
  dir,
  anchor,
  threadCount,
  onDrill,
}: {
  chart: Chart;
  dir?: "rtl" | "ltr";
  anchor?: { conversationId: string; turnIndex: number };
  threadCount?: (title: string) => number | undefined;
  onDrill?: (ctx: DrillContext) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const { kind, rows, x, y, color, names, values, y_format, title, highlight_x } = chart;
  const fmt = makeAxisTickFormatter(y_format);
  if (!rows?.length) return null;

  const reducedMotion = prefersReducedMotion();
  const animation = { isAnimationActive: !reducedMotion, animationDuration: 600 };
  // Recharts 3.9's Bar entrance-animation path renders zero bars under React
  // StrictMode's dev-mode double-render (verified: identical markup with only
  // isAnimationActive flipped goes from 0 rendered bars to all of them) --
  // Line/Area/Pie animate fine, so this is scoped to Bar only. Correctness
  // (bars must actually render) wins over the entrance animation here.
  const barAnimation = { isAnimationActive: false };

  const axis = { stroke: "#94A3B8", fontSize: 12, axisLine: false, tickLine: false };
  const grid = <CartesianGrid stroke="#EEF2F7" vertical={false} />;
  const tooltip = <Tooltip content={<ChartTooltip fmt={fmt} />} cursor={{ fill: "#F1F5F9" }} />;

  let body: React.ReactNode = null;
  // Fixed px (not %) since ResponsiveContainer needs a concrete height; the
  // xl bump gives charts more vertical detail once they have the width to
  // back it up.
  let heightClass = "h-[260px] xl:h-[320px]";
  // A subtitle only ever comes from the data itself (the chart's own first/
  // last x values) -- never a separate field to keep in sync.
  const subtitle = periodSubtitle(rows as Row[], x);

  if (kind === "donut") {
    heightClass = "h-[300px] xl:h-[360px]";
    body = (
      <PieChart>
        <Pie
          data={rows as Row[]}
          dataKey={values || "value"}
          nameKey={names || "name"}
          innerRadius={60}
          outerRadius={95}
          paddingAngle={2}
          {...animation}
        >
          {rows.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} stroke="#fff" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip content={<ChartTooltip fmt={fmt} />} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
      </PieChart>
    );
  } else if (color && x && y) {
    // multi-series (grouped bar / multi-line) -- several series overlapping
    // makes an area fill unreadable, so these stay plain bars/lines even
    // though a single-series line below gets a soft area fill.
    const { data, series } = pivot(rows as Row[], x, color, y);
    const tick = xAxisTickStyle(data.length);
    if (kind === "line") {
      body = (
        <LineChart data={data} margin={{ bottom: tick.height > 24 ? tick.height - 24 : 0 }}>
          {grid}
          <XAxis
            dataKey={x}
            tickFormatter={formatX}
            angle={tick.angle}
            textAnchor={tick.textAnchor}
            height={tick.height}
            {...axis}
          />
          <YAxis tickFormatter={fmt} {...axis} />
          {tooltip}
          <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
          {series.map((s, i) => (
            <Line
              key={s}
              type="monotone"
              dataKey={s}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 5 }}
              {...animation}
            />
          ))}
        </LineChart>
      );
    } else {
      body = (
        <BarChart data={data} barCategoryGap="28%" barGap={4} margin={{ bottom: tick.height > 24 ? tick.height - 24 : 0 }}>
          {grid}
          <XAxis
            dataKey={x}
            tickFormatter={formatX}
            angle={tick.angle}
            textAnchor={tick.textAnchor}
            height={tick.height}
            {...axis}
          />
          <YAxis tickFormatter={fmt} {...axis} />
          {tooltip}
          <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
          {series.map((s, i) => (
            <Bar
              key={s}
              dataKey={s}
              fill={PALETTE[i % PALETTE.length]}
              radius={[7, 7, 0, 0]}
              maxBarSize={40}
              activeBar={{ fillOpacity: 0.85 }}
              {...barAnimation}
            />
          ))}
        </BarChart>
      );
    }
  } else if (kind === "bar" && x && y) {
    const tick = xAxisTickStyle(rows.length);
    body = (
      <BarChart data={rows as Row[]} barCategoryGap="28%" margin={{ bottom: tick.height > 24 ? tick.height - 24 : 0 }}>
        {grid}
        <XAxis
          dataKey={x}
          tickFormatter={formatX}
          angle={tick.angle}
          textAnchor={tick.textAnchor}
          height={tick.height}
          {...axis}
        />
        <YAxis tickFormatter={fmt} {...axis} />
        {tooltip}
        <Bar dataKey={y} fill={PALETTE[0]} radius={[7, 7, 0, 0]} maxBarSize={44} activeBar={{ fillOpacity: 0.85 }} {...barAnimation} />
      </BarChart>
    );
  } else if (x && y) {
    // Single-series line: rendered as a line with a soft, flat (no gradient)
    // area fill beneath it -- the "line, area" visual system unified onto the
    // one `line` chart kind the backend contract actually has.
    const tick = xAxisTickStyle(rows.length);
    const hl = highlightPoint(rows as Row[], x, y, highlight_x);
    body = (
      <AreaChart data={rows as Row[]} margin={{ bottom: tick.height > 24 ? tick.height - 24 : 0 }}>
        {grid}
        <XAxis
          dataKey={x}
          tickFormatter={formatX}
          angle={tick.angle}
          textAnchor={tick.textAnchor}
          height={tick.height}
          {...axis}
        />
        <YAxis tickFormatter={fmt} {...axis} />
        {tooltip}
        <Area
          type="monotone"
          dataKey={y}
          stroke={PALETTE[0]}
          strokeWidth={2.5}
          fill={PALETTE[0]}
          fillOpacity={0.08}
          dot={{ r: 3 }}
          activeDot={{ r: 5 }}
          {...animation}
        />
        {/* Spotlights a real backend-chosen point (e.g. the month it's
            explaining) -- never an invented annotation; absent entirely when
            highlight_x isn't in the data. */}
        {hl && <ReferenceDot x={hl.x as string | number} y={hl.y} r={5} fill="#FFB4A2" stroke="#fff" strokeWidth={2} />}
      </AreaChart>
    );
  }

  if (!body) return null;

  const copyImage = async () => {
    // Must target the Recharts surface specifically: a bare querySelector("svg")
    // picks up the "Ask about this" button's Lucide icon, which sits earlier in
    // DOM order and would rasterize a 14px icon instead of the chart.
    const svg = wrapRef.current?.querySelector(".recharts-surface");
    if (!svg) throw new Error("Chart is not ready yet");
    // svgToPngBlob is passed UNAWAITED so the rasterize stays inside the click
    // gesture -- see copyPng.
    await copyPng(svgToPngBlob(svg as SVGSVGElement));
  };

  const copyData = async () => {
    const cols = chart.columns?.length ? chart.columns : Object.keys((rows[0] as Row) ?? {});
    await copyRich(toTSV(cols, rows as Row[]), toHTMLTable(cols, rows as Row[]));
  };

  const chartTitle = title || "Chart";
  const badge = threadCount?.(chartTitle);
  const rtl = dir === "rtl";

  const drill = () =>
    onDrill?.({
      kind: "chart",
      title: chartTitle,
      detail:
        `a ${kind} chart of ${y ?? values ?? "value"} by ${x ?? names ?? "category"}; ` +
        `data (JSON rows): ${JSON.stringify(rows).slice(0, 1500)}`,
      dir,
      ...anchor,
    });

  return (
    <CopyableBlock
      // dir="ltr" on the card itself (not the ambient `dir`): the chart's
      // axes/plot must stay LTR regardless of question language (see
      // xAxis/tickFormatter above), matching SqlBlock's existing rule for
      // another numeric/technical widget. Title/subtitle text below still
      // reads in the actual `dir`.
      dir="ltr"
      className="mt-3 rounded-xl border border-line bg-surface p-4"
      title="Copy chart as image"
      actions={[
        { label: "Copy image", icon: <ImageIcon size={13} />, run: copyImage },
        { label: "Copy underlying data", icon: <Table2 size={13} />, run: copyData },
      ]}
    >
      <div ref={wrapRef}>
        <div className="flex items-start justify-between mb-2 gap-2">
          <div className="min-w-0" dir={dir} style={{ textAlign: rtl ? "right" : "left" }}>
            {title && <div className="text-sm font-semibold text-ink truncate">{title}</div>}
            {subtitle && <div className="text-xs text-muted mt-0.5">{subtitle}</div>}
          </div>
          {onDrill && (
            // me-9 keeps this clear of the floating copy control.
            <div className="shrink-0 ms-auto me-9 flex items-center gap-2">
              {typeof badge === "number" && <ThreadBadge count={badge} />}
              <button
                onClick={drill}
                className="flex items-center gap-1 text-xs text-muted hover:text-primary transition"
                aria-label={`Ask about this chart${followUpsLabel(badge)}`}
                title="Ask about this chart"
              >
                <MessageSquareText size={14} /> Ask about this
              </button>
            </div>
          )}
        </div>
        <div className={heightClass}>
          <ResponsiveContainer width="100%" height="100%">
            {body as React.ReactElement}
          </ResponsiveContainer>
        </div>
      </div>
    </CopyableBlock>
  );
}
