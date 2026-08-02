import { useEffect, useState } from "react";
import type { ConversationSummary } from "../lib/api";
import { bucketConversations, filterByTitle, previewSplit } from "../lib/conversations";
import { useT } from "../locales";
import { ConversationItem, type ConversationActions } from "./ConversationItem";
import { SidebarSection } from "./SidebarSection";

const COLLAPSE_KEY = "sema:convSections"; // { [groupId]: bool } = open state
// "Older" defaults open (matches prior behavior); a fresh "Archived" toggle
// view defaults closed since it's rarely the reason someone opens the sidebar.
const DEFAULT_OPEN: Record<string, boolean> = { older: true };

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "{}");
  } catch {
    return {};
  }
}

/** A flat, unbucketed list of rows -- shared by search results and the
 * sidebar's "Archived" toggle view. */
export function Rows({
  items,
  activeId,
  actions,
}: {
  items: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {items.map((c) => (
        <ConversationItem key={c.id} conversation={c} active={c.id === activeId} actions={actions} />
      ))}
    </div>
  );
}

/** A collapsible accordion group (currently just "Older"), with its open
 * state persisted the same way the old flat groups were. */
function CollapsibleGroup({
  id,
  items,
  activeId,
  actions,
}: {
  id: "older";
  items: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
}) {
  const t = useT();
  const [open, setOpen] = useState<boolean>(() => loadCollapsed()[id] ?? DEFAULT_OPEN[id] ?? true);

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
      title={t.sidebar.groups[id]}
      count={items.length}
      open={open}
      onToggle={() => setOpen((o) => !o)}
    >
      <Rows items={items} activeId={activeId} actions={actions} />
    </SidebarSection>
  );
}

/** "Previous 7 days": always visible (not an accordion), but capped to
 * PREVIEW_LIMIT rows with a "Show all N" expander -- distinct from the
 * open/closed accordion pattern above, since collapsing it away entirely
 * isn't the point; hiding the tail of a long list is. */
function PreviewGroup({
  items,
  activeId,
  actions,
}: {
  items: ConversationSummary[];
  activeId: string | null;
  actions: ConversationActions;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const { shown, remaining } = previewSplit(items, expanded);

  return (
    <SidebarSection
      title={t.sidebar.groups.week}
      count={items.length}
      open
      onToggle={() => {}}
      collapsible={false}
    >
      <Rows items={shown} activeId={activeId} actions={actions} />
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="w-full text-left px-2.5 py-1.5 text-[0.78rem] font-medium text-primary hover:text-primary-dark transition"
        >
          {t.sidebar.showAll(items.length)}
        </button>
      )}
    </SidebarSection>
  );
}

/**
 * The chat-history panel: Pinned (always fully visible) → Recent → Today
 * (always fully visible) → Previous 7 days (capped, expandable) → Older
 * (collapsible). Empty groups render nothing, so the list only ever shows
 * structure that has content in it; the "no chats at all" case gets a single
 * hint instead.
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
  const t = useT();
  if (error) {
    return <div className="px-1 py-2 text-[0.78rem] text-muted">{t.sidebar.couldNotLoadHistory}</div>;
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
  if (search.trim()) {
    const matches = filterByTitle(conversations, search);
    if (matches.length === 0) {
      return (
        <div className="px-2 py-2 text-[0.78rem] text-muted leading-relaxed">
          {t.sidebar.noChatsMatch(search.trim())}
        </div>
      );
    }
    return <Rows items={matches} activeId={activeId} actions={actions} />;
  }

  if (conversations.length === 0) {
    return (
      <div className="px-2 py-2 text-[0.78rem] text-faint leading-relaxed">
        {t.sidebar.noConversationsYetPrefix}{" "}
        <span className="font-medium text-ink" dir="auto">
          {t.sidebar.newConversation}
        </span>
        .
      </div>
    );
  }

  const buckets = bucketConversations(conversations);
  const hasRecent = buckets.today.length > 0 || buckets.week.length > 0 || buckets.older.length > 0;

  return (
    <div>
      {buckets.pinned.length > 0 && (
        <SidebarSection
          title={t.sidebar.groups.pinned}
          count={buckets.pinned.length}
          open
          onToggle={() => {}}
          collapsible={false}
        >
          <Rows items={buckets.pinned} activeId={activeId} actions={actions} />
        </SidebarSection>
      )}

      {hasRecent && (
        <div className="px-1 pb-1 text-[0.72rem] font-semibold uppercase tracking-wide text-faint">
          {t.sidebar.groups.recent}
        </div>
      )}

      {buckets.today.length > 0 && (
        <SidebarSection
          title={t.sidebar.groups.today}
          count={buckets.today.length}
          open
          onToggle={() => {}}
          collapsible={false}
        >
          <Rows items={buckets.today} activeId={activeId} actions={actions} />
        </SidebarSection>
      )}

      {buckets.week.length > 0 && (
        <PreviewGroup items={buckets.week} activeId={activeId} actions={actions} />
      )}

      {buckets.older.length > 0 && (
        <CollapsibleGroup id="older" items={buckets.older} activeId={activeId} actions={actions} />
      )}
    </div>
  );
}
