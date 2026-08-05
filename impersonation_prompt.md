# Task: admin impersonation — "view as" another org user

A client_admin can temporarily use the system AS another user in their org — seeing exactly
what that user sees (role, data scope, home config) — to debug "why can't Dana see the
revenue dashboard" without walking to Dana's desk. Standard admin/support feature.

## Design constraints (read first)

1. **Identity has ONE swap point.** `sema_core/current_user.py::current_identity()` is
   deliberately the only place that answers "who is making this request", and
   `require_client_admin` / the data-scoped routes all flow through it. Impersonation must
   respect that architecture: implement it as a layer INSIDE the identity resolution
   (effective identity = impersonated user when an impersonation is active, else the real
   one), NOT as scattered per-route overrides. When real auth (#11) lands and
   `current_identity()` starts reading sessions, impersonation must keep working unchanged.
2. **Auth is still mock.** Today every request resolves to Miri (ecommerce client_admin).
   Impersonation state therefore can't live in a session cookie yet — hold it server-side,
   keyed by the real (admin) identity, in a small store (SQLite in `var/`, consistent with
   the other stores). One active impersonation per admin. When #11 ships sessions, the
   state keying moves from "mock identity" to "session identity" with no other change.
3. **The impersonator must never gain power, only lose it.** Effective role/data-scope =
   the TARGET user's. A viewer being impersonated must not expose admin routes: while
   impersonating, `require_client_admin` FAILS (403) unless the target is themselves a
   client_admin — with one exception, the stop-impersonation endpoint, which must always
   work for the real admin.

## Rules

- Who: active `client_admin` only (existing role model: `client_admin`/`analyst`/`viewer`
  in `sema_core/org_user_store.py`). Target: any OTHER active user in the SAME client.
  Suspended/invited targets: not impersonatable (they can't log in themselves — 409 with a
  clear message). Self-impersonation: no-op, reject.
- Cross-client impersonation: never. Validate both sides against the same `client_id`.
- Time-box: auto-expires after 30 minutes (store expiry timestamp; expired = not active,
  lazily cleaned). Stopping is always available and instant.
- **Write actions while impersonating are allowed** (that's the point — reproduce the
  user's experience) **except**: anything under the admin panel when the target is an
  admin — user management, org settings, semantic model publish — those require dropping
  impersonation first (403 with a message saying so). This keeps "acted as someone else"
  away from the highest-blast-radius operations.

## Audit — non-negotiable

The append-only audit log (`sema_core/audit_store.py`) records:

- `impersonation.started` — actor = the real admin, target user id/email, expiry.
- `impersonation.stopped` — actor = the real admin (explicit stop vs. expiry noted).
- Every audited action performed DURING impersonation carries BOTH identities: keep the
  existing actor field = effective (target) user for continuity, add an `impersonator`
  field (or metadata key) with the real admin's id. The audit screen shows it ("Dana Levi
  (via Miri Twena)"). Nothing performed while impersonating may appear in the log as
  plain-Dana with no trace of Miri.

## API

Under the existing admin router conventions (`require_client_admin`, audit, 404-safe):

- `POST /api/admin/impersonation` `{user_id}` → starts; returns effective-user summary +
  expiry. Errors: 403 (not admin), 404 (no such user), 409 (self / suspended / already
  impersonating).
- `DELETE /api/admin/impersonation` → stops. Always allowed for the real admin, even
  mid-impersonation (see design constraint 3).
- `GET /api/admin/impersonation` → current state (none / target + expiry). The frontend
  polls nothing new — fold this into the existing identity/me payloads if one is already
  fetched at boot (`admin_me` and whatever the app shell reads), so the app knows on load.

## Frontend

- **Entry point:** Users screen (`UsersScreen.tsx` / `UserRow.tsx` / `UserDetailDrawer.tsx`)
  — a "View as user" action on each eligible row (hidden on self, disabled with tooltip on
  suspended/invited).
- **The banner is the feature's seatbelt:** while impersonating, a persistent, unmissable
  top banner across the ENTIRE app (chat + admin): "Viewing as Dana Levi (viewer) · ends in
  27m · [Stop]" — warning-tinted (existing `warning` tokens), not dismissible, always shows
  the Stop button. RTL/locale-aware (en+he strings in the locale files).
- On start: full app-state refresh (the simplest correct approach: hard reload after the
  POST succeeds — conversations, home config, scopes all re-fetch under the new effective
  identity). Same on stop.
- While impersonating a non-admin, the sidebar's admin gear hides (matches the 403).

## Tests

- Identity layer: effective identity switches / restores; expiry honored; one-per-admin.
- Authz: viewer-as-target cannot reach any admin route (reuse the route matrix from
  `tests/test_authz_matrix.py` — run it under active impersonation of a viewer and assert
  the admin rows flip to 403 while the stop endpoint stays 200).
- Cross-client target rejected; suspended target rejected; self rejected.
- Audit: start/stop events; a scoped action during impersonation carries both identities.
- Data scope: impersonating a `viewer` with a narrow scope actually narrows chat/overview
  answers (existing scope test fixtures).
- `pytest`, `npm run lint`, `npm run build`, vitest green.

## Accept

- [ ] **Works fully TODAY under `SEMA_AUTH_MODE=mock` — this is the primary acceptance
      environment, not a future state.** Concretely: Miri (the mock identity) opens the
      Users screen, clicks "View as" on Dana Levi, and the entire app becomes Dana's —
      her role, her data scope, her home config, her conversations — until Stop or expiry.
      Nothing about this feature waits for #11/real sessions.
- [ ] Admin starts "View as" from the Users screen, sees the target's exact app (scope,
      role, home config), banner always visible, Stop restores instantly.
- [ ] No privilege escalation path: impersonated viewer ⇒ admin routes 403 (matrix-proven).
- [ ] Every trace in the audit log shows both identities; start/stop events present.
- [ ] Auto-expiry works (test with a shortened expiry via env/monkeypatch).
- [ ] Survives the future auth swap: impersonation logic reads/writes only through the
      identity layer + its own store — grep-provable absence of per-route identity hacks.
