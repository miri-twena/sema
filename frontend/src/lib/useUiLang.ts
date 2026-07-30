import { useEffect, useState } from "react";

export type UiLang = "en" | "he";

function readLang(): UiLang {
  return document.documentElement.lang === "he" ? "he" : "en";
}

/**
 * Reactive read of the chrome UI language App.tsx sets on `<html lang>`
 * (org setting once resolved, browser default before that -- see
 * org_settings_gapfix_prompt.md Part 2). Lets any component pick bilingual
 * copy without threading a language prop through the whole tree; a
 * MutationObserver (no new dependency) keeps it in sync if the attribute
 * changes after mount (e.g. the org-settings fetch resolving).
 */
export function useUiLang(): UiLang {
  const [lang, setLang] = useState<UiLang>(readLang);
  useEffect(() => {
    const observer = new MutationObserver(() => setLang(readLang()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    return () => observer.disconnect();
  }, []);
  return lang;
}
