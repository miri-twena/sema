import { useEffect, useRef, useState } from "react";
import { MoreHorizontal, Pin, PinOff, Archive, Trash2, Pencil } from "lucide-react";
import type { ConversationSummary } from "../lib/api";
import { useDismiss } from "../hooks/useDismiss";

export interface ConversationActions {
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}

/**
 * One conversation row in the sidebar: title (truncated, full title on hover),
 * active state, and a ⋯ menu (rename / pin / archive / delete) revealed on
 * hover or keyboard focus. Every menu control stops propagation, so acting on
 * a chat never also selects it.
 *
 * Deliberately flat: the row carries no background of its own, so the ONLY
 * accent-coloured row in the sidebar is the active conversation.
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
  const { id, title, pinned } = conversation;
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

  return (
    <div ref={rowRef} className="relative sema-copy-host">
      <button
        type="button"
        onClick={() => actions.onOpen(id)}
        title={title}
        className={`w-full text-start rounded-lg ps-3 pe-8 py-2 text-[0.82rem] leading-snug transition flex items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
          active ? "bg-primary/10 text-primary-dark font-medium" : "text-ink hover:bg-surfaceAlt"
        }`}
      >
        <span className="truncate" dir="auto">
          {title}
        </span>
      </button>

      {/* Kebab trigger. `sema-copy-affordance` is the shared hover/focus-reveal
          rule (and stays visible on touch, where there is no hover). It is
          dropped entirely while the menu is open so the trigger can't fade out
          from under an open menu. */}
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
        className={`absolute end-1 top-1/2 -translate-y-1/2 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-line hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 transition ${
          menuOpen ? "" : "sema-copy-affordance"
        }`}
      >
        <MoreHorizontal size={15} />
      </button>

      {menuOpen && (
        <div
          role="menu"
          className="absolute end-1 top-[calc(100%-2px)] z-30 w-44 rounded-xl border border-line bg-surface shadow-pop p-1"
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
