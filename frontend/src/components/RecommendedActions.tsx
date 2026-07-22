import { ArrowRight } from "lucide-react";
import type { DrillContext } from "./DrillChat";
import { ThreadBadge } from "./ThreadBadge";
import { followUpsLabel } from "../lib/format";

export function RecommendedActions({
  actions,
  dir,
  anchor,
  threadCount,
  onDrill,
}: {
  actions: string[];
  dir?: "rtl" | "ltr";
  anchor?: { conversationId: string; turnIndex: number };
  threadCount?: (title: string) => number | undefined;
  onDrill?: (ctx: DrillContext) => void;
}) {
  if (!actions?.length) return null;
  return (
    <div className="mt-4">
      <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted mb-2">Recommended actions</div>
      <div className="flex flex-col gap-2">
        {actions.map((action, i) => {
          const badge = threadCount?.(action);
          const open = onDrill
            ? () =>
                onDrill({
                  kind: "action",
                  title: action,
                  detail: action,
                  initialInput: action,
                  dir,
                  ...anchor,
                })
            : undefined;

          return (
            <button
              key={i}
              onClick={open}
              disabled={!open}
              aria-label={open ? `Discuss: ${action}${followUpsLabel(badge)}` : undefined}
              className={`group text-start w-full flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-all ${
                open ? "cursor-pointer hover:border-primary hover:shadow-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary" : "cursor-default"
              }`}
            >
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                <ArrowRight size={14} strokeWidth={2.5} />
              </span>
              <span className="text-sm text-ink leading-snug flex-1">{action}</span>
              {typeof badge === "number" && <ThreadBadge count={badge} className="mt-0.5" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
