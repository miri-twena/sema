import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true",
  );
}

/**
 * Confines Tab/Shift+Tab to the elements inside `ref` while `active`, and
 * autofocuses the first focusable element on activation -- what a modal/
 * drawer needs to be keyboard-accessible (nothing else in the codebase traps
 * focus yet; `useDismiss` handles Escape + outside-click but not Tab cycling).
 *
 * Takes an EXISTING ref rather than creating its own, so callers that also
 * need `useDismiss` on the same container (the usual case) attach one ref to
 * both hooks instead of merging two refs onto one element.
 *
 * Restores focus to whatever was focused before opening, once `active` goes
 * back to false -- so closing a drawer returns the keyboard user to the
 * control that opened it (e.g. the row that launched it) instead of stranding
 * focus on a now-hidden element or resetting it to the document body.
 */
export function useFocusTrap<T extends HTMLElement>(ref: RefObject<T | null>, active: boolean) {
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const container = ref.current;
    if (!container) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    focusableElements(container)[0]?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusableElements(container);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", onKeyDown);
    return () => {
      container.removeEventListener("keydown", onKeyDown);
      previouslyFocused.current?.focus();
    };
    // `ref` is a stable object identity from useRef in the caller.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}
