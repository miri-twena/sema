import { describe, expect, it } from "vitest";
import { dirOf, isRtl } from "./rtl";

describe("rtl detection", () => {
  it("detects Hebrew", () => {
    expect(isRtl("למה ההכנסות ירדו במרץ?")).toBe(true);
    expect(dirOf("למה ההכנסות ירדו במרץ?")).toBe("rtl");
  });

  it("treats English as ltr", () => {
    expect(isRtl("Why did revenue drop in March?")).toBe(false);
    expect(dirOf("Why did revenue drop in March?")).toBe("ltr");
  });

  // A turn's direction is decided ONCE from the question's language, so a
  // question that merely contains Latin characters or numbers still reads RTL.
  it("stays rtl when Hebrew is mixed with Latin text and numbers", () => {
    expect(dirOf("מה היו ההכנסות ב-Q2 2026?")).toBe("rtl");
    expect(dirOf("AOV ירד ב-19.8%")).toBe("rtl");
  });

  it("defaults to ltr for text with no letters at all", () => {
    expect(dirOf("2026-06-30")).toBe("ltr");
    expect(dirOf("")).toBe("ltr");
  });
});
