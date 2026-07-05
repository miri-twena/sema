import { Plus } from "lucide-react";
import type { Client } from "../lib/api";
import { ClientSelector } from "./ClientSelector";

export function Sidebar({
  clients,
  activeId,
  onClientChange,
  suggested,
  onPick,
  onNewConversation,
  dbConnected,
}: {
  clients: Client[];
  activeId: string;
  onClientChange: (id: string) => void;
  suggested: string[];
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
        <div className="text-[0.72rem] font-semibold uppercase tracking-wide text-[#475569] mb-2">
          Suggested questions
        </div>
        <div className="flex flex-col gap-2">
          {suggested.map((q, i) => (
            <button
              key={i}
              onClick={() => onPick(q)}
              className="text-start rounded-xl border border-lineSoft bg-primary/[0.06] text-primary-dark text-[0.82rem] px-3 py-2.5 leading-snug hover:bg-surface hover:border-primary hover:-translate-y-px hover:shadow-card transition"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
