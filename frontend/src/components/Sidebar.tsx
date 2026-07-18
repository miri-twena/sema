import { useEffect, useRef, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import type { Client, ConversationSummary, PopularQuestion } from "../lib/api";
import { ClientSelector } from "./ClientSelector";
import { ConversationList } from "./ConversationList";
import type { ConversationActions } from "./ConversationItem";
import { KPI_TINTS } from "../lib/tokens";

// Each sidebar question category gets its own pastel tint from the SAME
// palette used for KPI cards elsewhere (KPI_TINTS: [bg, text] pairs), so the
// lists read as distinct groups at a glance without introducing new colors.
const SUGGESTED_TINT = KPI_TINTS[2]; // lavender -- matches the app's primary accent
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
  popularQuestions,
  conversations,
  activeConversationId,
  conversationsLoading,
  conversationsError,
  conversationActions,
  onPick,
  onNewConversation,
  dbConnected,
}: {
  clients: Client[];
  activeId: string;
  onClientChange: (id: string) => void;
  suggested: string[];
  popularQuestions: PopularQuestion[];
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  conversationsLoading: boolean;
  conversationsError: boolean;
  conversationActions: ConversationActions;
  onPick: (q: string) => void;
  onNewConversation: () => void;
  dbConnected: boolean;
}) {
  // Search is toggled by the magnifying-glass icon; open it, type to filter.
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  const closeSearch = () => {
    setSearchOpen(false);
    setSearch("");
  };

  return (
    <aside className="w-72 shrink-0 h-full border-r border-line bg-surface flex flex-col">
      <div className="p-5 pb-3 shrink-0">
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

        <div className="mt-4 flex items-center gap-2">
          <button
            onClick={onNewConversation}
            className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium py-2.5 shadow-bubble hover:bg-primary/90 transition"
          >
            <Plus size={16} strokeWidth={2.5} /> New chat
          </button>
          <button
            onClick={() => (searchOpen ? closeSearch() : setSearchOpen(true))}
            aria-label={searchOpen ? "Close search" : "Search chats"}
            aria-expanded={searchOpen}
            title="Search chats"
            className={`shrink-0 w-10 h-10 rounded-xl border flex items-center justify-center transition ${
              searchOpen
                ? "border-primary text-primary bg-primary/10"
                : "border-line text-muted hover:text-ink hover:bg-surfaceAlt"
            }`}
          >
            <Search size={17} />
          </button>
        </div>

        {searchOpen && (
          <div className="mt-2 flex items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 focus-within:border-primary transition">
            <Search size={14} className="shrink-0 text-faint" />
            <input
              ref={searchRef}
              value={search}
              dir="auto"
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && closeSearch()}
              placeholder="Search chats..."
              className="flex-1 min-w-0 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-faint"
            />
            {search && (
              <button
                onClick={() => {
                  setSearch("");
                  searchRef.current?.focus();
                }}
                aria-label="Clear search"
                className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}
      </div>

      {/* conversation history -- the primary, scrollable content */}
      <div className="flex-1 min-h-0 overflow-auto sema-scroll px-4 py-1">
        <ConversationList
          conversations={conversations}
          activeId={activeConversationId}
          actions={conversationActions}
          loading={conversationsLoading}
          error={conversationsError}
          search={searchOpen ? search : ""}
        />
      </div>

      {/* discovery aids, pinned to the bottom */}
      <div className="shrink-0 border-t border-line px-5 py-4 max-h-[42%] overflow-auto sema-scroll">
        <QuestionList
          label="Suggested questions"
          items={suggested.map((q) => ({ text: q }))}
          tint={SUGGESTED_TINT}
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
