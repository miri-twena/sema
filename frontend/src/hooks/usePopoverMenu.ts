import { useCallback, useEffect, useRef, useState } from "react";
import { useDismissRefs } from "./useDismiss";
import { useFocusTrap } from "./useFocusTrap";

export interface PopoverPosition {
  top: number;
  left: number;
  width: number;
}

interface UsePopoverMenuOptions {
  /** Fixed pixel width, or "trigger" to match the trigger element's own
   * rendered width (e.g. a listbox that should span its trigger row). */
  width: number | "trigger";
  /** Estimated menu height (a rough ballpark, not pixel-exact) used to decide
   * whether an "auto" menu should flip upward, and to position an "above"
   * menu above its trigger. */
  estHeight: number;
  /** "auto" (default) flips up only when there's not enough room below;
   * "above"/"below" force a side regardless of available space -- used by
   * the sidebar-bottom menus, which always open upward. */
  placement?: "auto" | "above" | "below";
  /** Physical anchor edge: "end" aligns the menu's right edge with the
   * trigger's right edge (default, most kebab menus); "start" aligns left
   * edges (used for full-width listboxes). Physical, not logical -- these
   * menus are positioned in raw viewport pixels regardless of RTL/LTR. */
  align?: "start" | "end";
  margin?: number;
}

/**
 * Shared state/behavior for every popover and kebab menu in the app: portal-
 * ready viewport position (computed from the trigger's rect, with optional
 * flip-up), outside-click/Escape dismiss across the trigger+portaled-menu
 * pair, Tab-cycling focus trap, and close-on-scroll (a portaled menu is
 * positioned in viewport coordinates, so it would visually detach from its
 * trigger if the list scrolled underneath it -- closing is simpler and more
 * robust than re-tracking position every scroll frame).
 *
 * Extracted from the sidebar conversation-menu fix (sidebar_improvements_
 * prompt.md) so every popover in the app shares one implementation instead
 * of re-deriving the same portal/position/dismiss/focus-trap logic per
 * component -- the root cause of the popover-clipping bug class this fixes
 * (popover_zorder_sweep_prompt.md).
 *
 * Pair with <PopoverMenu> (components/PopoverMenu.tsx) to render the portal.
 */
export function usePopoverMenu<T extends HTMLElement = HTMLButtonElement>(
  opts: UsePopoverMenuOptions,
) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<T>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<PopoverPosition | null>(null);
  const { width, estHeight, placement = "auto", align = "end", margin = 6 } = opts;

  const close = useCallback(() => setOpen(false), []);
  useDismissRefs(open, close, triggerRef, menuRef);
  useFocusTrap(menuRef, open);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => close();
    document.addEventListener("scroll", onScroll, true);
    return () => document.removeEventListener("scroll", onScroll, true);
  }, [open, close]);

  const computePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const resolvedWidth = width === "trigger" ? rect.width : width;
    const openUp =
      placement === "above" ||
      (placement === "auto" && window.innerHeight - rect.bottom < estHeight && rect.top > estHeight);
    const top = openUp
      ? Math.max(margin, rect.top - estHeight - margin)
      : rect.bottom + margin;
    const left =
      align === "start" ? Math.max(margin, rect.left) : Math.max(margin, rect.right - resolvedWidth);
    setPos({ top, left, width: resolvedWidth });
  }, [align, estHeight, margin, placement, width]);

  const toggle = useCallback(
    (e?: { stopPropagation?: () => void }) => {
      e?.stopPropagation?.();
      setOpen((wasOpen) => {
        if (!wasOpen) computePosition();
        return !wasOpen;
      });
    },
    [computePosition],
  );

  /** Opens (or keeps open, repositioned) as a side effect of some OTHER
   * action -- e.g. a "thumbs down" click that reveals a comment box -- rather
   * than a direct trigger-click toggle. */
  const openNow = useCallback(() => {
    computePosition();
    setOpen(true);
  }, [computePosition]);

  return { open, close, toggle, openNow, triggerRef, menuRef, pos };
}
