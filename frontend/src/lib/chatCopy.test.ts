import { describe, expect, it } from "vitest";
import { CHAT_PLACEHOLDER, NEW_CONVERSATION, drillPlaceholder } from "./chatCopy";

describe("CHAT_PLACEHOLDER", () => {
  it("has a non-empty, distinct string for each language", () => {
    expect(CHAT_PLACEHOLDER.en.length).toBeGreaterThan(0);
    expect(CHAT_PLACEHOLDER.he.length).toBeGreaterThan(0);
    expect(CHAT_PLACEHOLDER.en).not.toBe(CHAT_PLACEHOLDER.he);
  });
});

describe("NEW_CONVERSATION", () => {
  it("has a non-empty, distinct string for each language", () => {
    expect(NEW_CONVERSATION.en).toBe("New conversation");
    expect(NEW_CONVERSATION.he.length).toBeGreaterThan(0);
    expect(NEW_CONVERSATION.en).not.toBe(NEW_CONVERSATION.he);
  });
});

describe("drillPlaceholder", () => {
  it("interpolates the short title in both languages", () => {
    expect(drillPlaceholder("en", "Revenue by Month")).toContain("Revenue by Month");
    expect(drillPlaceholder("he", "Revenue by Month")).toContain("Revenue by Month");
  });

  it("only the Hebrew variant differs by language", () => {
    expect(drillPlaceholder("en", "X")).not.toBe(drillPlaceholder("he", "X"));
  });
});
