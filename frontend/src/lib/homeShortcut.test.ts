import { describe, expect, it } from "vitest";
import { shouldFocusAskInput, type SlashShortcutContext } from "./homeShortcut";

function ctx(over: Partial<SlashShortcutContext> = {}): SlashShortcutContext {
  return {
    key: "/",
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    modalOpen: false,
    activeElementTag: undefined,
    activeElementEditable: false,
    ...over,
  };
}

describe("shouldFocusAskInput", () => {
  it("focuses on a plain '/' with nothing else focused", () => {
    expect(shouldFocusAskInput(ctx())).toBe(true);
  });

  it("ignores any key other than '/'", () => {
    expect(shouldFocusAskInput(ctx({ key: "a" }))).toBe(false);
    expect(shouldFocusAskInput(ctx({ key: "Enter" }))).toBe(false);
  });

  it("ignores '/' with a modifier held (browser/editor shortcuts)", () => {
    expect(shouldFocusAskInput(ctx({ metaKey: true }))).toBe(false);
    expect(shouldFocusAskInput(ctx({ ctrlKey: true }))).toBe(false);
    expect(shouldFocusAskInput(ctx({ altKey: true }))).toBe(false);
  });

  it("ignores '/' while a modal/drawer/drill panel is open", () => {
    expect(shouldFocusAskInput(ctx({ modalOpen: true }))).toBe(false);
  });

  it("ignores '/' while focus is already in a text input, textarea, or select", () => {
    expect(shouldFocusAskInput(ctx({ activeElementTag: "INPUT" }))).toBe(false);
    expect(shouldFocusAskInput(ctx({ activeElementTag: "TEXTAREA" }))).toBe(false);
    expect(shouldFocusAskInput(ctx({ activeElementTag: "SELECT" }))).toBe(false);
  });

  it("ignores '/' while focus is in a contenteditable element", () => {
    expect(shouldFocusAskInput(ctx({ activeElementEditable: true }))).toBe(false);
  });

  it("still focuses when a non-input element (e.g. a button) has focus", () => {
    expect(shouldFocusAskInput(ctx({ activeElementTag: "BUTTON" }))).toBe(true);
  });
});
