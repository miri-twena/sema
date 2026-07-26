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
} from "lucide-react";
import type { ConversationSummary } from "../lib/api";
import { useDismiss } from "../hooks/useDismiss";
import { dirOf } from "../lib/rtl";

export interface ConversationActions {
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onDelete: (id: string) => void;
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
  const { id, title, pinned, archived } = conversation;
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  const closeMenu = () => {
    setMenuOpen(false);
    setConfirmingDelete(false);
  };

  const rowRef = useDismiss<HTMLDivElement>(menuOpen, closeMenu);

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
    <div ref={rowRef} className="relative sema-copy-host">
      <button
        type="button"
        onClick={() => actions.onOpen(id)}
        title={title}
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
      </button>

      {/* Kebab trigger, always visible (not hover-reveal) so every row's
          actions are equally reachable at a glance. Position is physical
          (right-1, not end-1) so it stays in the same spot regardless of the
          row's title language. */}
      <button
        type="button"
        aria-label="Conversation actions"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((o) => !o);
          setConfirmingDelete(false);
        }}
        className="absolute right-1 top-1/2 -translate-y-1/2 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-line hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition"
      >
        <MoreHorizontal size={15} />
      </button>

      {menuOpen && (
        <div
          role="menu"
          className="absolute right-1 top-[calc(100%-2px)] z-30 w-44 rounded-xl border border-line bg-surface shadow-pop p-1"
          onClick={(e) => e.stopPropagation()}
        >
          {confirmingDelete ? (
            <div className="p-1.5">
              <div className="text-[0.72rem] text-muted mb-1.5 px-1">Delete this chat?</div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => {
                    actions.onDelete(id);
                    closeMenu();
                  }}
                  className="flex-1 rounded-lg bg-critical-fg text-white text-xs font-medium py-1.5 hover:brightness-95 transition"
                >
                  Delete
                </button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  className="flex-1 rounded-lg border border-line text-ink text-xs py-1.5 hover:bg-surfaceAlt transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : archived ? (
            <>
              <MenuItem
                icon={<ArchiveRestore size={14} />}
                label="Unarchive"
                onClick={() => {
                  actions.onUnarchive(id);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Trash2 size={14} />}
                label="Delete"
                danger
                onClick={() => setConfirmingDelete(true)}
              />
            </>
          ) : (
            <>
              <MenuItem icon={<Pencil size={14} />} label="Rename" onClick={startRename} />
              <MenuItem
                icon={pinned ? <PinOff size={14} /> : <Pin size={14} />}
                label={pinned ? "Unpin chat" : "Pin chat"}
                onClick={() => {
                  actions.onTogglePin(id, !pinned);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Archive size={14} />}
                label="Archive"
                onClick={() => {
                  actions.onArchive(id);
                  closeMenu();
                }}
              />
              <MenuItem
                icon={<Trash2 size={14} />}
                label="Delete"
                danger
                onClick={() => setConfirmingDelete(true)}
              />
            </>
          )}
        </div>
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
