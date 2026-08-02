import { useEffect, useRef, type RefObject } from "react";

/**
 * Close-on-outside-click + Escape for popovers and dropdowns. Attach the
 * returned ref to the element that should COUNT as "inside" (trigger and
 * popover together, so clicking the trigger to close doesn't reopen it).
 *
 * Listens on mousedown rather than click: a click fires after the pointer is
 * released, which lets a menu item's own handler run against a stale layout if
 * the outside click also moved something.
 */
export function useDismiss<T extends HTMLElement = HTMLDivElement>(
  active: boolean,
  onClose: () => void,
) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!active) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, onClose]);
  return ref;
}

/**
 * Same close-on-outside-click + Escape as useDismiss, but "inside" spans TWO
 * separate elements -- for a trigger + its dropdown when the dropdown is
 * rendered in a portal (document.body), so it's no longer a DOM descendant of
 * the trigger and a single-ref containment check would treat every click
 * inside the (portaled) menu itself as "outside." Both refs come from
 * `useRef` in the caller, so they're stable identities across renders --
 * safe to depend on directly, unlike a freshly-built array literal would be.
 */
export function useDismissRefs(
  active: boolean,
  onClose: () => void,
  ref1: RefObject<HTMLElement | null>,
  ref2: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!active) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const inside = (ref1.current?.contains(target) ?? false) || (ref2.current?.contains(target) ?? false);
      if (!inside) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, onClose, ref1, ref2]);
}
