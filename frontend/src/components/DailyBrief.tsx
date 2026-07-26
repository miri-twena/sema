import type { ComponentType } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Package,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Trophy,
  Users,
} from "lucide-react";
import type { BriefInsight, DailyBrief as DailyBriefResponse, PulseMetric } from "../lib/api";
import { formatValue } from "../lib/format";

const STATUS_COLOR = {
  above: "#1B7A5E", // success
  below: "#DC2626", // danger
  normal: "#94A3B8", // muted gray
} as const;

/** "2026-06-30" -> "Jun 30, 2026", parsed as UTC so it never shifts a day in
 * a positive-UTC-offset timezone (same convention format.ts's isoToLabel uses). */
function formatAsOf(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Plain inline polyline -- no charting library, per the sparkline constraint.
 * aria-hidden: the tile's value + status line already say what matters in
 * text; the line itself is decorative reinforcement, not new information. */
function Sparkline({ values, status }: { values: number[]; status: PulseMetric["status"] }) {
  const w = 64;
  const h = 24;
  const pad = 2;
  if (values.length < 2) return <svg width={w} height={h} aria-hidden="true" />;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke={STATUS_COLOR[status]}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PulseTile({ metric }: { metric: PulseMetric }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.75rem] text-muted">{metric.label}</span>
        <Sparkline values={metric.spark} status={metric.status} />
      </div>
      <div className="mt-1 text-xl font-medium text-ink" dir="ltr">
        {formatValue(metric.value, metric.format)}
      </div>
      <div className="mt-0.5 text-[0.68rem]" style={{ color: STATUS_COLOR[metric.status] }}>
        {metric.status_label}
      </div>
    </div>
  );
}

const INSIGHT_ICON: Record<BriefInsight["icon"], { Icon: ComponentType<{ size?: number; className?: string }>; color: string }> = {
  warning: { Icon: AlertTriangle, color: "#CA8A04" },
  customers: { Icon: Users, color: "#5B5F9F" },
  trending_up: { Icon: TrendingUp, color: "#1B7A5E" },
  trending_down: { Icon: TrendingDown, color: "#DC2626" },
  record: { Icon: Trophy, color: "#7C8CFF" },
  product: { Icon: Package, color: "#7C8CFF" },
};

function InsightRow({ insight, onAsk }: { insight: BriefInsight; onAsk: (question: string) => void }) {
  const { Icon, color } = INSIGHT_ICON[insight.icon];
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-surface p-3">
      <Icon size={18} className="shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1" style={{ color }}>
        <div className="text-sm font-semibold text-ink" dir="auto">
          {insight.headline}
        </div>
        <div className="text-[0.78rem] text-muted mt-0.5 leading-snug" dir="auto" style={{ unicodeBidi: "plaintext" }}>
          {insight.detail}
        </div>
        <button
          onClick={() => onAsk(insight.follow_up_question)}
          className="group mt-1.5 inline-flex items-center gap-1.5 text-[0.78rem] font-medium text-primary hover:underline"
        >
          Tell me more
          <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </div>
  );
}

/** The quiet-day state: insights is empty, which is the NORMAL case on most
 * days, not a degraded one -- a single calm line, never a filler card. */
function AllNormalRow() {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5">
      <CheckCircle2 size={16} className="shrink-0" style={{ color: STATUS_COLOR.above }} />
      <span className="text-sm text-ink">All metrics in their normal range today</span>
    </div>
  );
}

/**
 * Daily Brief: two layers, separating freshness from insight.
 *
 * Layer 1 (pulse) ALWAYS renders -- yesterday's revenue/orders/conversion
 * with a 14-day spark and a same-weekday-vs-typical status. This is what
 * makes the section change every day, honestly, with no pretense of insight
 * on a day where nothing happened.
 *
 * Layer 2 (attention cards) is event-driven: up to 3 ranked findings from 6
 * independent SQL-backed generators, each gated by its own threshold. A
 * quiet day (the common case) shows one calm line instead of empty space or
 * manufactured filler.
 *
 * The whole section hides itself when there's no pulse data at all (a fresh
 * client, or the endpoint failing) -- same "no data, no card" convention as
 * the rest of the home dashboard.
 */
export function DailyBrief({
  brief,
  onAsk,
}: {
  brief: DailyBriefResponse | null; // null while loading
  onAsk: (question: string) => void;
}) {
  if (brief === null) {
    return (
      <section className="mt-8" aria-busy="true">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted mb-2">
          Daily brief
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 rounded-xl bg-surfaceAlt animate-pulse" />
          ))}
        </div>
      </section>
    );
  }

  if (brief.pulse.length === 0) return null;

  return (
    <section className="mt-8">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <Sparkles size={13} className="text-primary" />
          <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Daily brief</span>
        </div>
        {brief.as_of && (
          <span className="text-[0.7rem] text-muted shrink-0" dir="ltr">
            As of {formatAsOf(brief.as_of)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {brief.pulse.map((m) => (
          <PulseTile key={m.metric} metric={m} />
        ))}
      </div>

      <div className="mt-3 flex flex-col gap-2">
        {brief.insights.length > 0 ? (
          brief.insights.map((i) => <InsightRow key={i.id} insight={i} onAsk={onAsk} />)
        ) : (
          <AllNormalRow />
        )}
      </div>
    </section>
  );
}
