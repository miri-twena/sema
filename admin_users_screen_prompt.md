# Task: Client admin panel — Users and permissions screen (no real auth yet)

First implementation slice of the SEMA admin panel (spec: `SEMA-Admin-Panel-Spec.pdf` §6.1). Strategy agreed: NO real authentication yet — a mock "current user" (client admin) is hardcoded server-side; users live in real DB tables so the screen works on live data. Login comes in a later slice. Follow `AGENTS.md`; backend `sema_core/` + `api/`, frontend `frontend/`.

## Backend

1. Tables (mirror existing storage patterns/migrations): `org_users(id, client_id, name, email UNIQUE per client, title, role ENUM('client_admin','analyst','viewer'), status ENUM('active','suspended','invited'), invited_by (FK org_users.id, nullable — null for seeded/founding users), invited_at, invite_expires_at, joined_at (nullable — set when an invite is accepted / for seeded users = their created_at), last_active_at, created_at)`. `title` = free-text job title shown in the UI. `invited_by` + `joined_at` power the "Invited by / Joined on" profile fields.
2. Seed 10 users for client `e-commerce` (emails @ecommerce-demo.com unless noted; varied `last_active_at` from "now" to weeks ago):
   - Miri Levi / miri1988@gmail.com / Head of Data / **client_admin** / active
   - Dan Avrahami / CEO / **viewer** / active
   - Ronit Shapira / VP Operations / **viewer** / active
   - Demo User / Analyst / **analyst** / active
   - Noa Berman / Senior Analyst / **analyst** / active
   - Yossi Cohen / Marketing Analyst / **analyst** / active
   - Tamar Golan / Ecommerce Manager / **analyst** / active
   - Avi Peretz / CFO / **viewer** / active
   - Lior Katz / Data Analyst / **analyst** / suspended
   - dana@ecommerce-demo.com / Operations Analyst / **analyst** / invited (expires +7d)
   Also seed `invited_by` and `joined_at`: founding users (Miri, Dan, Demo User) get `invited_by=null` and a `joined_at` months ago; the rest get `invited_by=Miri` (or another admin) with varied `joined_at` dates; the pending `dana` invite has `invited_by=Miri`, `joined_at=null`. Seed runs with the existing data-seeding mechanism.
3. Endpoints under `/api/admin/users` (list w/ search+role filter, invite {email, role} → status=invited, PATCH role/status, DELETE, resend-invite → resets expiry). The list/detail payload includes each user's `invited_by` (resolved to the inviter's name, null when none) and `joined_at`. When an invite is created, stamp `invited_by` = current mock user. No email actually sent — log it, return ok.
3a. `GET /api/admin/roles` returns the role catalog used by the UI legend/tooltip: for each role (`client_admin`, `analyst`, `viewer`) a display name and a short capability description. This is the single source of truth — keep the copy consistent with spec §3, incl. the note that Analyst and Viewer are identical in the MVP and the distinction (e.g. data-scope limits) is reserved for V2.
4. `GET /api/admin/me` returns the mocked current user (Miri, client_admin, client e-commerce). ALL admin endpoints enforce server-side: requester must be client_admin (from the mock identity — build the check as real middleware so plugging in auth later is a drop-in).
5. Guards (server-side, tested): can't delete/downgrade/suspend the last active client_admin; can't invite an email that already exists in the client; invited users expire (expired invites shown as such, resend allowed).

## Frontend

New route `/admin` (React Router isn't installed — use the same conditional-render approach the app uses, or add a tiny hash-based route; NO new deps). Entry point: gear icon in the sidebar's workspace switcher area.

**Admin shell:** full-page layout, own secondary sidebar (nav items per spec §4; only "Users and permissions" is active — others render a disabled state with "Coming soon"), "Back to SEMA" link at top. Same design tokens/components as the app.

**Users screen — follow the approved mockup (Linear/Notion-style density):**

- Breadcrumb "E-Commerce › Organization admin", h1 "Users and permissions", primary CTA "Invite user" (top-right), subtitle "N members · N pending invites".
- Toolbar: search input (debounced, filters name/email) + role filter select.
- Table (flat rows, hairline dividers, no cards): avatar circle with initials (deterministic pastel per user), name + job title on one line (title muted) with email below, role as inline select (changes PATCH immediately, optimistic + toast on failure), relative last-active ("2 hours ago" — small util, no dep), kebab menu (view details / suspend / remove, with confirm popover reusing `useDismiss`).
- **Role legend/tooltip (from `GET /api/admin/roles`):** the "ROLE" column header carries a small info affordance (ⓘ) that opens a compact legend listing every role with its one-line capability description; each role select/label also exposes the same description on hover/focus via `aria-describedby` (native `title` is not enough — build an accessible tooltip). Copy must state that Analyst and Viewer currently have identical access and the distinction is reserved for V2. RTL-safe positioning.
- **User detail (Invited by / Joined on):** clicking a row — or the kebab "View details" — opens a right-side drawer/popover with the full profile: avatar, name, title, email, role, status, last active, **Invited by** (inviter's name, or "—" / "Founding member" when null) and **Joined on** (formatted `joined_at`; for pending invites show "Not joined yet · invited {relative}"). Read-only here except the same role/status controls; RTL-safe, keyboard-dismissible (`useDismiss`), focus-trapped.
- Current user's row: "(you)" suffix, no role select / no kebab. Last-admin rule surfaced as a muted info line under the table AND enforced by disabling the relevant controls.
- Invited rows: envelope avatar, "Invite sent · expires in N days" (or "expired"), Pending badge, Resend/Cancel inline text actions.
- Invite modal: email + role select + hint "Invite link is valid for 7 days" — validate email format, show server errors inline (duplicate email etc.).
- Empty search state: "No users match your search". Loading: skeleton rows.

## Constraints

- RTL-safe (logical properties), keyboard accessible (row actions reachable, aria-labels, focus rings), no new deps.
- SaaS-grade polish: 13px row text, 32px avatars, consistent 0.5px hairlines, subtle hover on rows, toasts for failures only (success is silent state change).
- Tests: backend guards (last admin, duplicate invite, expiry) via `pytest`; run `npm run lint`, `npm run build`.

## Accept

- [ ] `/admin` shows the 10 seeded users for e-commerce (incl. one suspended, one pending invite); search + role filter work.
- [ ] Inline role change, suspend, remove, invite, resend, cancel — all functional against the DB with optimistic UI.
- [ ] Last-admin and duplicate-invite guards enforced server-side and reflected in UI.
- [ ] Own row is protected; pending invite shows expiry; expired invite offers resend.
- [ ] Role legend/tooltip renders from `GET /api/admin/roles`, is keyboard/screen-reader accessible, and states the Analyst≡Viewer (V2 distinction) note.
- [ ] User detail drawer shows Invited by and Joined on from live data (incl. "Founding member" / "Not joined yet" cases).
- [ ] `pytest`, lint, build pass.
