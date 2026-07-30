# Task: Real authentication — login screen, email one-time code, Google/Microsoft SSO, sessions

Implements `SEMA-Login-Spec.pdf` v1.1. Replaces the mock identity with real auth. Trial customers are REAL organizations with REAL data — treat this as production security, not demo code. Follow `AGENTS.md`. No passwords anywhere.

**Three parts. Part 0 (login page UI) is runnable NOW, standalone, before any hosting exists. Parts A+B are BLOCKED until a real HTTPS host is available — do not start them when executing Part 0. Part A must be fully green before Part B starts.**

## Part 0 — Login page UI only (run now, as prep for the hosting milestone)

Build the complete login page as a frontend-only slice — every visual and interaction state, no real backend:

0.1 Full-page route (`/login`, same routing approach as `/admin` — no new deps), OUTSIDE the app shell. The app itself remains freely accessible as today (mock identity untouched); the page is reachable directly for review and demos.
0.2 Implement the ENTIRE visual spec from `SEMA-Login-Spec.pdf` v1.1 §2: logo, headline, email field + continue, divider, Google/Microsoft buttons (official brand guidelines — icon, full label, equal size, no "primary" among them; rendered in disabled state with a "בקרוב"/"Coming soon" tooltip), "נתקלת בבעיה?" mailto, full RTL, bilingual copy (browser language), loading states, and the code step: 6-digit input (`autocomplete="one-time-code"`, autofocus), 60s resend countdown, "החלף אימייל" link.
0.3 Drive it with a local state machine + mocked async responses so EVERY state is demonstrable without a server: code sent, wrong code (attempts counter), expired code, uninvited email (generic message per anti-enumeration spec), suspended, network error. A small dev-only panel (visible only in dev builds) lets you force each state for review.
0.4 All the states are the spec's §2.2 error catalog — copy exactly as specced, in both languages. Keyboard accessible end-to-end.
0.5 Tests: `npm run lint`, `npm run build`; component renders in both languages/directions. NO backend code, NO session logic, NO cookies in this part — the mocked layer must be deletable in one file swap when Part A lands.

## Parts A+B — BLOCKED until real hosting (HTTPS) exists

Do NOT execute below this line while the queue marks this item blocked. Secure cookies and OAuth callbacks require a real HTTPS host; building them against localhost produces false confidence.

## Part A — Email one-time code + sessions (launch blocker)

1. **Login screen** (full-page route, outside the app shell): SEMA logo, one headline, email field + "המשך"/"Continue", divider, two SSO buttons (rendered but disabled with "בקרוב" until Part B ships behind its flag), "נתקלת בבעיה?" mailto link. Browser-language detection for first paint; org language after identification. Full RTL. Loading states per spec — never a blank screen.
2. **Code step:** "שלחנו קוד בן 6 ספרות ל-{email}" — code input with `autocomplete="one-time-code"` + autofocus, resend button with 60s countdown, "החלף אימייל" link.
3. **OTP backend:**
   - `login_codes(email, code_hash, expires_at, attempts, created_at)` — 6-digit code from a CSPRNG (`secrets`), ONLY the hash stored (same hashing approach as passwords, e.g. sha256+salt or passlib if already present — no new deps), 10-minute expiry, single use, new code invalidates previous, max 5 verify attempts then the code dies.
   - **Anti-enumeration:** uninvited email gets the exact same "code sent" screen with no email sent and comparable response time. Same principle on verify errors.
   - **Rate limits:** per-email and per-IP (5 codes/hour), simple counter table or in-memory with persistence — no new deps.
   - **Email sending:** pluggable sender in `sema_core` — `SMTP_HOST/PORT/USER/PASSWORD/FROM` env vars; bilingual minimal template (code, validity, "didn't request? ignore"). In `SEMA_AUTH_MODE=mock` the code is written to the server log instead of sent. Invite emails from the Users screen may reuse this sender (separate small template) but that's optional scope.
4. **Identity matching (invite-only):** verified email must match an `org_users` row (`active` or `invited`), case-insensitive. First login of an invited user: status→active, `joined_at` set, audit `user.joined`. Suspended → the spec's suspended message. No self-signup path whatsoever.
5. **Sessions:**
   - `sessions(id, user_id, created_at, last_seen_at, expires_at, user_agent)`; opaque random token (CSPRNG) in ONE cookie: httpOnly, Secure, SameSite=Lax. Fixed 14-day expiry (no sliding — MVP simplification).
   - Middleware: replace the mock identity resolution with session lookup WHEN `SEMA_AUTH_MODE=real`; `mock` keeps today's behavior for dev/tests. Everything downstream (require_client_admin, data scopes, audit actor) must work unchanged — zero call-site edits outside the middleware.
   - **Status check on every request:** suspended/removed user → 401 + session deleted; frontend redirects to login with the appropriate message (closes the spec §8 edge case).
   - Logout: button in the workspace switcher footer; deletes the server session.
6. **Audit ("access" category):** `auth.signed_in` (method: email_code), `auth.signed_out`, `auth.sign_in_failed` (uninvited/suspended — email only, never the code). Reuse `log_admin_event`'s system-actor path where the actor isn't an org user.
7. **Frontend session handling:** 401 anywhere → redirect to login (preserve nothing — post-login always lands on home, MVP simplification). App boot calls `/api/me`-equivalent to hydrate the user.

## Part B — Google + Microsoft SSO (after Part A is green)

8. OIDC Authorization Code + PKCE, server-side only: `/auth/{provider}/start` → provider → `/auth/{provider}/callback` on the API. Validate `state` + `nonce`; accept only `email_verified`; extract email/name/picture, discard provider tokens immediately (never stored, never sent to the browser). Same identity matching as Part A — same account regardless of method.
9. Providers behind flags: `AUTH_GOOGLE_ENABLED` / `AUTH_MS_ENABLED` (+ client_id/secret env vars, callback allowlist). A disabled provider's button shows disabled with tooltip. Google: standard OIDC. Microsoft: Entra ID v2.0 endpoint, work + personal accounts.
10. First-login name/picture from provider fill empty `org_users` fields (never overwrite admin-entered values). Audit method: `google`/`microsoft`.

## Constraints

- Production security bar: no secrets in code/logs, no provider tokens at rest, parameterized everything, CSRF via state + SameSite + Origin check on mutations. `docker-compose` gets the new env vars documented in `.env.example`.
- No new deps if avoidable (Python stdlib `smtplib`, `secrets`, `hashlib` cover Part A; for OIDC prefer manual code flow with `httpx`/`requests` if already present — check before adding any lib; if a lib is genuinely needed, ask per AGENTS.md rule).
- RTL-safe, bilingual copy, keyboard accessible (code input, resend).
- Tests (`pytest`): OTP happy path; expiry; 5-attempt lockout; single-use; resend invalidates old; anti-enumeration (uninvited email → same response shape, no email queued); rate limit; invited→active transition with `joined_at`; suspended blocked at login AND mid-session (second request after suspension → 401); logout kills session; mock mode still works end-to-end (all existing tests green in mock mode). Part B: state/nonce validation rejects tampering, unverified email rejected.
- Run `pytest`, `npm run lint`, `npm run build` — in BOTH auth modes for the backend suite.

## Accept

- [ ] In `real` mode: invited user enters email → receives code (or log line in dev) → enters code → lands on home as themselves; role/data-scope/audit all reflect the real user.
- [ ] Uninvited email sees "code sent" but nothing is sent; suspended user gets the suspended message; user suspended mid-session is cut off on their next request.
- [ ] Sessions survive API restart; logout works; cookie is httpOnly+Secure+Lax; 14-day expiry enforced.
- [ ] `mock` mode: entire existing dev/test experience unchanged.
- [ ] Part B (when enabled): Google and Microsoft both reach the same account as the email method; provider tokens are nowhere in DB or logs.
- [ ] All access events in the Audit log under the access category.
- [ ] `pytest` (both modes), lint, build pass.
