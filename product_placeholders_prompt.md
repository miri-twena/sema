# Task: Placeholders pass — every discussed element visible in the product NOW

Goal: the product should SHOW the full vision in demos, even where functionality lands later. Frontend-only, one sweep. Every placeholder here is an ENTRY POINT + a minimal "coming soon"-grade surface — do NOT build deep UI that the queued functional prompts (`data_sources_add_prompt.md`, `alert_templates_prompt.md`, `answer_feedback_prompt.md`, auth Parts A+B) will replace; they own the real implementations. Follow `AGENTS.md` (SEMA is feminine in Hebrew; bilingual copy; RTL-safe; no new deps).

Shared pattern: disabled/placeholder affordances all use the same visual language — normal control, `cursor-default`, a small "בקרוב"/"Coming soon" tag or tooltip, and (where a click makes sense) a quiet toast "בקרוב — בפיתוח". Never a dead button with no feedback.

## 1. Sidebar footer — user identity (approved mockup, login spec v1.4 §4)

Two rows: org row (existing switcher + gear, unchanged) + user row below — initials avatar, name, role from the mock identity (**Miri Levi / "מירי לוי" · Admin** — server-reported via the existing me-equivalent, NOT hardcoded). Click opens a menu (`useDismiss`, keyboard accessible): "הגדרות אישיות" (disabled, "בקרוב" tag) · divider · "התנתקות" (danger color, logout icon) which navigates to the existing `/login` page — the placeholder loop until real auth. Both rows always present.

## 2. Gear menu — platform console entry (main spec §4)

Where the gear opens org admin today, show the two-level structure: "ניהול הארגון" (active, as today) + "קונסולת פלטפורמה" (disabled, "בקרוב") — so the two-tier model is visible.

## 3. Data sources — "Add data source" gallery (client screens spec §4.4 v1.6)

"הוסף מקור נתונים" button on the Data sources screen opens the connector gallery: cards with icon, one-line "what it unlocks", grouped — SQL DBs (PostgreSQL, MySQL, MS SQL Server), מערכות עסקיות (Priority ERP, Salesforce), מקורות קלים (Google Sheets, Excel/CSV), בקרוב (Shopify/WooCommerce, Google Analytics, Meta Ads). ALL cards are placeholder-state for now: clicking any shows "החיבור ייפתח בקרוב — בפיתוח" toast. The gallery component is the real one (`data_sources_add_prompt.md` keeps it and wires the flows); only the click handlers are placeholders.

## 4. Alerts area — "New alert" entry (spec §1.6.1 v1.4+)

In the home-screen customization Alerts area: "התראה חדשה" button opening a small preview popover of the 4 template types (percent change / absolute threshold / anomaly / streak — icon + name + one-liner each), all rows disabled with "בקרוב". One component, replaced by the real builder later.

## 5. Answer feedback — thumbs on answers (answer_feedback_prompt.md preview)

Thumbs up/down icons in the existing answer actions row (next to copy), both languages/directions, visible on hover like the other actions. Click → quiet toast "הפידבק יישמר בקרוב". No storage, no API.

## Constraints & accept

- Frontend only; zero backend changes; lint + build green; existing tests untouched.
- Every placeholder discoverable in a demo walk-through: login page (exists) → app → sidebar user row + menu → gear two-tier → Data sources gallery → Alerts "new alert" → answer thumbs.
- [ ] All five areas visible and consistent; every placeholder gives feedback on interaction; nothing dead-ends.
- [ ] `npm run lint`, `npm run build` pass.
