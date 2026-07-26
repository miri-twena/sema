import { describe, expect, it } from "vitest";
import type { ChatResponse } from "./api";
import { isAnswerable, pickFollowUp } from "./questions";

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
