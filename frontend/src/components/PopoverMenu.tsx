import { createPortal } from "react-dom";
import type { ReactNode, RefObject } from "react";
import type { PopoverPosition } from "../hooks/usePopoverMenu";

/**
 * Portals popover/kebab-menu content to document.body at a pre-computed
 * viewport position (from usePopoverMenu), so it's never clipped by a
 * scrolling list, a later sibling row, or any ancestor's overflow/stacking
 * context -- the bug class fixed once for the sidebar (sidebar_improvements_
 * prompt.md) and now shared by every popover in the app
 * (popover_zorder_sweep_prompt.md).
 */
export function PopoverMenu({
  pos,
  menuRef,
  role = "menu",
  ariaLabel,
  dir,
  className = "",
  children,
}: {
  pos: PopoverPosition | null;
  menuRef: RefObject<HTMLDivElement | null>;
  role?: "menu" | "dialog" | "listbox";
  ariaLabel?: string;
  /** Overrides the portaled menu's own text direction -- for content (like a
   * feedback comment box) that should follow a language other than the
   * trigger row's. Omit to inherit normally. */
  dir?: "ltr" | "rtl";
  className?: string;
  children: ReactNode;
}) {
  if (!pos) return null;
  return createPortal(
    <div
      ref={menuRef}
      role={role}
      aria-label={ariaLabel}
      dir={dir}
      style={{ position: "fixed", top: pos.top, left: pos.left, width: pos.width }}
      className={`z-50 border border-line bg-surface shadow-pop ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>,
    document.body,
  );
}
