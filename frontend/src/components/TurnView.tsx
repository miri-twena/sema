import { memo } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import type { ChatTurn } from "../hooks/useChat";
import { ChatMessage } from "./ChatMessage";
import { AssistantResponseCard } from "./AssistantResponseCard";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ProgressPanel } from "./ProgressPanel";
import { ErrorBoundary } from "./ErrorBoundary";
import type { DrillContext } from "./DrillChat";

// One question/answer turn. Memoized: completed turns keep referential identity
// (useChat only replaces the last turn), so a new message never re-renders the
// whole transcript.
export const TurnView = memo(function TurnView({
  turn,
  index,
  isFirst,
  onDrill,
  onRetry,
  onAsk,
}: {
  turn: ChatTurn;
  index: number;
  isFirst: boolean;
  onDrill?: (ctx: DrillContext) => void;
  onRetry?: (index: number) => void;
  onAsk?: (q: string) => void;
}) {
  const r = turn.response;
  return (
    <div className={isFirst ? "" : "border-t border-line pt-4 mt-4"}>
      <ChatMessage text={turn.question} dir={turn.dir} />
      {r ? (
        r.status === "error" ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-critical-fg/30 bg-critical-bg px-4 py-3 text-sm text-critical-fg">
            <span className="flex items-center gap-2 min-w-0">
              <AlertTriangle size={16} className="shrink-0" />
              <span className="truncate">Something went wrong. Please try again.</span>
            </span>
            {onRetry && (
              <button
                onClick={() => onRetry(index)}
                className="shrink-0 flex items-center gap-1 rounded-lg border border-critical-fg/40 px-2.5 py-1 text-xs font-medium hover:bg-critical-fg/10 transition"
              >
                <RotateCw size={13} /> Retry
              </button>
            )}
          </div>
        ) : (
          <ErrorBoundary>
            <AssistantResponseCard
              response={r}
              dir={turn.dir}
              onDrill={onDrill}
              onRetry={onRetry ? () => onRetry(index) : undefined}
              onAsk={onAsk}
            />
          </ErrorBoundary>
        )
      ) : turn.stopped ? (
        <div className="px-1 py-3 text-sm italic text-muted">Response stopped.</div>
      ) : turn.progress?.length ? (
        <ProgressPanel events={turn.progress} dir={turn.dir} />
      ) : (
        <ThinkingIndicator />
      )}
    </div>
  );
});
