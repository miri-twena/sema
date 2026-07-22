import { describe, expect, it } from "vitest";
import type { ChatResponse, PopularQuestion } from "./api";
import { MAX_OTHERS, isAnswerable, pickFollowUp, pickOthers } from "./questions";

function resp(follow_up_questions: string[]): ChatResponse {
  return {
    answer: "",
    kpis: [],
    chart: null,
    table: null,
    actions: [],
    follow_up_questions,
    sql_used: null,
    confidence: null,
    evidence: null,
    status: "ok",
    error: null,
  };
}

const popular = (n: number): PopularQuestion[] =>
  Array.from({ length: n }, (_, i) => ({ question: `q${i + 1}`, times_asked: n - i }));

describe("pickFollowUp", () => {
  it("offers the first answerable question", () => {
    expect(pickFollowUp(resp(["Which channel converts best?"]))).toBe(
      "Which channel converts best?",
    );
  });

  // Correctness rule, not preference: suggesting an action SEMA cannot perform
  // got the user "I can't do that" when they accepted it.
  it("drops execution actions and falls through to the next candidate", () => {
    expect(pickFollowUp(resp(["Send a win-back email", "Why did AOV fall?"]))).toBe(
      "Why did AOV fall?",
    );
  });

  it("returns null rather than suggesting something un-answerable", () => {
    expect(pickFollowUp(resp(["Launch a retargeting campaign"]))).toBeNull();
    expect(pickFollowUp(resp([]))).toBeNull();
  });

  it("applies the same rule in Hebrew", () => {
    expect(isAnswerable("שלח אימייל ללקוחות")).toBe(false);
    expect(isAnswerable("למה ההכנסות ירדו במרץ?")).toBe(true);
    expect(pickFollowUp(resp(["שלח קופון ללקוחות VIP", "למה ה-AOV ירד?"]))).toBe("למה ה-AOV ירד?");
  });

  it("ignores blank entries", () => {
    expect(pickFollowUp(resp(["   ", "Real question?"]))).toBe("Real question?");
  });
});

describe("pickOthers", () => {
  it("never repeats the question that was just asked", () => {
    const picked = pickOthers(popular(4), "q2", 0);
    expect(picked).not.toContain("q2");
  });

  it("matches the asked question regardless of case and padding", () => {
    expect(pickOthers(popular(4), "  Q2  ", 0)).not.toContain("q2");
  });

  // REGRESSION: this shipped. The original used a module-level "already shown"
  // Set, which silently failed -- every card in a restored transcript mounts in
  // the same render pass, so all of them read the Set while it was still empty
  // and rendered identical chips.
  it("gives consecutive answers different chips", () => {
    const p = popular(6);
    expect(pickOthers(p, "", 0)).not.toEqual(pickOthers(p, "", 1));
  });

  it("wraps around once the list is exhausted instead of running dry", () => {
    const p = popular(6);
    expect(pickOthers(p, "", 2)).toEqual(pickOthers(p, "", 0));
    expect(pickOthers(p, "", 2)).toHaveLength(MAX_OTHERS);
  });

  it("is deterministic for the same inputs", () => {
    const p = popular(6);
    expect(pickOthers(p, "q1", 3)).toEqual(pickOthers(p, "q1", 3));
  });

  it("shows at most MAX_OTHERS", () => {
    expect(pickOthers(popular(20), "", 0)).toHaveLength(MAX_OTHERS);
  });

  it("handles a list shorter than MAX_OTHERS without duplicating", () => {
    const picked = pickOthers(popular(2), "", 0);
    expect(picked).toHaveLength(2);
    expect(new Set(picked).size).toBe(2);
  });

  it("returns nothing when the only popular question is the one just asked", () => {
    expect(pickOthers(popular(1), "q1", 0)).toEqual([]);
  });

  it("returns nothing for an empty list", () => {
    expect(pickOthers([], "anything", 5)).toEqual([]);
  });
});
