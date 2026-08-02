import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, ChevronLeft, ChevronRight, Plus, Search, X } from "lucide-react";
import type { Client, ConversationSummary } from "../lib/api";
import { useT } from "../locales";
import { ConversationList, Rows } from "./ConversationList";
import type { ConversationActions } from "./ConversationItem";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";
import { UserFooter } from "./UserFooter";
import { Logo } from "./brand/Logo";

// Resizable width (sidebar_improvements_prompt.md item 1). The sidebar is
// ALWAYS on the left (AGENTS.md's anchored-layout rule), so "resize" only
// ever means dragging the RIGHT edge -- physical, never a logical/RTL-aware
// edge, matching ConversationItem.tsx's own physical-positioning convention.
const MIN_WIDTH = 220;
const MAX_WIDTH = 420;
const DEFAULT_WIDTH = 288; // the old fixed w-72
const WIDTH_KEY = "sema:sidebar:width";
const KEYBOARD_STEP = 16;

function loadWidth(): number {
  try {
    const raw = Number(localStorage.getItem(WIDTH_KEY));
    return Number.isFinite(raw) && raw > 0 ? clampWidth(raw) : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

function clampWidth(w: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w));
}

/**
 * Navigation and conversations only. Discovery questions (suggested /
 * popular) deliberately live on the home screen instead: mixing "things you
 * did" with "things you could ask" made the sidebar a second dashboard, and
 * the pastel cards competed with the active-chat highlight.
 *
 * Colour rule: the sidebar is neutral. The one accent-coloured row is the
 * active conversation. Desktop shows this permanently (App.tsx renders it
 * with no collapse control); the mobile off-canvas drawer mounts the same
 * component unchanged.
 */
export function Sidebar({
  clients,
  activeClientId,
  dbConnected,
  orgLogoUrl,
  conversations,
  activeConversationId,
  conversationsLoading,
  conversationsError,
  archivedConversations,
  archivedLoading,
  onLoadArchived,
  conversationActions,
  archivedActions,
  onSwitchClient,
  onNewConversation,
  onGoHome,
  onOpenAdmin,
}: {
  clients: Client[];
  activeClientId: string;
  dbConnected: boolean;
  /** The active client's uploaded logo (org settings §2), or null/undefined
   * to fall back to the initials avatar. */
  orgLogoUrl?: string | null;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  conversationsLoading: boolean;
  conversationsError: boolean;
  archivedConversations: ConversationSummary[];
  archivedLoading: boolean;
  /** Fetches the archived list; called each time the Archived view opens. */
  onLoadArchived: () => void;
  conversationActions: ConversationActions;
  /** Same shape as conversationActions, but onDelete targets the archived
   * list's own state so a deleted row disappears immediately. */
  archivedActions: ConversationActions;
  onSwitchClient: (id: string) => void;
  onNewConversation: () => void;
  /** Clicking the brand returns to the home screen (new chat). */
  onGoHome: () => void;
  /** Opens the organization admin panel from the workspace switcher's gear. */
  onOpenAdmin?: () => void;
}) {
  const t = useT();
  // Search is toggled by the "Search conversations" control; open it, type to filter.
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  // A separate toggle view (not part of the scrolling group list) for chats
  // the user archived -- rare enough that it isn't fetched until opened.
  const [archivedView, setArchivedView] = useState(false);

  const [width, setWidth] = useState(loadWidth);
  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      // Storage disabled -- the resize still works, it just won't persist.
    }
  }, [width]);

  // Pointer-based drag (no dnd library): a single pointer capture drives width
  // from the horizontal delta since drag start, clamped every frame so the
  // handle can never be dragged past the sensible min/max.
  const startDrag = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = width;
      const onMove = (ev: PointerEvent) => {
        setWidth(clampWidth(startWidth + (ev.clientX - startX)));
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [width],
  );

  const resetWidth = useCallback(() => setWidth(DEFAULT_WIDTH), []);

  const onHandleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") setWidth((w) => clampWidth(w - KEYBOARD_STEP));
    else if (e.key === "ArrowRight") setWidth((w) => clampWidth(w + KEYBOARD_STEP));
    else if (e.key === "Home") setWidth(MIN_WIDTH);
    else if (e.key === "End") setWidth(MAX_WIDTH);
    else return;
    e.preventDefault();
  }, []);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  // Both are per-client UI state; switching workspaces should land back on
  // the normal conversation list rather than another client's stale search.
  useEffect(() => {
    setSearchOpen(false);
    setSearch("");
    setArchivedView(false);
  }, [activeClientId]);

  const closeSearch = () => {
    setSearchOpen(false);
    setSearch("");
  };

  const openArchived = () => {
    setArchivedView(true);
    onLoadArchived();
  };

  return (
    <aside
      className="relative shrink-0 h-full border-e border-line bg-surface flex flex-col"
      style={{ width }}
    >
      <div className="p-5 pb-3 shrink-0">
        {/* brand -- clicking it returns to the home screen (new chat) */}
        <button
          type="button"
          onClick={onGoHome}
          aria-label="Go to home"
          title="Home"
          className="flex items-center gap-2.5 mb-1 rounded-lg -mx-1 px-1 py-0.5 hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
        >
          <Logo size={24} />
        </button>
        <div className="text-xs text-muted mb-4 ps-1">AI Business Advisor</div>

        <button
          onClick={onNewConversation}
          className="w-full flex items-center justify-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium py-2 shadow-bubble hover:bg-primary/90 transition"
        >
          <Plus size={16} strokeWidth={2.5} /> <span dir="auto">{t.sidebar.newConversation}</span>
        </button>

        {searchOpen ? (
          <div className="mt-2 flex items-center gap-1.5 rounded-xl border border-primary bg-surface px-2.5">
            <Search size={14} className="shrink-0 text-faint" />
            <input
              ref={searchRef}
              value={search}
              dir="auto"
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && closeSearch()}
              placeholder={t.sidebar.searchPlaceholder}
              className="flex-1 min-w-0 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-faint"
            />
            <button
              onClick={() => (search ? (setSearch(""), searchRef.current?.focus()) : closeSearch())}
              aria-label={search ? t.sidebar.clearSearch : t.sidebar.closeSearch}
              className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            aria-expanded={false}
            className="mt-2 w-full flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm text-muted hover:text-ink hover:bg-surfaceAlt transition"
          >
            <Search size={14} className="shrink-0" /> {t.sidebar.searchConversations}
          </button>
        )}
      </div>

      {/* Conversations fill the remaining height; the workspace switcher is
          pinned below them. Only this area scrolls. */}
      <div className="flex-1 min-h-0 overflow-auto sema-scroll px-4 py-1">
        {archivedView ? (
          <div>
            <button
              type="button"
              onClick={() => setArchivedView(false)}
              className="w-full flex items-center gap-1.5 px-1 py-2 mb-1 text-[0.82rem] font-medium text-ink hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-lg transition"
            >
              <ChevronLeft size={16} className="shrink-0" /> {t.sidebar.archived}
            </button>
            {archivedLoading && archivedConversations.length === 0 ? (
              <div className="flex flex-col gap-1.5 px-1 py-1" aria-busy="true">
                {[0, 1].map((i) => (
                  <div key={i} className="h-8 rounded-lg bg-surfaceAlt animate-pulse" />
                ))}
              </div>
            ) : archivedConversations.length === 0 ? (
              <div className="px-2 py-2 text-[0.78rem] text-faint leading-relaxed">{t.sidebar.noArchivedChats}</div>
            ) : (
              <Rows items={archivedConversations} activeId={activeConversationId} actions={archivedActions} />
            )}
          </div>
        ) : (
          <ConversationList
            conversations={conversations}
            activeId={activeConversationId}
            actions={conversationActions}
            loading={conversationsLoading}
            error={conversationsError}
            search={searchOpen ? search : ""}
          />
        )}
      </div>

      <button
        type="button"
        onClick={openArchived}
        className="shrink-0 w-full flex items-center gap-2.5 px-4 py-2.5 text-[0.82rem] text-muted hover:text-ink hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <Archive size={15} className="shrink-0" />
        <span className="flex-1 text-left">{t.sidebar.archived}</span>
        <ChevronRight size={14} className="shrink-0 text-faint" aria-hidden />
      </button>

      {clients.length > 0 && (
        <WorkspaceSwitcher
          clients={clients}
          activeId={activeClientId}
          dbConnected={dbConnected}
          logoUrl={orgLogoUrl}
          onSwitch={onSwitchClient}
          onOpenAdmin={onOpenAdmin}
        />
      )}
      <UserFooter />

      {/* Resize handle: a wide invisible hit-area with a thin visible line,
          pinned to the physical right edge (never `end-*` -- the sidebar
          never mirrors). Hover/focus highlights it; drag or Arrow keys
          resize; double-click or Home/End reset/jump to the clamps. */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuenow={width}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        tabIndex={0}
        onPointerDown={startDrag}
        onDoubleClick={resetWidth}
        onKeyDown={onHandleKeyDown}
        className="group absolute top-0 right-0 h-full w-2 translate-x-1/2 cursor-col-resize select-none touch-none focus-visible:outline-none"
      >
        <div className="mx-auto h-full w-px bg-transparent group-hover:bg-primary/50 group-focus-visible:bg-primary transition-colors" />
      </div>
    </aside>
  );
}
