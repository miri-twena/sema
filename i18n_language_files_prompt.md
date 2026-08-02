# Task: Organized language files (i18n) — full Hebrew chrome when org language is Hebrew

Updated user decision (August 2026, supersedes the "only 2 strings" MVP rule): when the org opts into Hebrew, the UI chrome is FULLY translated — e.g. the conversation kebab menu (Rename / Pin chat / Archive / Delete) and the workspace switcher ("Connected") from the user's screenshots. English stays the default for every org. The user explicitly asked for organized language files. Follow `AGENTS.md` (its language bullet is already updated).

## 1. Infrastructure — central locale files, no scattered dicts

- `frontend/src/locales/en.ts` + `he.ts`: one typed structure, namespaced keys (`sidebar.*`, `menus.conversation.*`, `workspace.*`, `userMenu.*`, `chat.*`, `home.*`, `admin.users.*`, ...). TypeScript modules (not JSON) so key typos fail the build; a shared `TranslationKeys` type guarantees en/he structural parity at compile time.
- `useT()` hook / `t()` helper reading the EXISTING org-language source (`useUiLang` / `document.documentElement.lang`) — no new plumbing, no new deps (the codebase's `Record<Lang, ...>` pattern, centralized).
- Migrate the existing scattered dicts INTO the locale files (`placeholderCopy.ts`, `feedbackCopy.ts`, `loginCopy.ts` stays separate-but-relocatable since login is English-only at runtime, `auditSentences.ts` may stay put if its template logic doesn't fit flat keys — judgment call, document it).

## 2. Translation sweep — app chrome

Audit and migrate every hardcoded user-facing string in the main app: sidebar (section headers, New conversation, Archived, the kebab menu items incl. Delete, Trending chips label), workspace switcher (Connected, workspace, gear menu items), user menu, MessageActions (Copy/Retry/feedback labels), drill/thread UI labels, home dashboard section labels (BUSINESS OVERVIEW, RECOMMENDED ACTIONS, suggested questions header, period picker labels), toasts, empty states, confirm popovers.

## 3. Translation sweep — admin panel

Same treatment for all admin screens (nav items, Users screen labels/buttons, Data sources, Semantic model tabs, Org settings, Audit log UI labels). Where bilingual copy already exists (audit sentences, gallery), route it through the same locale mechanism or leave documented in place — no third pattern.

## 4. Rules that do NOT change

- Layout anchored: sidebar LEFT, no `dir="rtl"` on the shell; individual text elements may set direction as needed.
- Login page: English always (explicit earlier decision).
- Agent answers: language of the question, untouched.
- Brand/technical terms stay English: SEMA, "AI Business Advisor", SQL/YAML, metric ids, "Admin"/"Analyst"/"Viewer"? — role names DO get Hebrew display labels (מנהל/אנליסט/צופה) since they're user-facing; keep the canonical ids internal.
- English default org-wide; Hebrew only on explicit org opt-in.

## 5. Guardrails + verification

- Parity test: a vitest that walks both locale objects and fails on any missing/extra key (compile-time type + runtime test both).
- Hebrew quality: SEMA in feminine per AGENTS.md; sentence-case equivalents; no machine-translation stiffness — write copy like the existing Hebrew strings in the codebase.
- Verify live in BOTH languages: the two screenshot cases (conversation menu, workspace switcher) plus one admin screen; RTL text renders correctly inside the anchored LTR layout.
- `npm run lint`, `npm run build`, `npm run test`, `pytest` green.

Accept: [ ] Org language Hebrew → conversation menu, workspace switcher, sidebar, home labels, and admin screens all render Hebrew from the locale files; English default unchanged; parity test green; no hardcoded user-facing strings left in migrated surfaces.
