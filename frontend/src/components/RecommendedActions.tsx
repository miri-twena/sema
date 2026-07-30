import { ArrowRight } from "lucide-react";
import type { DrillContext } from "./DrillChat";
import type { RecommendedAction } from "../lib/api";
import { ThreadBadge } from "./ThreadBadge";
import { followUpsLabel } from "../lib/format";
import { CopyButton } from "./CopyButton";
import { copyText, stripMarkdown } from "../lib/clipboard";

const COPY_LABEL = { rtl: "העתק המלצה", ltr: "Copy recommendation" } as const;

const EFFORT_LABEL: Record<"low" | "medium" | "high", string> = {
  low: "Low effort",
  medium: "Medium effort",
  high: "High effort",
};

// Distinct muted tint per effort level -- a quick visual read of what to
// tackle first without needing to read the label.
const EFFORT_TINT: Record<"low" | "medium" | "high", string> = {
  low: "bg-mint/25 text-ink",
  medium: "bg-sun/40 text-ink",
  high: "bg-coral/30 text-ink",
};

function EffortBadge({ effort }: { effort: "low" | "medium" | "high" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.66rem] font-medium whitespace-nowrap ${EFFORT_TINT[effort]}`}
    >
      {EFFORT_LABEL[effort]}
    </span>
  );
}

/** Normalizes a possibly-legacy plain-string action into the structured
 * shape, so every entry renders through one code path regardless of when it
 * was persisted (a conversation from before recommended_actions became
 * structured stores a bare string array). */
function normalize(action: string | RecommendedAction): RecommendedAction {
  return typeof action === "string" ? { action } : action;
}

export function RecommendedActions({
  actions,
  dir,
  anchor,
  threadCount,
  onDrill,
}: {
  actions: (string | RecommendedAction)[];
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
        {actions.map((raw, i) => {
          const { action: title, why, expected_impact, effort } = normalize(raw);
          const badge = threadCount?.(title);
          // Richer drill context when there's evidence to hand off, without
          // changing what identifies this widget's thread (still `title`).
          const detail = [title, why && `Why: ${why}`, expected_impact && `Expected impact: ${expected_impact}`]
            .filter(Boolean)
            .join(" ");
          const open = onDrill
            ? () =>
                onDrill({
                  kind: "action",
                  title,
                  detail,
                  initialInput: title,
                  dir,
                  ...anchor,
                })
            : undefined;

          // Plain-text clipboard payload: action + why + impact, one per
          // line, markdown stripped -- distinct from `detail` above (which
          // is space-joined, built for the drill-chat prompt, not for reading).
          const copyPayload = stripMarkdown(
            [title, why && `Why: ${why}`, expected_impact && `Expected impact: ${expected_impact}`]
              .filter(Boolean)
              .join("\n"),
          );

          return (
            // Not a <button>: the copy control below is a real nested
            // <button>, and buttons can't nest. role="button" + onKeyDown
            // keeps the whole-card click/keyboard affordance identical.
            <div
              key={i}
              role={open ? "button" : undefined}
              tabIndex={open ? 0 : undefined}
              onClick={open}
              onKeyDown={
                open
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        open();
                      }
                    }
                  : undefined
              }
              aria-label={open ? `Discuss: ${title}${followUpsLabel(badge)}` : undefined}
              className={`group sema-copy-host text-start w-full flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-all ${
                open ? "cursor-pointer hover:border-primary hover:shadow-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary" : "cursor-default"
              }`}
            >
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                <ArrowRight size={14} strokeWidth={2.5} />
              </span>
              <span className="flex-1 min-w-0 max-w-3xl">
                <span className="block text-sm text-ink leading-snug">{title}</span>
                {why && <span className="block mt-0.5 text-[0.78rem] text-muted leading-snug">{why}</span>}
                {(expected_impact || effort) && (
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {expected_impact && (
                      <span className="inline-flex items-center rounded-full bg-primary/10 text-primary-dark px-2 py-0.5 text-[0.66rem] font-medium">
                        {expected_impact}
                      </span>
                    )}
                    {effort && <EffortBadge effort={effort} />}
                  </span>
                )}
              </span>
              {/* Direct child of .sema-copy-host, per the CSS hover/focus
                  selector in index.css -- nesting it deeper would silently
                  break the reveal-on-hover behavior. */}
              <span className="sema-copy-affordance shrink-0 self-center">
                <CopyButton title={COPY_LABEL[dir === "rtl" ? "rtl" : "ltr"]} actions={[{ label: "Copy", run: () => copyText(copyPayload) }]} />
              </span>
              {typeof badge === "number" && <ThreadBadge count={badge} className="mt-0.5 shrink-0" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
