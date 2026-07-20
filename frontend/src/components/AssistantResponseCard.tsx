import { Suspense, lazy, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Code2 } from "lucide-react";
import type { ChatResponse } from "../lib/api";
import { Card } from "./ui/Card";
import { KpiCards } from "./KpiCards";
import { DataTable } from "./DataTable";
import { RecommendedActions } from "./RecommendedActions";
import { MessageActions } from "./MessageActions";
import { SqlBlock } from "./SqlBlock";
import type { DrillContext } from "./DrillChat";
import { ConfidenceBadge, EvidencePanel, NoticeBadges, PeriodBanner } from "./EvidencePanel";
import { CopyableBlock } from "./CopyButton";
import { CodeBlock, InlineCode } from "./CodeBlock";
import { ModeCard } from "./ModeCard";
import { copyRich } from "../lib/clipboard";

// Recharts is heavy (~half the bundle); load it only when an answer has a chart.
const ChartRenderer = lazy(() => import("./ChartRenderer").then((m) => ({ default: m.ChartRenderer })));

export function AssistantResponseCard({
  response,
  dir,
  onDrill,
  onRetry,
  onAsk,
}: {
  response: ChatResponse;
  dir: "rtl" | "ltr";
  onDrill?: (ctx: DrillContext) => void;
  onRetry?: () => void;
  /** Sends a follow-up in the SAME conversation -- drives clarification
   * choices and cannot-answer alternatives. */
  onAsk?: (q: string) => void;
}) {
  const proseRef = useRef<HTMLDivElement>(null);
  if (response.status === "error") {
    return (
      <Card className="p-4 border-critical-fg/30">
        <div className="flex items-center gap-2 text-critical-fg text-sm">
          <AlertTriangle size={16} className="shrink-0" /> {response.error || "Something went wrong."}
        </div>
      </Card>
    );
  }

  // Non-answer modes render as their own calm state: no confidence badge, no
  // period banner, and none of the analytical sections below. The server has
  // already stripped KPIs/charts/evidence for these, so this is belt-and-braces
  // -- the mode alone decides, never the prose.
  const mode = response.mode ?? "answer";
  if (mode !== "answer") {
    return (
      <Card className="p-4">
        <div dir={dir} style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary to-mint" />
            <span className="text-xs font-semibold text-primary-dark">SEMA</span>
          </div>
          <NoticeBadges notices={response.notices} dir={dir} />
          <ModeCard response={response} dir={dir} onAsk={onAsk} />
          <MessageActions text={response.answer} onRetry={onRetry} />
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <div dir={dir} style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
        <div className="flex items-center gap-2 mb-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary to-mint" />
          <span className="text-xs font-semibold text-primary-dark">SEMA</span>
          <ConfidenceBadge confidence={response.confidence} />
        </div>

        <NoticeBadges notices={response.notices} dir={dir} />
        <PeriodBanner dateRange={response.evidence?.date_range} />

        {/* Plain text gets the raw markdown source; rich targets get the
         * rendered HTML straight off the DOM node. */}
        <CopyableBlock
          title="Copy this text"
          actions={[
            {
              label: "Copy text",
              run: () => copyRich(response.answer, proseRef.current?.innerHTML ?? response.answer),
            },
          ]}
        >
          <div ref={proseRef} className="sema-prose text-ink text-[0.94rem]">
            {/* Code in an answer gets its own LTR-isolated block + copy button;
             * `pre` covers fenced blocks, `code` the inline spans. */}
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: CodeBlock, code: InlineCode }}>
              {response.answer}
            </ReactMarkdown>
          </div>
        </CopyableBlock>

        {response.kpis.length > 0 && (
          <div className="mt-3">
            <KpiCards kpis={response.kpis} dir={dir} onDrill={onDrill} />
          </div>
        )}

        {response.chart && (
          <Suspense fallback={<div className="mt-3 h-[280px] rounded-xl bg-surfaceAlt animate-pulse" />}>
            <ChartRenderer chart={response.chart} dir={dir} onDrill={onDrill} />
          </Suspense>
        )}

        {response.table && <DataTable table={response.table} />}
        {response.actions.length > 0 && <RecommendedActions actions={response.actions} dir={dir} onDrill={onDrill} />}

        {response.sql_used && (
          <details className="mt-4">
            <summary className="cursor-pointer list-none flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition w-fit">
              <Code2 size={14} /> View SQL
            </summary>
            <SqlBlock sql={response.sql_used} />
          </details>
        )}

        <EvidencePanel evidence={response.evidence} dir={dir} />

        <MessageActions text={response.answer} onRetry={onRetry} />
      </div>
    </Card>
  );
}
