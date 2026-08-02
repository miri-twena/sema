import { describe, expect, it } from "vitest";
import { limitPool, nextIndex, shouldCycle } from "./useCyclingPlaceholder";

describe("limitPool", () => {
  it("caps at 4 items by default", () => {
    expect(limitPool(["a", "b", "c", "d", "e", "f"])).toEqual(["a", "b", "c", "d"]);
  });

  it("passes a shorter list through unchanged", () => {
    expect(limitPool(["a", "b"])).toEqual(["a", "b"]);
  });

  it("handles an empty list", () => {
    expect(limitPool([])).toEqual([]);
  });
});

describe("nextIndex", () => {
  it("advances by one", () => {
    expect(nextIndex(0, 4)).toBe(1);
    expect(nextIndex(1, 4)).toBe(2);
  });

  it("wraps back to zero at the end of the pool", () => {
    expect(nextIndex(3, 4)).toBe(0);
  });

  it("never divides by zero for an empty pool", () => {
    expect(nextIndex(0, 0)).toBe(0);
  });
});

describe("shouldCycle", () => {
  it("cycles with 2+ questions, not stopped, motion allowed", () => {
    expect(shouldCycle(false, 3, false)).toBe(true);
  });

  it("stops permanently once the caller reports stopped", () => {
    expect(shouldCycle(true, 3, false)).toBe(false);
  });

  it("never cycles with 0 or 1 question -- nothing to cycle to", () => {
    expect(shouldCycle(false, 0, false)).toBe(false);
    expect(shouldCycle(false, 1, false)).toBe(false);
  });

  it("respects prefers-reduced-motion -- a static fallback, not a faster cycle", () => {
    expect(shouldCycle(false, 3, true)).toBe(false);
  });
});
