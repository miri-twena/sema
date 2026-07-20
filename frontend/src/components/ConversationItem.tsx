import { useEffect, useRef, useState } from "react";
import { MoreHorizontal, Pin, PinOff, Archive, Trash2, Pencil } from "lucide-react";
import type { ConversationSummary } from "../lib/api";

export interface ConversationActions {
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}

/**
 * One conversation row in the sidebar: title (truncated, full title on hover),
 * active state, and a hover ⋯ menu (rename / pin / archive / delete). Every
 * menu control stops propagation, so acting on a chat never also selects it.
 */
export function ConversationItem({
  conversation,
  active,
  actions,
  tint,
}: {
  conversation: ConversationSummary;
  active: boolean;
  actions: ConversationActions;
  /** Fixed category colour (background, text/border) applied when not active. */
  tint?: readonly [string, string];
}) {
  const { id, title, pinned } = conversation;
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(title);
  const rowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const closeMenu = () => {
    setMenuOpen(false);
    setConfirmingDelete(false);
  };

  // Close the menu on outside click / Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (rowRef.current && !rowRef.current.contains(e.target as Node)) closeMenu();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeMenu();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

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

  // Fixed category colour when not active; the active chat keeps the primary
  // highlight so selection never relies on the category tint alone.
  const tinted = tint && !active;
  const [bg, fg] = tint ?? ["", ""];

  return (
    <div ref={rowRef} className="relative group">
      <button
        type="button"
        onClick={() => actions.onOpen(id)}
        title={title}
        style={tinted ? { background: bg, color: fg, borderColor: `${fg}2e` } : undefined}
        className={`w-full text-start rounded-lg border pl-3 pr-8 py-2 text-[0.82rem] leading-snug transition flex items-center ${
          active
            ? "bg-primary/12 text-primary-dark font-medium border-transparent"
            : tinted
              ? "hover:brightness-[0.97]"
              : "text-ink border-transparent hover:bg-surfaceAlt"
        }`}
      >
        <span className="truncate" dir="auto">
          {title}
        </span>
      </button>

      {/* two-dot menu trigger -- visible on hover, or whenever its menu is open */}
      <button
        type="button"
        aria-label="Conversation actions"
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((o) => !o);
          setConfirmingDelete(false);
        }}
        className={`absolute end-1 top-1/2 -translate-y-1/2 w-6 h-6 rounded-md flex items-center justify-center text-muted hover:bg-line hover:text-ink transition ${
          menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        }`}
      >
        <MoreHorizontal size={15} />
      </button>

      {menuOpen && (
        <div
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
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.82rem] transition hover:bg-surfaceAlt ${
        danger ? "text-critical-fg" : "text-ink"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
