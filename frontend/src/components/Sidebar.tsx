import { useEffect, useRef, useState } from "react";
import { PanelLeftClose, Plus, Search, X } from "lucide-react";
import type { ConversationSummary, PopularQuestion } from "../lib/api";
import { ConversationList } from "./ConversationList";
import type { ConversationActions } from "./ConversationItem";
import { SidebarSection } from "./SidebarSection";
import { KPI_TINTS } from "../lib/tokens";

// Fixed pastel tint per category (from the shared KPI palette), so every item
// in a category reads as one coloured group. [background, text/border] pairs.
const PINNED_TINT = KPI_TINTS[3]; // mint
const RECENT_TINT = KPI_TINTS[0]; // peach
const SUGGESTED_TINT = KPI_TINTS[2]; // lavender -- matches the app's primary accent
const POPULAR_TINT = KPI_TINTS[1]; // sky

// Open/closed state for the question categories, persisted locally so a
// collapsed section stays collapsed across refreshes (parallel to the
// ConversationList sections' own `sema:convSections` map).
const QSECTION_KEY = "sema:questionSections";

function loadQOpen(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(QSECTION_KEY) || "{}");
  } catch {
    return {};
  }
}

// Pastel question cards for one category: soft tinted background, subtle
// border, hover elevation, up to two lines then truncated (full text in the
// native tooltip). The whole card is a button, so click + keyboard activation
// and a visible focus ring come for free.
function QuestionCards({
  items,
  tint,
  onPick,
}: {
  items: { text: string; badge?: string }[];
  tint: readonly [string, string];
  onPick: (q: string) => void;
}) {
  const [bg, fg] = tint;
  return (
    <div className="flex flex-col gap-2">
      {items.map((item, i) => (
        <button
          key={i}
          onClick={() => onPick(item.text)}
          title={item.text}
          dir="auto"
          style={{ background: bg, color: fg, borderColor: `${fg}33` }}
          className="text-start rounded-xl border text-[0.82rem] px-3 py-2.5 leading-snug hover:brightness-[0.98] hover:-translate-y-px hover:shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition flex items-start justify-between gap-2"
        >
          <span className="line-clamp-2">{item.text}</span>
          {item.badge && (
            <span
              className="shrink-0 mt-px text-[0.66rem] font-semibold rounded-full px-1.5 py-0.5"
              style={{ background: `${fg}1f` }}
            >
              {item.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Sidebar({
  suggested,
  popularQuestions,
  conversations,
  activeConversationId,
  conversationsLoading,
  conversationsError,
  conversationActions,
  onPick,
  onNewConversation,
  onGoHome,
  onCollapse,
}: {
  suggested: string[];
  popularQuestions: PopularQuestion[];
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  conversationsLoading: boolean;
  conversationsError: boolean;
  conversationActions: ConversationActions;
  onPick: (q: string) => void;
  onNewConversation: () => void;
  /** Clicking the brand returns to the home screen (new chat). */
  onGoHome: () => void;
  /** Collapse (hide) the sidebar -- desktop collapses the panel, mobile closes
   *  the drawer. Expanded again from the header's expand button. */
  onCollapse: () => void;
}) {
  // Search is toggled by the magnifying-glass icon; open it, type to filter.
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const searching = searchOpen && search.trim().length > 0;

  // Per-category open state (Suggested / Popular). Defaults to open; the stored
  // map only records deviations, so a section the user collapsed stays collapsed.
  const [qOpen, setQOpen] = useState<Record<string, boolean>>(() => loadQOpen());
  const isQOpen = (id: string) => qOpen[id] !== false;
  const toggleQ = (id: string) =>
    setQOpen((prev) => {
      const next = { ...prev, [id]: prev[id] === false };
      try {
        localStorage.setItem(QSECTION_KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable */
      }
      return next;
    });

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
        <div className="flex items-start justify-between gap-2 mb-1">
          {/* brand -- clicking it returns to the home screen (new chat) */}
          <button
            type="button"
            onClick={onGoHome}
            aria-label="Go to home"
            title="Home"
            className="flex items-center gap-2.5 rounded-lg -mx-1 px-1 py-0.5 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
          >
            <span className="inline-block w-7 h-7 rounded-lg bg-gradient-to-br from-primary via-sky to-mint" />
            <span className="text-xl font-semibold text-ink">SEMA</span>
          </button>
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="shrink-0 w-8 h-8 -mt-0.5 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
        <div className="text-xs text-muted mb-5 ps-1">AI Business Advisor</div>

        <div className="flex items-center gap-2">
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

      {/* All categories stacked in ONE scroll area, one below the other:
          Pinned + Recent (chats), then Suggested + Popular (questions). No
          second pane -- the sidebar is a single continuous, scrollable list. */}
      <div className="flex-1 min-h-0 overflow-auto sema-scroll px-4 py-1">
        <ConversationList
          conversations={conversations}
          activeId={activeConversationId}
          actions={conversationActions}
          loading={conversationsLoading}
          error={conversationsError}
          search={searchOpen ? search : ""}
          pinnedTint={PINNED_TINT}
          recentTint={RECENT_TINT}
        />

        {/* Discovery questions -- hidden while searching (results only). */}
        {!searching && suggested.length > 0 && (
          <SidebarSection
            title="Suggested questions"
            count={suggested.length}
            open={isQOpen("suggested")}
            onToggle={() => toggleQ("suggested")}
          >
            <QuestionCards items={suggested.map((q) => ({ text: q }))} tint={SUGGESTED_TINT} onPick={onPick} />
          </SidebarSection>
        )}
        {!searching && popularQuestions.length > 0 && (
          <SidebarSection
            title="Popular in your company"
            count={popularQuestions.length}
            open={isQOpen("popular")}
            onToggle={() => toggleQ("popular")}
          >
            <QuestionCards
              items={popularQuestions.map((p) => ({ text: p.question, badge: `${p.times_asked}×` }))}
              tint={POPULAR_TINT}
              onPick={onPick}
            />
          </SidebarSection>
        )}
      </div>
    </aside>
  );
}
