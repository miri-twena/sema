import { useEffect, useState } from "react";
import type { ConversationSummary } from "../lib/api";
import {
  GROUP_LABELS,
  GROUP_ORDER,
  bucketConversations,
  type GroupId,
} from "../lib/conversations";
import { ConversationItem, type ConversationActions } from "./ConversationItem";
import { SidebarSection } from "./SidebarSection";

const COLLAPSE_KEY = "sema:convSections"; // { [groupId]: bool } = open state

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "{}");
  } catch {
    return {};
  }
}

function Group({
  id,
  items,
  activeId,
  actions,
}: {
  id: GroupId;
  items: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
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

  return (
    <SidebarSection
      title={GROUP_LABELS[id]}
      count={items.length}
      open={open}
      onToggle={() => setOpen((o) => !o)}
    >
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
    </SidebarSection>
  );
}

/**
 * The chat-history panel: Pinned first, then conversations bucketed by when
 * they were last updated (Today / Last 7 days / Older). Empty groups render
 * nothing, so the list only ever shows structure that has content in it; the
 * "no chats at all" case gets a single hint instead.
 *
 * The server already sorts (pinned first, then most recently updated), so
 * bucketing preserves that order within each group.
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
  /** When non-empty, show a flat list of title matches instead of groups. */
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
  // first), no groups -- these are results, not organization.
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

  if (conversations.length === 0) {
    return (
      <div className="px-2 py-2 text-[0.78rem] text-faint leading-relaxed">
        No conversations yet. Start one with <span className="font-medium text-ink">New chat</span>.
      </div>
    );
  }

  const buckets = bucketConversations(conversations);

  return (
    <div>
      {GROUP_ORDER.filter((id) => buckets[id].length > 0).map((id) => (
        <Group key={id} id={id} items={buckets[id]} activeId={activeId} actions={actions} />
      ))}
    </div>
  );
}
