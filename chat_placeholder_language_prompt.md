# Task: Chat input placeholder follows org language (the ONE translated string pair)

Per the final language decision (spec v2.0 §2.1, AGENTS.md): the UI is English always, EXCEPT exactly two strings that follow the org language when an org explicitly opts into Hebrew: (1) the chat input ghost placeholder, (2) the "New conversation" label.

1. When org language = Hebrew: the chat input placeholder "Ask about revenue, customers, campaigns..." renders as "אפשר לשאול על הכנסות, לקוחות וקמפיינים..." (neutral address, no gendered verb), `dir="rtl"` on the placeholder text only (the input itself keeps its existing behavior; typed English stays LTR via the existing `dir="auto"` handling).
2. Same rule for the DRILL-DOWN input (DrillChat): its ghost placeholder (the follow-up prompt) gets a Hebrew counterpart under the same condition, same neutral phrasing style (e.g. "אפשר להמשיך לשאול על הנתון הזה..."), same `dir` handling. If DrillChat has more than one placeholder variant (new thread vs. resumed thread), translate each.
3. When org language = Hebrew: "New conversation" → "שיחה חדשה" (sidebar button / anywhere the label appears).
4. When org language = English (the default): everything stays English — zero visual change from today.
5. Wire to the SAME org-language source the app already reads (`PublicOrgSettings.language` → `document.documentElement.lang` from the gapfix work) — no new plumbing, no localStorage, no browser detection.
6. Verify all the strings flip together when toggling the org language in admin settings (main input, drill input, New conversation), and that nothing else in the UI changes language. `npm run lint`, `npm run build`; add/adjust a unit test asserting placeholder selection by lang.
