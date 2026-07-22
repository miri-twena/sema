import { ArrowRight, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import type { Brief, BriefInsight } from "../lib/api";
import { formatValue } from "../lib/format";
import { Card } from "./ui/Card";

/** Sentiment -> tint. Driven by what the metric MEANS (a fall in AOV is bad
 * even though "down" is neutral on its own), never by the direction arrow. */
const TONE = {
  positive: { bg: "#EAFBF4", fg: "#1B7A5E" },
  negative: { bg: "#FEE2E2", fg: "#DC2626" },
} as const;

function InsightCard({
  insight,
  onAsk,
}: {
  insight: BriefInsight;
  onAsk: (question: string) => void;
}) {
  const tone = TONE[insight.sentiment];
  const Trend = insight.direction === "up" ? TrendingUp : TrendingDown;

  return (
    <Card className="flex flex-col p-4 hover:border-primary transition-colors">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
          {insight.metric_label}
        </span>
        <span
          className="inline-flex items-center gap-1 rounded-lg px-1.5 py-0.5 text-[0.7rem] font-semibold"
          style={{ backgroundColor: tone.bg, color: tone.fg }}
        >
          <Trend size={12} />
          {insight.change_pct === null ? "—" : `${Math.abs(insight.change_pct)}%`}
        </span>
      </div>

      {/* dir="auto": the phrasing is English today but the same slot carries
          translated copy, and these sit inside a possibly-RTL page. */}
      <div className="mt-2 text-sm font-semibold text-ink" dir="auto">
        {insight.headline}
      </div>
      <p className="mt-1 text-[0.8rem] leading-relaxed text-muted" dir="auto">
        {insight.detail}
      </p>

      <div className="mt-2.5 flex items-baseline gap-2 text-[0.78rem]">
        <span className="font-semibold text-ink">
          {formatValue(insight.current_value, insight.value_format)}
        </span>
        <span className="text-muted">
          from {formatValue(insight.previous_value, insight.value_format)}
        </span>
      </div>

      <button
        onClick={() => onAsk(insight.follow_up_question)}
        className="group mt-3 inline-flex items-center gap-1.5 self-start text-[0.78rem] font-medium text-primary hover:underline"
      >
        Tell me more
        <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
      </button>
    </Card>
  );
}

/**
 * Daily Brief: what moved in the selected period, phrased, before the user
 * asks anything. Deterministic (no model call on page load) and scoped to the
 * period already chosen in the Business Overview's picker -- this section
 * never renders a picker of its own.
 *
 * Renders nothing at all when there is no story to tell, so a quiet period
 * costs the home screen no vertical space. The one exception is a missing
 * baseline, which gets a quiet explanatory line instead of silence.
 */
export function DailyBrief({
  brief,
  onAsk,
}: {
  brief: Brief | null; // null while loading
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
            <div key={i} className="h-36 rounded-xl2 bg-surfaceAlt animate-pulse" />
          ))}
        </div>
      </section>
    );
  }

  // A client with no monthly revenue reports at all (or a failed fetch) has no
  // brief to give -- render nothing, the same as a quiet period. Only a client
  // that HAS data but lacks a baseline gets the explanatory line below, since
  // "not enough history" would be misleading for the other cases.
  if (brief.unavailable_reason && brief.unavailable_reason !== "insufficient_history") {
    return null;
  }

  // No baseline window: say so quietly rather than showing a comparison the
  // data can't support. Never blocks the rest of the home screen.
  if (!brief.comparison_available) {
    return (
      <section className="mt-8">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted mb-2">
          Daily brief
        </div>
        <p className="text-sm text-muted">
          Not enough history yet to compare this period with the one before it.
        </p>
      </section>
    );
  }

  if (brief.insights.length === 0) return null;

  return (
    <section className="mt-8">
      <div className="flex items-center gap-1.5 mb-2">
        <Sparkles size={13} className="text-primary" />
        <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
          Daily brief
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {brief.insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} onAsk={onAsk} />
        ))}
      </div>
    </section>
  );
}
