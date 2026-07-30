// SEMA: the ONLY UI strings that follow the org's language setting
// (chat_placeholder_language_prompt.md, per AGENTS.md's "UI is English,
// always" decision -- exactly these three, everything else stays English).
// Read via lib/useUiLang.ts, same `document.documentElement.lang` source the
// rest of the org-language-aware admin panel already reads.

import type { UiLang } from "./useUiLang";

export const CHAT_PLACEHOLDER: Record<UiLang, string> = {
  en: "Ask about revenue, customers, campaigns...",
  he: "אפשר לשאול על הכנסות, לקוחות וקמפיינים...",
};

export const NEW_CONVERSATION: Record<UiLang, string> = {
  en: "New conversation",
  he: "שיחה חדשה",
};

/** The drill-down panel's ghost placeholder -- a function, not a static dict
 * entry, since it interpolates the widget's (already-shortened) title. */
export function drillPlaceholder(lang: UiLang, shortTitle: string): string {
  return lang === "he" ? `אפשר להמשיך לשאול על ${shortTitle}...` : `Ask about ${shortTitle}...`;
}
