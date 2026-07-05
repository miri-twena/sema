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
import type { Chart } from "../lib/api";

const PALETTE = ["#7C8CFF", "#7EE6C3", "#9ED8FF", "#FFB4A2", "#F2C94C", "#C9A0FF"];

type Row = Record<string, unknown>;

function makeTickFormatter(yFormat?: string | null) {
  return (v: unknown): string => {
    if (typeof v !== "number") return String(v ?? "");
    if (yFormat === "currency") {
      const a = Math.abs(v);
      if (a >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
      if (a >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
      return `$${v}`;
    }
    if (yFormat === "percent") return `${v}%`;
    return v.toLocaleString();
  };
}

/** Format an x tick: ISO dates -> "Jul 25"; otherwise pass through. */
function formatX(v: unknown): string {
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    const d = new Date(v);
    if (!isNaN(d.getTime())) return d.toLocaleDateString("en", { month: "short", year: "2-digit" });
  }
  return String(v ?? "");
}

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

export function ChartRenderer({ chart }: { chart: Chart }) {
  const { kind, rows, x, y, color, names, values, y_format, title } = chart;
  if (!rows?.length) return null;
  const fmt = makeTickFormatter(y_format);

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

  return (
    <div className="mt-3">
      {title && <div className="text-sm font-semibold text-ink mb-1">{title}</div>}
      <ResponsiveContainer width="100%" height={280}>
        {body as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}
