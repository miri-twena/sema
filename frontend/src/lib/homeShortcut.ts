// The home screen's "/" shortcut (home_ask_bar_top_prompt.md item 5): focus
// the hero ask input from anywhere on the page. Extracted as a pure function
// (no DOM access) so the guard conditions are unit-testable without a
// component-render harness -- this codebase has none (see loginReducer in
// hooks/useLoginFlow.ts for the same pattern).

export interface SlashShortcutContext {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  /** True while a modal/drawer/panel is covering the home screen (the
   * mobile sidebar drawer, the drill-down panel). The admin panel doesn't
   * need to be checked here -- opening it unmounts the whole home tree, so
   * this handler is never even attached while it's open. */
  modalOpen: boolean;
  /** `document.activeElement?.tagName`, or undefined if nothing is focused. */
  activeElementTag: string | undefined;
  /** `document.activeElement`'s `isContentEditable`. */
  activeElementEditable: boolean;
}

const FOCUSABLE_INPUT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** True iff this keydown should focus the hero ask input. */
export function shouldFocusAskInput(ctx: SlashShortcutContext): boolean {
  if (ctx.key !== "/" || ctx.metaKey || ctx.ctrlKey || ctx.altKey) return false;
  if (ctx.modalOpen) return false;
  if (ctx.activeElementEditable) return false;
  if (ctx.activeElementTag && FOCUSABLE_INPUT_TAGS.has(ctx.activeElementTag)) return false;
  return true;
}
