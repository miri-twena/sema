import { useEffect, useState } from "react";
import { prefersReducedMotion } from "../lib/chart";

const CYCLE_MS = 3000;
const MAX_ITEMS = 4;

/** Pure decision logic, extracted for unit testing without a hook-rendering
 * harness (this codebase has none -- see loginReducer in useLoginFlow.ts for
 * the same pattern). Never invented copy: the pool is always a slice of
 * real suggested questions, so whatever shows is something the user could
 * actually ask right now. */
export function limitPool(questions: string[], max: number = MAX_ITEMS): string[] {
  return questions.slice(0, max);
}

export function nextIndex(index: number, poolLength: number): number {
  if (poolLength <= 0) return 0;
  return (index + 1) % poolLength;
}

/** Whether the interval should be running at all. Cycling never starts (not
 * "runs faster") under prefers-reduced-motion -- a static fallback to
 * whatever's at the current index, per home_ask_bar_top_prompt.md item 3. */
export function shouldCycle(stopped: boolean, poolLength: number, reducedMotion: boolean): boolean {
  return !stopped && poolLength > 1 && !reducedMotion;
}

/**
 * Cycles the home screen's hero ask input through a handful of real
 * suggested questions. Stops PERMANENTLY once the caller reports the input
 * was focused (see `stop()`) -- once someone's about to type their own
 * question, cycling the placeholder under it would be distracting, and
 * there is no legitimate reason to resume it later in the same visit.
 */
export function useCyclingPlaceholder(questions: string[]): { text: string | undefined; stop: () => void } {
  const pool = limitPool(questions);
  const key = pool.join(" "); // content identity, so a client switch restarts the cycle
  const [index, setIndex] = useState(0);
  const [stopped, setStopped] = useState(false);

  useEffect(() => setIndex(0), [key]);

  useEffect(() => {
    if (!shouldCycle(stopped, pool.length, prefersReducedMotion())) return;
    const id = setInterval(() => setIndex((i) => nextIndex(i, pool.length)), CYCLE_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `pool` is a fresh array each render; `key`/`pool.length` capture everything that should restart the interval
  }, [stopped, key, pool.length]);

  return { text: pool[index], stop: () => setStopped(true) };
}
