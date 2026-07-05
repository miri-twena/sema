import { ArrowRight } from "lucide-react";
import type { DrillContext } from "./DrillChat";

export function RecommendedActions({
  actions,
  onDrill,
}: {
  actions: string[];
  onDrill?: (ctx: DrillContext) => void;
}) {
  if (!actions?.length) return null;
  return (
    <div className="mt-4">
      <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted mb-2">Recommended actions</div>
      <div className="flex flex-col gap-2">
        {actions.map((action, i) => {
          const open = onDrill
            ? () =>
                onDrill({
                  title: action.length > 48 ? action.slice(0, 48) + "…" : action,
                  contextBlock: `The user is asking about this recommended action: "${action}". Explain how to execute it, what results to expect, and what to measure.`,
                  initialInput: action,
                })
            : undefined;

          return (
            <button
              key={i}
              onClick={open}
              disabled={!open}
              aria-label={open ? `Discuss: ${action}` : undefined}
              className={`group text-start w-full flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-all ${
                open ? "cursor-pointer hover:border-primary hover:shadow-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary" : "cursor-default"
              }`}
            >
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                <ArrowRight size={14} strokeWidth={2.5} />
              </span>
              <span className="text-sm text-ink leading-snug">{action}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
