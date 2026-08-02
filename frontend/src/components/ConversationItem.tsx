import { useEffect, useRef, useState } from "react";
import {
  MoreHorizontal,
  MessageSquare,
  Pin,
  PinOff,
  Archive,
  ArchiveRestore,
  Trash2,
  Pencil,
  RefreshCw,
} from "lucide-react";
import type { ConversationSummary } from "../lib/api";
import { usePopoverMenu } from "../hooks/usePopoverMenu";
import { dirOf } from "../lib/rtl";
import { useT } from "../locales";
import { PopoverMenu } from "./PopoverMenu";
import { ThreadBadge } from "./ThreadBadge";

// Matches the menu's own `w-44` (11rem). A rough height estimate (rather than
// measuring the real rendered menu, which would need a two-pass render) is
// enough to decide "flip up or not" -- it only needs to be in the right
// ballpark, not pixel-exact, since the menu isn't full-bleed against the
// viewport edge either way. Bumped slightly for the extra Rerun item
// (rerun_conversation_prompt.md).
const MENU_WIDTH = 176;
const MENU_EST_HEIGHT = 230;

export interface ConversationActions {
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onDelete: (id: string) => void;
  /** Opens a brand-NEW conversation asking the source's first question fresh
   * (new SQL, current data/semantic model) -- NOT retry-in-place, and NOT the
   * whole turn sequence (MVP scope is the first question only, since it's
   * what defines the chat; follow-ups often depend on earlier answers and
   * would drift). The source conversation and its drill threads are never
   * touched. (rerun_conversation_prompt.md) */
  onRerun: (id: string) => void;
}

/**
 * One conversation row in the sidebar: a leading icon (pin for pinned chats,
 * chat bubble otherwise), title (truncated, full title on hover), active/
 * pinned state, and an always-visible ⋯ menu. Every menu control stops
 * propagation, so acting on a chat never also selects it.
 *
 * A pinned row gets the same pale accent as the active row (so "this is
 * pinned" reads at a glance without opening it); the active row additionally
 * gets bold/darker text so the two are still distinguishable when they
 * differ.
 *
 * Title alignment is intentionally PHYSICAL (`text-left`, not the logical
 * `text-start` used elsewhere in the app): the redesign wants every title --
 * Hebrew or English -- to read like ChatGPT's sidebar, always left-aligned,
 * with the kebab and accent bar in the same physical spot regardless of the
 * title's language. `dir` is still set from the title's own language (via
 * `dirOf`, not `dir="auto"`) so Hebrew characters and punctuation still order
 * correctly -- only the block's alignment is fixed.
 */
export function ConversationItem({
  conversation,
  active,
  actions,
}: {
  conversation: ConversationSummary;
  active: boolean;
  actions: ConversationActions;
}) {
  const { id, title, pinned, archived, drill_count, message_count } = conversation;
  const t = useT();
  // Hidden for a broken/empty source conversation -- there is no first
  // question to rerun (rerun_conversation_prompt.md edge case).
  const canRerun = message_count > 0;
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  const { open: menuOpen, close: closeMenuPos, toggle, triggerRef, menuRef, pos: menuPos } =
    usePopoverMenu<HTMLButtonElement>({ width: MENU_WIDTH, estHeight: MENU_EST_HEIGHT });

  const closeMenu = () => {
    closeMenuPos();
    setConfirmingDelete(false);
  };

  const toggleMenu = (e: React.MouseEvent) => {
    setConfirmingDelete(false);
    toggle(e);
  };

  // Focus + select the field when rename begins.
  useEffect(() => {
    if (renaming) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [renaming]);

  const startRename = () => {
    setDraft(title);
    setRenaming(true);
    closeMenu();
  };

  const commitRename = () => {
    const next = draft.trim();
    if (next && next !== title) actions.onRename(id, next);
    setRenaming(false);
  };

  if (renaming) {
    return (
      <div className="px-1 py-0.5">
        <input
          ref={inputRef}
          value={draft}
          dir="auto"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            else if (e.key === "Escape") setRenaming(false);
          }}
          onBlur={commitRename}
          className="w-full rounded-lg border border-primary bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none"
        />
      </div>
    );
  }

  const highlighted = active || pinned;

  return (
    <div className="relative sema-copy-host">
      <button
        type="button"
        onClick={() => actions.onOpen(id)}
        title={title}
        aria-label={drill_count > 0 ? `${title}, ${t.sidebar.drillFollowUps(drill_count)}` : undefined}
        className={`w-full h-10 text-left rounded-lg border-l-2 pl-2.5 pr-8 text-[0.82rem] transition flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
          highlighted
            ? "border-primary bg-primary/10 hover:bg-primary/15"
            : "border-transparent text-ink hover:bg-surfaceAlt"
        } ${active ? "text-primary-dark font-medium" : highlighted ? "text-ink" : ""}`}
      >
        {pinned ? (
          <Pin size={14} className="shrink-0 text-primary" aria-hidden />
        ) : (
          <MessageSquare size={14} className="shrink-0 text-faint" aria-hidden />
        )}
        <span className="truncate" dir={dirOf(title)}>
          {title}
        </span>
        {/* Total drill-down follow-ups across every thread on this
            conversation (sidebar_improvements_prompt.md item 3) -- shrink-0
            so it never itself wraps/shrinks; the title's own truncate always
            gives way first. Reuses ThreadBadge (the same pill already used
            for a widget's own follow-up count) for visual consistency. This
            IS app chrome (a sidebar row), not answer content, so it follows
            the org language via the locale files like the rest of the
            sidebar (i18n_language_files_prompt.md) -- unlike followUpsLabel
            (lib/format.ts), which labels widgets INSIDE an agent's answer
            and stays with the answer's own question-language, untouched. */}
        {drill_count > 0 && (
          <span title={t.sidebar.drillFollowUps(drill_count)} className="shrink-0">
            <ThreadBadge count={drill_count} />
          </span>
        )}
      </button>

      {/* Kebab trigger, always visible (not hover-reveal) so every row's
          actions are equally reachable at a glance. Position is physical
          (right-1, not end-1) so it stays in the same spot regardless of the
          row's title language. */}
      <button
        ref={triggerRef}
        type="button"
        aria-label={t.menus.conversation.actionsLabel}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onClick={toggleMenu}
        className="absolute right-1 top-1/2 -translate-y-1/2 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-line hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <MoreHorizontal size={15} />
      </button>

      {menuOpen && (
        <PopoverMenu pos={menuPos} menuRef={menuRef} className="rounded-xl p-1">
          {confirmingDelete ? (
            <div className="p-1.5">
              <div className="text-[0.72rem] text-muted mb-1.5 px-1">
                {t.menus.conversation.deleteConfirmPrompt}
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => {
                    actions.onDelete(id);
                    closeMenu();
                  }}
                  className="flex-1 rounded-lg bg-critical-fg text-white text-xs font-medium py-1.5 hover:brightness-95 transition"
                >
                  {t.menus.conversation.delete}
                </button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  className="flex-1 rounded-lg border border-line text-ink text-xs py-1.5 hover:bg-surfaceAlt transition"
                >
                  {t.common.cancel}
                </button>
              </div>
            </div>
          ) : archived ? (
            <>
              {canRerun && (
                <MenuItem
                  icon={<RefreshCw size={14} />}
                  label={t.menus.conversation.rerun}
                  onClick={() => {
                    actions.onRerun(id);
                    closeMenu();
                  }}
                />
              )}
              <MenuItem
                icon={<ArchiveRestore size={14} />}
                label={t.menus.conversation.unarchive}
                onClick={() => {
                  actions.onUnarchive(id);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Trash2 size={14} />}
                label={t.menus.conversation.delete}
                danger
                onClick={() => setConfirmingDelete(true)}
              />
            </>
          ) : (
            <>
              <MenuItem icon={<Pencil size={14} />} label={t.menus.conversation.rename} onClick={startRename} />
              {canRerun && (
                <MenuItem
                  icon={<RefreshCw size={14} />}
                  label={t.menus.conversation.rerun}
                  onClick={() => {
                    actions.onRerun(id);
                    closeMenu();
                  }}
                />
              )}
              <MenuItem
                icon={pinned ? <PinOff size={14} /> : <Pin size={14} />}
                label={pinned ? t.menus.conversation.unpinChat : t.menus.conversation.pinChat}
                onClick={() => {
                  actions.onTogglePin(id, !pinned);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Archive size={14} />}
                label={t.menus.conversation.archive}
                onClick={() => {
                  actions.onArchive(id);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Trash2 size={14} />}
                label={t.menus.conversation.delete}
                danger
                onClick={() => setConfirmingDelete(true)}
              />
            </>
          )}
        </PopoverMenu>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={`w-full text-start flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.82rem] transition hover:bg-surfaceAlt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
        danger ? "text-critical-fg" : "text-ink"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
