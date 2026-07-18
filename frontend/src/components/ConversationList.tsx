import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { ConversationSummary } from "../lib/api";
import { ConversationItem, type ConversationActions } from "./ConversationItem";

const COLLAPSE_KEY = "sema:convSections"; // { pinned: bool, recent: bool } = open state

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "{}");
  } catch {
    return {};
  }
}

function Section({
  id,
  label,
  items,
  activeId,
  actions,
  emptyHint,
}: {
  id: "pinned" | "recent";
  label: string;
  items: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
  emptyHint: React.ReactNode;
}) {
  // Open by default; the stored map only records deviations from that.
  const [open, setOpen] = useState<boolean>(() => loadCollapsed()[id] !== false);

  useEffect(() => {
    const map = loadCollapsed();
    map[id] = open;
    try {
      localStorage.setItem(COLLAPSE_KEY, JSON.stringify(map));
    } catch {
      /* storage unavailable */
    }
  }, [id, open]);

  // Both sections are always shown so the structure is stable and each can be
  // collapsed independently -- an empty section shows a hint rather than
  // disappearing (which used to make Recent look like it had replaced Pinned).
  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-1 px-1 mb-1 text-[0.7rem] font-semibold uppercase tracking-wide text-muted hover:text-ink transition"
      >
        <ChevronDown size={13} className={`transition-transform ${open ? "" : "-rotate-90"}`} />
        {label}
        <span className="ms-auto text-faint font-normal">{items.length}</span>
      </button>
      {open &&
        (items.length > 0 ? (
          <div className="flex flex-col gap-0.5">
            {items.map((c) => (
              <ConversationItem
                key={c.id}
                conversation={c}
                active={c.id === activeId}
                actions={actions}
              />
            ))}
          </div>
        ) : (
          <div className="px-2 py-1.5 text-[0.76rem] text-faint leading-relaxed">{emptyHint}</div>
        ))}
    </div>
  );
}

/**
 * The chat-history panel: Pinned then Recent, each independently collapsible
 * with its state persisted locally. The server already sorts (pinned first,
 * then most recently updated), so this only splits the single list into its
 * two sections. Both sections are always shown -- an empty one shows a hint,
 * so Recent never looks like it has replaced Pinned.
 */
export function ConversationList({
  conversations,
  activeId,
  actions,
  loading,
  error,
  search = "",
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
  loading: boolean;
  error: boolean;
  /** When non-empty, show a flat list of title matches instead of sections. */
  search?: string;
}) {
  if (error) {
    return <div className="px-1 py-2 text-[0.78rem] text-muted">Couldn't load chat history.</div>;
  }
  if (loading && conversations.length === 0) {
    return (
      <div className="flex flex-col gap-1.5 px-1 py-1" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-8 rounded-lg bg-surfaceAlt animate-pulse" />
        ))}
      </div>
    );
  }

  // Search mode: a flat list of title matches (order preserved -> pinned still
  // first), no sections -- these are results, not organization.
  const query = search.trim().toLowerCase();
  if (query) {
    const matches = conversations.filter((c) => c.title.toLowerCase().includes(query));
    if (matches.length === 0) {
      return (
        <div className="px-2 py-2 text-[0.78rem] text-muted leading-relaxed">
          No chats match “{search.trim()}”.
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-0.5">
        {matches.map((c) => (
          <ConversationItem key={c.id} conversation={c} active={c.id === activeId} actions={actions} />
        ))}
      </div>
    );
  }

  const pinned = conversations.filter((c) => c.pinned);
  const recent = conversations.filter((c) => !c.pinned);

  return (
    <div>
      <Section
        id="pinned"
        label="Pinned"
        items={pinned}
        activeId={activeId}
        actions={actions}
        emptyHint="Pin a chat from its ⋯ menu to keep it here."
      />
      <Section
        id="recent"
        label="Recent"
        items={recent}
        activeId={activeId}
        actions={actions}
        emptyHint={
          <>
            No conversations yet. Start one with{" "}
            <span className="font-medium text-ink">New chat</span>.
          </>
        }
      />
    </div>
  );
}
