import { Plus } from "lucide-react";
import type { Client, PopularQuestion } from "../lib/api";
import { ClientSelector } from "./ClientSelector";
import { KPI_TINTS } from "../lib/tokens";

// Each sidebar question category gets its own pastel tint from the SAME
// palette used for KPI cards elsewhere (KPI_TINTS: [bg, text] pairs), so the
// three lists read as distinct groups at a glance without introducing new
// colors into the app.
const SUGGESTED_TINT = KPI_TINTS[2]; // lavender -- matches the app's primary accent
const RECENT_TINT = KPI_TINTS[3]; // mint
const POPULAR_TINT = KPI_TINTS[1]; // sky

function QuestionList({
  label,
  items,
  tint,
  onPick,
}: {
  label: string;
  items: { text: string; badge?: string }[];
  tint: readonly [string, string];
  onPick: (q: string) => void;
}) {
  if (!items.length) return null;
  const [bg, fg] = tint;
  return (
    <div className="mb-5">
      <div className="text-[0.72rem] font-semibold uppercase tracking-wide mb-2" style={{ color: fg }}>
        {label}
      </div>
      <div className="flex flex-col gap-2">
        {items.map((item, i) => (
          <button
            key={i}
            onClick={() => onPick(item.text)}
            style={{ background: bg, color: fg, borderColor: `${fg}33` }}
            className="text-start rounded-xl border text-[0.82rem] px-3 py-2.5 leading-snug hover:brightness-[0.97] hover:-translate-y-px hover:shadow-card transition flex items-center justify-between gap-2"
          >
            <span className="truncate">{item.text}</span>
            {item.badge && (
              <span className="shrink-0 text-[0.68rem] font-medium opacity-70">{item.badge}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Sidebar({
  clients,
  activeId,
  onClientChange,
  suggested,
  questionHistory,
  popularQuestions,
  onPick,
  onNewConversation,
  dbConnected,
}: {
  clients: Client[];
  activeId: string;
  onClientChange: (id: string) => void;
  suggested: string[];
  questionHistory: string[];
  popularQuestions: PopularQuestion[];
  onPick: (q: string) => void;
  onNewConversation: () => void;
  dbConnected: boolean;
}) {
  return (
    <aside className="w-72 shrink-0 h-full border-r border-line bg-surface flex flex-col">
      <div className="p-5">
        {/* brand */}
        <div className="flex items-center gap-2.5 mb-1">
          <span className="inline-block w-7 h-7 rounded-lg bg-gradient-to-br from-primary via-sky to-mint" />
          <span className="text-xl font-semibold text-ink">SEMA</span>
        </div>
        <div className="text-xs text-muted mb-5">AI Business Advisor</div>

        {clients.length > 0 && (
          <ClientSelector clients={clients} activeId={activeId} onChange={onClientChange} />
        )}

        <div className="flex items-center gap-1.5 mt-2 text-[0.75rem]">
          <span className={`w-2 h-2 rounded-full ${dbConnected ? "bg-emerald-500" : "bg-red-500"}`} />
          <span className={dbConnected ? "text-emerald-600" : "text-red-500"}>
            {dbConnected ? "Connected" : "Disconnected"}
          </span>
        </div>

        <button
          onClick={onNewConversation}
          className="w-full mt-4 flex items-center justify-center gap-1.5 rounded-xl border border-lineSoft bg-primary/10 text-primary-dark text-sm font-medium py-2 hover:bg-primary/15 transition"
        >
          <Plus size={15} strokeWidth={2.5} /> New conversation
        </button>
      </div>

      <div className="px-5 pb-5 overflow-auto sema-scroll">
        <QuestionList
          label="Suggested questions"
          items={suggested.map((q) => ({ text: q }))}
          tint={SUGGESTED_TINT}
          onPick={onPick}
        />
        <QuestionList
          label="Your recent questions"
          items={questionHistory.map((q) => ({ text: q }))}
          tint={RECENT_TINT}
          onPick={onPick}
        />
        <QuestionList
          label="Popular in your company"
          items={popularQuestions.map((p) => ({
            text: p.question,
            badge: `${p.times_asked}×`,
          }))}
          tint={POPULAR_TINT}
          onPick={onPick}
        />
      </div>
    </aside>
  );
}
