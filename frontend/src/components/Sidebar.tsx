import { useEffect, useRef, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import type { Client, ConversationSummary } from "../lib/api";
import { ConversationList } from "./ConversationList";
import type { ConversationActions } from "./ConversationItem";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

/**
 * Navigation and conversations only. Discovery questions (suggested /
 * popular) deliberately live on the home screen instead: mixing "things you
 * did" with "things you could ask" made the sidebar a second dashboard, and
 * the pastel cards competed with the active-chat highlight.
 *
 * Colour rule: the sidebar is neutral. The one accent-coloured row is the
 * active conversation.
 */
export function Sidebar({
  clients,
  activeClientId,
  dbConnected,
  conversations,
  activeConversationId,
  conversationsLoading,
  conversationsError,
  conversationActions,
  onSwitchClient,
  onNewConversation,
  onGoHome,
}: {
  clients: Client[];
  activeClientId: string;
  dbConnected: boolean;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  conversationsLoading: boolean;
  conversationsError: boolean;
  conversationActions: ConversationActions;
  onSwitchClient: (id: string) => void;
  onNewConversation: () => void;
  /** Clicking the brand returns to the home screen (new chat). */
  onGoHome: () => void;
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
    <aside className="w-72 shrink-0 h-full border-e border-line bg-surface flex flex-col">
      <div className="p-5 pb-3 shrink-0">
        {/* brand -- clicking it returns to the home screen (new chat) */}
        <button
          type="button"
          onClick={onGoHome}
          aria-label="Go to home"
          title="Home"
          className="flex items-center gap-2.5 mb-1 rounded-lg -mx-1 px-1 py-0.5 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
        >
          <span className="inline-block w-7 h-7 rounded-lg bg-gradient-to-br from-primary via-sky to-mint" />
          <span className="text-xl font-semibold text-ink">SEMA</span>
        </button>
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

      {/* Conversations fill the remaining height; the workspace switcher is
          pinned below them. */}
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

      {clients.length > 0 && (
        <WorkspaceSwitcher
          clients={clients}
          activeId={activeClientId}
          dbConnected={dbConnected}
          onSwitch={onSwitchClient}
        />
      )}
    </aside>
  );
}
