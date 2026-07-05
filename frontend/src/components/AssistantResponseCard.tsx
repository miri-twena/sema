import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle } from "lucide-react";
import type { ChatResponse } from "../lib/api";
import { Card } from "./ui/Card";
import { KpiCards } from "./KpiCards";
import { ChartRenderer } from "./ChartRenderer";
import { DataTable } from "./DataTable";
import { RecommendedActions } from "./RecommendedActions";

export function AssistantResponseCard({ response, dir }: { response: ChatResponse; dir: "rtl" | "ltr" }) {
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
            <KpiCards kpis={response.kpis} />
          </div>
        )}

        {response.chart && <ChartRenderer chart={response.chart} />}
        {response.table && <DataTable table={response.table} />}
        {response.actions.length > 0 && <RecommendedActions actions={response.actions} />}
      </div>
    </Card>
  );
}
