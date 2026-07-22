import { useEffect, useRef } from "react";

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
