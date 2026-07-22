import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatTurn } from "../lib/conversations";

/** How close to the bottom still counts as "following along". */
const ATTACH_PX = 80;
/** Breathing room above an answer card once it's aligned to the top. */
const ANSWER_TOP_OFFSET = 8;

/**
 * Chat scroll behaviour, shared by the main transcript and the drill panel.
 *
 * Two distinct moments, deliberately handled differently:
 *
 *  - WHILE WAITING, the view follows the bottom so progress stays visible --
 *    but only while the user is attached. The previous implementation scrolled
 *    to the bottom on every turns/loading change, which yanked anyone who had
 *    scrolled up to re-read something.
 *
 *  - WHEN THE ANSWER LANDS, the view jumps to the TOP of that answer instead of
 *    its end. Following the bottom here would drop the reader at the last line
 *    of a long analysis and make them scroll up to start reading.
 *
 * State-driven throughout: no timers, so nothing fires against a layout that
 * has already changed.
 */
export function useChatScroll(turns: ChatTurn[]) {
  const scrollRef = useRef<HTMLDivElement>(null);
  /** The last turn's answer card, for top-aligning a freshly arrived answer. */
  const lastAnswerRef = useRef<HTMLDivElement>(null);

  // Whether the user is following the bottom. Not state: reading it inside the
  // effects must never be a render behind, or one stale value re-hijacks the
  // scroll position the user just chose.
  const attachedRef = useRef(true);
  const [detached, setDetached] = useState(false);

  const isAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= ATTACH_PX;
  }, []);

  const setAttached = useCallback((next: boolean) => {
    attachedRef.current = next;
    setDetached(!next);
  }, []);

  const onScroll = useCallback(() => setAttached(isAtBottom()), [isAtBottom, setAttached]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  /** "Back to latest": jump to the newest content and resume following it. */
  const scrollToLatest = useCallback(() => {
    setAttached(true);
    scrollToBottom();
  }, [scrollToBottom, setAttached]);

  /** Call when the user sends or retries -- an explicit action always means
   * "show me what happens next", regardless of where they had scrolled. */
  const reattach = useCallback(() => setAttached(true), [setAttached]);

  const last = turns[turns.length - 1];
  const pending = turns.length > 0 && !last?.response && !last?.stopped;
  const answered = !!last?.response;

  // Tracks the pending->answered TRANSITION rather than a key built from
  // turns.length: retry removes the failed turn and re-adds it, so a
  // length-based key returns to a value already seen and the alignment below
  // would silently never fire for a retried answer.
  const wasPending = useRef(pending);

  // Follow progress while waiting -- only for an attached reader.
  const progressLength = last?.progress?.length ?? 0;
  useEffect(() => {
    if (!pending || !attachedRef.current) return;
    scrollToBottom();
  }, [pending, progressLength, turns.length, scrollToBottom]);

  // An answer arrived: show it from its beginning.
  useEffect(() => {
    const justAnswered = wasPending.current && !pending && answered;
    wasPending.current = pending;
    if (!justAnswered) return;

    // The one case where we leave the viewport alone: the reader deliberately
    // scrolled away while waiting, so they are reading something else and a
    // jump would steal the page out from under them.
    if (!attachedRef.current) return;

    const el = lastAnswerRef.current;
    const container = scrollRef.current;
    if (!el || !container) {
      scrollToBottom();
      return;
    }
    // Position the card's top just below the container's top edge. Computed
    // against the container rather than scrollIntoView's own alignment so the
    // small offset is honoured inside a scrollable panel.
    const top = container.scrollTop + el.getBoundingClientRect().top
      - container.getBoundingClientRect().top - ANSWER_TOP_OFFSET;
    container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    // Reading from the top means we are no longer at the bottom; treat that as
    // detached so "Back to latest" is offered rather than silently re-following.
    setAttached(false);
  }, [pending, answered, scrollToBottom, setAttached]);

  return {
    scrollRef,
    lastAnswerRef,
    onScroll,
    /** Show the "Back to latest" button. */
    showScrollToLatest: detached && turns.length > 0,
    scrollToLatest,
    reattach,
  };
}
