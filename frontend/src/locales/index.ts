import { en, type TranslationKeys } from "./en";
import { he } from "./he";
import { useUiLang, type UiLang } from "../lib/useUiLang";

export type { TranslationKeys } from "./en";

export const LOCALES: Record<UiLang, TranslationKeys> = { en, he };

/** The current org-language locale object, read via the same
 * `document.documentElement.lang` source every other language-aware
 * component already uses (useUiLang). Access nested keys directly --
 * `const t = useT(); t.sidebar.newConversation` -- rather than a `t("a.b.c")`
 * string function, so a typo or a renamed key fails the TypeScript build. */
export function useT(): TranslationKeys {
  const lang = useUiLang();
  return LOCALES[lang];
}
