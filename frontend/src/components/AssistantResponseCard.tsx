import { Suspense, lazy } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Code2 } from "lucide-react";
import type { ChatResponse } from "../lib/api";
import { Card } from "./ui/Card";
import { KpiCards } from "./KpiCards";
import { DataTable } from "./DataTable";
import { RecommendedActions } from "./RecommendedActions";
import type { DrillContext } from "./DrillChat";

// Recharts is heavy (~half the bundle); load it only when an answer has a chart.
const ChartRenderer = lazy(() => import("./ChartRenderer").then((m) => ({ default: m.ChartRenderer })));

export function AssistantResponseCard({
  response,
  dir,
  onDrill,
}: {
  response: ChatResponse;
  dir: "rtl" | "ltr";
  onDrill?: (ctx: DrillContext) => void;
}) {
  if (response.status === "error") {
    return (
      <Card className="p-4 border-critical-fg/30">
        <div className="flex items-center gap-2 text-critical-fg text-sm">
          <AlertTriangle size={16} className="shrink-0" /> {response.error || "Something went wrong."}
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
        </div>

        <div className="sema-prose text-ink text-[0.94rem]">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.answer}</ReactMarkdown>
        </div>

        {response.kpis.length > 0 && (
          <div className="mt-3">
            <KpiCards kpis={response.kpis} onDrill={onDrill} />
          </div>
        )}

        {response.chart && (
          <Suspense fallback={<div className="mt-3 h-[280px] rounded-xl bg-surfaceAlt animate-pulse" />}>
            <ChartRenderer chart={response.chart} onDrill={onDrill} />
          </Suspense>
        )}

        {response.table && <DataTable table={response.table} />}
        {response.actions.length > 0 && <RecommendedActions actions={response.actions} onDrill={onDrill} />}

        {response.sql_used && (
          <details className="mt-4">
            <summary className="cursor-pointer list-none flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition w-fit">
              <Code2 size={14} /> View SQL
            </summary>
            <pre
              dir="ltr"
              className="mt-2 overflow-auto sema-scroll rounded-lg border border-line bg-surfaceAlt p-3 text-[0.72rem] leading-relaxed text-ink"
            >
              {response.sql_used}
            </pre>
          </details>
        )}
      </div>
    </Card>
  );
}
