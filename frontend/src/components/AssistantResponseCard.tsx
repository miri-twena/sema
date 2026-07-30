import { Suspense, lazy, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Code2, Sparkles } from "lucide-react";
import type { ChatResponse, TurnFeedback } from "../lib/api";
import { Card } from "./ui/Card";
import { KpiCards } from "./KpiCards";
import { DataTable } from "./DataTable";
import { RecommendedActions } from "./RecommendedActions";
import { MessageActions } from "./MessageActions";
import { SqlBlock } from "./SqlBlock";
import type { DrillContext, ThreadCountLookup } from "./DrillChat";
import { ConfidenceBadge, EvidencePanel, NoticeBadges, PeriodBanner } from "./EvidencePanel";
import { CopyableBlock } from "./CopyButton";
import { CodeBlock, InlineCode } from "./CodeBlock";
import { ModeCard } from "./ModeCard";
import { copyRich } from "../lib/clipboard";

// Recharts is heavy (~half the bundle); load it only when an answer has a chart.
const ChartRenderer = lazy(() => import("./ChartRenderer").then((m) => ({ default: m.ChartRenderer })));

const SUMMARY_HEADING = { rtl: "סיכום בקצרה", ltr: "In short" } as const;

/**
 * The answer's headline takeaway, above everything else.
 *
 * Renders the STRUCTURED `summary` field and nothing else -- it is never
 * derived from `answer` by slicing, truncation, markdown parsing or a second
 * model call. No summary means no block, which is why this returns null rather
 * than falling back to an extract.
 *
 * Plain text by design: a summary is one or two sentences, so markdown would
 * only invite the model to smuggle headings and tables above the fold.
 */
function AnswerSummary({ text, dir }: { text: string; dir: "rtl" | "ltr" }) {
  return (
    <div className="mb-3 rounded-xl border border-lineSoft bg-primary/[0.06] px-4 py-3">
      <div className="flex items-center gap-1.5 mb-1">
        <Sparkles size={13} className="text-primary shrink-0" aria-hidden />
        <span className="text-[0.68rem] font-semibold uppercase tracking-wide text-primary-dark">
          {SUMMARY_HEADING[dir]}
        </span>
      </div>
      {/* unicodeBidi: plaintext so a Hebrew summary inside an LTR card (or the
          reverse) lays out by its OWN direction, matching the alert messages. */}
      <p className="text-[0.95rem] font-medium leading-relaxed text-ink" style={{ unicodeBidi: "plaintext" }}>
        {text}
      </p>
    </div>
  );
}

export function AssistantResponseCard({
  response,
  dir,
  turnIndex = 0,
  conversationId,
  clientId,
  feedback,
  getThreadCount,
  onDrill,
  onRetry,
  onAsk,
  onFeedback,
}: {
  response: ChatResponse;
  dir: "rtl" | "ltr";
  /** Position in the transcript; anchors any widget the user drills into (see
   * conversationId below). */
  turnIndex?: number;
  /** The conversation this answer belongs to. Present -> widgets in this
   * answer anchor their drill-downs here (persisted threads); absent (e.g.
   * the home dashboard's overview KPIs, which have no parent conversation) ->
   * widgets drill ephemerally, exactly as before threads existed. */
  conversationId?: string;
  /** Which client's DB this answer belongs to -- needed alongside
   * conversationId/turnIndex to persist feedback. */
  clientId?: string;
  /** This turn's current feedback (answer_feedback_prompt.md), hydrated from
   * the hosting turn -- undefined/null renders as unrated. */
  feedback?: TurnFeedback | null;
  /** Stable lookup for an existing thread's follow-up count, keyed by turn +
   * widget. Undefined wherever conversationId is (no anchor, nothing to look
   * up). See DrillChat.ThreadCountLookup for the stability contract. */
  getThreadCount?: ThreadCountLookup;
  onDrill?: (ctx: DrillContext) => void;
  onRetry?: () => void;
  /** Sends a follow-up in the SAME conversation -- drives clarification
   * choices and cannot-answer alternatives. */
  onAsk?: (q: string) => void;
  onFeedback?: (feedback: TurnFeedback | null) => void;
}) {
  const proseRef = useRef<HTMLDivElement>(null);

  // Built once here rather than threaded as two separate props into every
  // leaf: every widget in THIS answer shares the same anchor, so there is one
  // {conversationId, turnIndex} object and one per-kind threadCount closure.
  const anchor = conversationId !== undefined ? { conversationId, turnIndex } : undefined;
  const kpiThreadCount = (title: string) => getThreadCount?.(turnIndex, "kpi", title);
  const chartThreadCount = (title: string) => getThreadCount?.(turnIndex, "chart", title);
  const tableThreadCount = (title: string) => getThreadCount?.(turnIndex, "table", title);
  const actionThreadCount = (title: string) => getThreadCount?.(turnIndex, "action", title);

  // Whitespace-only is treated as absent, so a blank field can never render an
  // empty tinted block or add a stray heading to the clipboard.
  const summary = response.summary?.trim() || null;
  // "Copy answer" and "Copy text" both use this, so the summary is included
  // exactly once whichever control the user reaches for.
  const copyPlain = summary
    ? `${SUMMARY_HEADING[dir]}\n${summary}\n\n${response.answer}`
    : response.answer;
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
        <div dir={dir} style={{ textAlign: dir === "rtl" ? "right" : "left" }} className="max-w-3xl">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary to-mint" />
            <span className="text-xs font-semibold text-primary-dark">SEMA</span>
          </div>
          <NoticeBadges notices={response.notices} dir={dir} />
          <ModeCard response={response} dir={dir} onAsk={onAsk} />
          <MessageActions
            text={response.answer}
            onRetry={onRetry}
            conversationId={anchor?.conversationId}
            turnIndex={anchor?.turnIndex}
            clientId={clientId}
            feedback={feedback}
            onFeedbackChange={onFeedback}
          />
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <div dir={dir} style={{ textAlign: dir === "rtl" ? "right" : "left" }}>
        {/* Reading content stays a narrow column for line-length readability
            even once the card itself spans the wide xl/2xl container -- only
            the data widgets below (KPIs/chart/table) take the full width. */}
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary to-mint" />
            <span className="text-xs font-semibold text-primary-dark">SEMA</span>
            <ConfidenceBadge confidence={response.confidence} />
          </div>

          <NoticeBadges notices={response.notices} dir={dir} />
          <PeriodBanner dateRange={response.evidence?.date_range} />

          {summary && <AnswerSummary text={summary} dir={dir} />}

          {/* Plain text gets the raw markdown source; rich targets get the
           * rendered HTML straight off the DOM node. The summary is prepended to
           * BOTH formats rather than living inside proseRef -- inside, it would
           * reach the rich copy but not the plain one. */}
          <CopyableBlock
            title="Copy this text"
            actions={[
              {
                label: "Copy text",
                run: () =>
                  copyRich(
                    copyPlain,
                    summary
                      ? `<p><strong>${SUMMARY_HEADING[dir]}</strong><br>${summary}</p>${
                          proseRef.current?.innerHTML ?? response.answer
                        }`
                      : (proseRef.current?.innerHTML ?? response.answer),
                  ),
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
        </div>

        {response.kpis.length > 0 && (
          <div className="mt-3">
            <KpiCards
              kpis={response.kpis}
              dir={dir}
              anchor={anchor}
              threadCount={kpiThreadCount}
              onDrill={onDrill}
            />
          </div>
        )}

        {response.chart && (
          <Suspense fallback={<div className="mt-3 h-[280px] xl:h-[330px] rounded-xl bg-surfaceAlt animate-pulse" />}>
            <ChartRenderer
              chart={response.chart}
              dir={dir}
              anchor={anchor}
              threadCount={chartThreadCount}
              onDrill={onDrill}
            />
          </Suspense>
        )}

        {response.table && (
          <DataTable
            table={response.table}
            dir={dir}
            anchor={anchor}
            threadCount={tableThreadCount}
            onDrill={onDrill}
          />
        )}
        {response.actions.length > 0 && (
          <RecommendedActions
            actions={response.actions}
            dir={dir}
            anchor={anchor}
            threadCount={actionThreadCount}
            onDrill={onDrill}
          />
        )}

        <div className="max-w-3xl">
          {response.sql_used && (
            <details className="mt-4">
              <summary className="cursor-pointer list-none flex items-center gap-1.5 text-xs font-medium text-muted hover:text-primary transition w-fit">
                <Code2 size={14} /> View SQL
              </summary>
              <SqlBlock sql={response.sql_used} />
            </details>
          )}

          <EvidencePanel evidence={response.evidence} dir={dir} />

          <MessageActions
            text={copyPlain}
            onRetry={onRetry}
            conversationId={anchor?.conversationId}
            turnIndex={anchor?.turnIndex}
            clientId={clientId}
            feedback={feedback}
            onFeedbackChange={onFeedback}
          />
        </div>
      </div>
    </Card>
  );
}
