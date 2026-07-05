import {
  ResponsiveContainer,
  LineChart,
  Line,
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
} from "recharts";
import { MessageSquareText } from "lucide-react";
import type { Chart } from "../lib/api";
import type { DrillContext } from "./DrillChat";
import { formatX, makeAxisTickFormatter } from "../lib/format";
import { CHART_PALETTE as PALETTE } from "../lib/tokens";

type Row = Record<string, unknown>;

/** Pivot long rows ({x, color, y}) into wide rows ({x, series1, series2, ...}). */
function pivot(rows: Row[], x: string, color: string, y: string) {
  const xValues = [...new Set(rows.map((r) => r[x] as string))];
  const series = [...new Set(rows.map((r) => String(r[color])))];
  const data = xValues.map((xv) => {
    const obj: Row = { [x]: xv };
    rows.filter((r) => r[x] === xv).forEach((r) => {
      obj[String(r[color])] = r[y];
    });
    return obj;
  });
  return { data, series };
}

export function ChartRenderer({ chart, onDrill }: { chart: Chart; onDrill?: (ctx: DrillContext) => void }) {
  const { kind, rows, x, y, color, names, values, y_format, title } = chart;
  if (!rows?.length) return null;
  const fmt = makeAxisTickFormatter(y_format);

  const axis = { stroke: "#94A3B8", fontSize: 12 };
  const grid = <CartesianGrid strokeDasharray="3 3" stroke="#EEF2F7" vertical={false} />;

  let body: React.ReactNode = null;

  if (kind === "donut") {
    body = (
      <PieChart>
        <Pie data={rows as Row[]} dataKey={values || "value"} nameKey={names || "name"} innerRadius={60} outerRadius={95} paddingAngle={2}>
          {rows.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} stroke="#fff" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    );
  } else if (color && x && y) {
    // multi-series (grouped bar / multi-line)
    const { data, series } = pivot(rows, x, color, y);
    if (kind === "line") {
      body = (
        <LineChart data={data}>
          {grid}
          <XAxis dataKey={x} tickFormatter={formatX} {...axis} />
          <YAxis tickFormatter={fmt} {...axis} />
          <Tooltip formatter={fmt as never} />
          <Legend />
          {series.map((s, i) => (
            <Line key={s} type="monotone" dataKey={s} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2.5} dot={false} />
          ))}
        </LineChart>
      );
    } else {
      body = (
        <BarChart data={data}>
          {grid}
          <XAxis dataKey={x} tickFormatter={formatX} {...axis} />
          <YAxis tickFormatter={fmt} {...axis} />
          <Tooltip formatter={fmt as never} />
          <Legend />
          {series.map((s, i) => (
            <Bar key={s} dataKey={s} fill={PALETTE[i % PALETTE.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      );
    }
  } else if (kind === "bar" && x && y) {
    body = (
      <BarChart data={rows as Row[]}>
        {grid}
        <XAxis dataKey={x} tickFormatter={formatX} {...axis} />
        <YAxis tickFormatter={fmt} {...axis} />
        <Tooltip formatter={fmt as never} />
        <Bar dataKey={y} fill={PALETTE[0]} radius={[4, 4, 0, 0]} />
      </BarChart>
    );
  } else if (x && y) {
    body = (
      <LineChart data={rows as Row[]}>
        {grid}
        <XAxis dataKey={x} tickFormatter={formatX} {...axis} />
        <YAxis tickFormatter={fmt} {...axis} />
        <Tooltip formatter={fmt as never} />
        <Line type="monotone" dataKey={y} stroke={PALETTE[0]} strokeWidth={2.5} dot={{ r: 3 }} fill="#7C8CFF" />
      </LineChart>
    );
  }

  if (!body) return null;

  const drill = () =>
    onDrill?.({
      title: title || "Chart",
      contextBlock:
        `The user is asking about the chart "${title || "chart"}" ` +
        `(a ${kind} chart of ${y ?? values ?? "value"} by ${x ?? names ?? "category"}). ` +
        `Underlying data (JSON rows): ${JSON.stringify(rows).slice(0, 1500)}. ` +
        `Answer only in the context of this chart and its metric.`,
    });

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-1 gap-2">
        {title && <div className="text-sm font-semibold text-ink">{title}</div>}
        {onDrill && (
          <button
            onClick={drill}
            className="shrink-0 flex items-center gap-1 text-xs text-muted hover:text-primary transition"
            title="Ask about this chart"
          >
            <MessageSquareText size={14} /> Ask about this
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        {body as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}
