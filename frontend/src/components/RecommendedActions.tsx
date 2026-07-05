import { ArrowRight } from "lucide-react";

export function RecommendedActions({ actions }: { actions: string[] }) {
  if (!actions?.length) return null;
  return (
    <div className="mt-4">
      <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted mb-2">
        Recommended actions
      </div>
      <div className="flex flex-col gap-2">
        {actions.map((action, i) => (
          <div
            key={i}
            className="group flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-all hover:border-primary hover:shadow-card"
          >
            <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
              <ArrowRight size={14} strokeWidth={2.5} />
            </span>
            <span className="text-sm text-ink leading-snug">{action}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
