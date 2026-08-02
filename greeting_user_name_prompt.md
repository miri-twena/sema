# Task: Two small UI fixes — greeting name + login screen English-only

## Fix 1: Login screen is ALWAYS English

The login page currently renders in Hebrew (browser-language detection from the original Part 0 spec — since superseded by the "UI is English, always" decision in `AGENTS.md`). Fix:

A. The ENTIRE login screen (`/login`) renders in English only, LTR, regardless of browser language or org language: headline, labels ("Email"), buttons ("Continue"), divider ("or"), code step, all error states, "Having trouble?". Remove/bypass the browser-language detection on this page (keep the copy dictionary — the Hebrew strings become dead for now, don't delete them).
B. While here: the tagline under the logo must be **"AI Business Advisor"** (English brand phrase, per login spec v1.4 §2.1) — the screenshot shows the old Hebrew tagline.
C. Email input stays LTR (already is). Update the Part-0 unit tests that assert language detection/Hebrew rendering on this page.

## Fix 2: Home screen greeting — greet the user, not the organization

The home dashboard greeting currently reads "Good afternoon, E-Commerce" (org name). It must greet the PERSON: "Good afternoon, Miri".

1. Source: the same identity the sidebar user row uses (`/api/admin/me`-equivalent — mock identity today, real user after auth Part A lands automatically). Use the FIRST name only (first whitespace-separated token of the display name).
2. Fallback chain: user first name → org name (current behavior) if identity doesn't resolve. Never an empty greeting.
3. Greeting language follows the chrome-language rules (English always; the existing time-of-day logic unchanged). The name renders as-is (a Hebrew display name inside the English greeting is fine — wrap the name in `dir="auto"`).
4. Applies everywhere the greeting renders (home dashboard; check the daily-brief header if it repeats the pattern).
5. `npm run lint`, `npm run build`; adjust any existing test that asserts the org-name greeting.

Accept: home screen shows "Good afternoon, Miri" with the mock identity; org name still appears only in the sidebar org row.
