# Deployment

Platform-agnostic steps for SEMA's first production deployment. This is the
code-side companion to `SEMA-Deployment-Checklist.pdf`; that document covers
the human/business steps (DNS, platform account, support process), this one
covers what the running system needs.

## ⚠️ Read this before deploying

**There is no real authentication yet.** `sema_core/current_user.py`
resolves every request's identity to a single hard-coded mock user
(`current_identity()`), which backs every `/api/admin/*` route (users,
semantic model, org settings, audit log, data sources) and every
data-scoped route (chat, overview, alerts). Real login (email one-time code
+ SSO) is `auth_login_prompt.md` Parts A+B, blocked until a host with HTTPS
exists — i.e. blocked until *this* deployment exists.

This deployment prep deliberately leaves the mock identity **active** in
production rather than disabling it (which would make the admin panel and
chat unusable) or building real auth early (out of scope here, and it needs
this host to exist first). The consequence: **anyone who reaches the
deployed URL has full, unauthenticated admin access** — user management,
semantic model edits, org settings, the works. Treat this deployment as a
**private/controlled pilot** (an unlisted URL, a small trusted group) until
real auth ships, not as something to link publicly. The API logs a loud
warning about this on every production boot so it's never silently
forgotten; see `sema_core/settings.py`'s `validate_for_production` and
`api/main.py`'s startup block.

**Internal-pilot access gate (`SEMA_API_KEY`) is not a substitute for the
above.** Setting `SEMA_API_KEY` makes every `/api/*` route (and only those
— see §3) require a shared `X-API-Key` header; the React frontend now has a
matching gate screen (`frontend/src/components/access/PilotAccessGate.tsx`)
that prompts for the key once, keeps it in `sessionStorage` for the tab's
lifetime, and attaches it to every request (`frontend/src/lib/pilotAccess.ts`).
This is a **temporary shared-secret door**, not authentication: everyone who
has the key is the SAME anonymous caller as far as the app is concerned —
still the one mock identity above, still full admin access once inside. Its
only job is to keep an unlisted pilot URL from being a bare, keyless admin
panel to anyone who finds it. Do not describe it to users as "logging in."

## 1. Choose a container option

Two ways to serve the frontend; **API-served is the default** for a
single-service pilot (fewer moving parts, no CORS between two origins):

- **API-served (default):** `api/Dockerfile.prod` builds the React app and
  serves the static output from the same FastAPI process (`api/main.py`'s
  SPA catch-all route, active only when `frontend/dist` exists in the
  image). One container, one port, one URL.
- **Separate static service:** build `frontend/` with `npm run build` and
  serve `frontend/dist` from any static host/CDN (Netlify, Vercel, a
  platform's static-site service, nginx) instead, pointing it at the API's
  URL via `VITE_API_URL` at build time. Needs `SEMA_CORS_ORIGINS` (or
  `SEMA_PUBLIC_URL`) on the API side to include that static host's origin,
  and cookies -- once sessions exist -- to work cross-origin. Use this if
  you want the frontend on a CDN/edge network independent of the API's
  deploy cadence; otherwise prefer the option above.

This doc covers the API-served option end-to-end; the separate-service
option only needs the CORS note above on top of the same API deployment
steps.

## 2. Build and run

```bash
# Local smoke test (see docker-compose.prod.yml's own header comment for
# the full walkthrough):
cp .env.example .env
#   ...fill in every "REQUIRED in production" value in .env, set SEMA_ENV=production...
docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost:8000/healthz
```

For an actual platform (Railway/Render/Fly/etc.), point it at `api/
Dockerfile.prod` as a Docker-based service and configure the same env vars
directly in the platform's dashboard/secrets manager instead of a `.env`
file. Most platforms auto-detect the `EXPOSE 8000` and route traffic to it.

## 3. Environment variables

Every variable is documented in `.env.example`, grouped and commented. The
ones marked **REQUIRED in production** there are enforced at startup:
`sema_core.settings.validate_for_production` runs once when `SEMA_ENV=
production`, and `api/main.py` raises immediately (before the app can serve
a single request) if any are missing or still at their local-dev default —
you'll see every problem listed at once in the container's boot logs, not a
crash-loop discovering them one at a time:

| Variable | Why it's required |
|---|---|
| `ANTHROPIC_API_KEY` | No agent without it |
| `SEMA_SECRETS_KEY` | Encrypts stored DB credentials at rest; must be a valid Fernet key |
| `SEMA_API_KEY` | Empty = the entire API has NO authentication. Once set, `require_api_key` (`api/main.py`) gates every `/healthz`-excepted, `/api/*` route with this value as a shared `X-API-Key` header — see §0's internal-pilot gate note. Non-`/api` paths (the built SPA's `index.html`/JS/CSS) stay reachable with no key on purpose, so the browser can load the gate screen itself; the interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled outright in production instead, since they also live outside `/api`. |
| `SEMA_PUBLIC_URL` | Drives the CORS allowlist |
| `POSTGRES_PASSWORD` / `POSTGRES_READONLY_PASSWORD` | Must not be the well-known local-dev defaults |

`SEMA_ENV=production` also makes cookies (once sessions exist) default to
`Secure`, and is what api/main.py's mock-identity warning above checks for.

## 4. Persistent storage — what MUST be on a volume

Everything stateful lives under two logical paths. Losing either without a
volume means losing real data on every restart/recreate:

- **`var/`** — a single SQLite file (`sema_state.db`) backing conversations,
  org users, org settings, the audit log, home-screen config, alerts,
  data-source connection/request/upload metadata, and answer feedback —
  plus `var/logos` (uploaded org logos, `api/main.py`'s `_logos_dir()`,
  which is always `SEMA_CONVERSATION_DB`'s parent directory — pointing that
  one env var at the volume covers both).
- **`sql/`** — the semantic model's `*.yaml` files (`sql/semantic/`,
  `sql/insurance/semantic/`), and really the WHOLE `sql/` tree
  (`schema.sql`, `validation_queries.sql`, `create_readonly_role.sql`, …) —
  some code paths read other files under `sql/`, not just the two semantic
  directories. **Easy to miss on the YAML specifically**: it looks like
  static config checked into git, but the admin panel's Publish/Restore
  flow (`sema_core/semantic_editor.py`) rewrites it on disk at runtime.
  Without this on a volume too, a published semantic-model change survives
  only until the container is recreated, then silently reverts to whatever
  was baked into the image.

**Single-disk platforms (Render — see §9 — and any platform that only
offers one mount path per service):** `sema_core/persist_bootstrap.py` runs
once at container start, before Uvicorn (`api/Dockerfile.prod`'s `CMD`), and
reconciles ONE mounted disk into both paths above:
1. Creates `<disk>/var` (so `SEMA_CONVERSATION_DB=<disk>/var/sema_state.db`
   has somewhere to create its file) and `<disk>/sql`.
2. On the FIRST boot only (an empty/missing `<disk>/sql`), copies the
   image's own `sql/` tree into `<disk>/sql` — seeding it from what THIS
   image shipped with, never overwriting an already-seeded disk.
3. Symlinks the image's `sql/` path to `<disk>/sql`, so every existing
   module that reads/writes `sql/...` (unchanged) transparently goes
   through to the persisted copy.

Mounting the disk directly over `/app` (hides the application code) or
directly over `/app/sql` (hides the image's baked-in `sql/` tree on an
otherwise-empty first-boot disk) are both explicitly wrong — this is why
the bootstrap step exists instead. The disk path itself is configurable via
`SEMA_PERSIST_ROOT` (default `/app/persist`); `render.yaml` and
`docker-compose.prod.yml` both use that default.

**Docker Compose (multi-disk platforms, or this repo's own local smoke
test):** `docker-compose.prod.yml` mounts ONE named volume
(`sema_persist_prod`) at `/app/persist`, deliberately mirroring Render's
single-disk constraint rather than mounting `/app/var` and `/app/sql`
separately — see that file's own comments.

Uploaded CSV/xlsx row data does NOT need a volume — it's written into the
tenant's own Postgres database (already durable via that database's own
storage), only the upload's *metadata* lives in `var/`.

**Verify locally** before trusting this in production:
```bash
docker compose -f docker-compose.prod.yml up -d --build
#   ...create a conversation, invite a user, edit something in the admin panel...
docker compose -f docker-compose.prod.yml restart api
#   ...confirm everything you just did is still there.
```

## 5. CORS and cookies

`SEMA_CORS_ORIGINS` is the explicit allowlist (comma-separated); `
SEMA_PUBLIC_URL` is folded into it automatically so you don't repeat the
same origin in two places. No cookies are set anywhere yet (no sessions
exist) — `settings.cookie_secure` (true whenever `SEMA_ENV=production`) is
the one flag `auth_login_prompt.md`'s session implementation will read; it
exists now as the configuration surface, not as something active today.

## 6. Health check

`GET /healthz` — no auth, not under `/api`, minimal payload
(`{"status", "db_connected", "version"}`). Point your platform's health
check / uptime monitor at this path. `version` reflects `SEMA_VERSION` if
your CI/build sets it (a commit SHA or tag); otherwise `"unknown"`, which
is expected locally.

`GET /api/health` still exists separately — that's the richer, API-key-
gated status the frontend itself polls for its own connection indicator;
`/healthz` is the infra-facing one.

## 7. What's gated in production vs. what isn't

Audited every route and dev affordance in the codebase for this task:

- **The frontend's login dev-state panel** (`DevStatePanel.tsx`, lets a
  reviewer force any login-flow state without a backend) is already gated
  by Vite's `import.meta.env.DEV`, which a production build strips
  entirely — no further gating needed; it's a frontend-only affordance
  with no backend route to double-gate.
- **No seed/reset HTTP endpoint exists** in `api/main.py` today — the demo
  data seeding (`OrgUserStore.seed_demo_users`) is only ever called from a
  manual script (`data/load_data.py`) and test fixtures, never from a
  route. Nothing to gate.
- **The mock identity** (see the warning at the top of this doc) is
  deliberately left active rather than gated — gating it would break the
  admin panel and every data-scoped route until real auth ships.

If you add a genuinely dev-only route later, gate it the same way
`validate_for_production` already establishes the pattern: check
`settings.env` server-side (never client/build-time only for anything with
a real backend route behind it).

## 8. Smoke test after deploying

1. `curl https://<your-domain>/healthz` → `{"status": "ok", "db_connected": true, ...}`
2. Open the app in a browser, ask a real question, confirm a chart/table/KPI renders.
3. Open the admin panel, confirm Users/Semantic model/Data sources load.
4. Check the container's boot logs for the mock-identity warning (§0) — if
   it's missing, `SEMA_ENV` probably isn't actually `production`.

## 9. Render internal pilot

The recommended path for the first deployment: one paid Web Service
(Docker, Frankfurt, Starter), Render-managed Postgres, one persistent disk.
`render.yaml` (repo root) is the Blueprint — its own header comment explains
exactly what it can and can't express declaratively; this section is the
walkthrough, including the manual steps it calls out.

### 9.1 Create the Postgres database

From the Render dashboard: **New → Blueprint**, point it at this repo.
Render reads `render.yaml` and proposes `sema-pilot` (the web service) and
`sema-pilot-db` (Postgres, Frankfurt, `basic-256mb`) together. Approve it —
Postgres provisions first since the web service's env vars reference it via
`fromDatabase`.

### 9.2 Connect using Render's internal hostname

`render.yaml`'s `fromDatabase` env vars already wire this up automatically
— you do not manually copy a connection string. For reference, this is
what gets resolved:

| `render.yaml` env var | Render connection field | Notes |
|---|---|---|
| `POSTGRES_HOST` | Internal hostname (`fromDatabase: host`) | Resolves only from services in the same Render private network — never publicly routable, which is exactly what you want (§9.7). |
| `POSTGRES_PORT` | `fromDatabase: port` | Always `5432` for Render Postgres. |
| `POSTGRES_USER` | `fromDatabase: user` | Render's own admin user — **do not** also use this as `POSTGRES_READONLY_USER` (§9.4). |
| `POSTGRES_PASSWORD` | `fromDatabase: password` | |
| `POSTGRES_DB` | `fromDatabase: database` | `sema_db` — the `ecommerce` client's database (`config/clients.yaml`'s `db_env: POSTGRES_DB`). |

### 9.3 Obtain the Render External Database URL without exposing it

Several steps below (§9.4–§9.6) need `psql` connected as `sema-pilot-db`'s
admin user from your own machine — Render only offers this via the
**External Connection String** (`sema-pilot-db` → **Connect** tab), which
embeds the admin password. Handle it so it never lands in git, chat, a
screenshot, shell history, or a log:

```powershell
$env:SEMA_TMP_DB_URL = Read-Host "Paste the Render External Connection String"
```

`Read-Host` reads your pasted answer as interactive input, not as a
command-line argument — it is never written to PowerShell's command
history (only literal commands you type are). Use `$env:SEMA_TMP_DB_URL`
in every command below instead of pasting the connection string itself
each time, and remove it the moment you're done (§9.7 has the exact
cleanup command) — never leave it sitting in an open terminal's
environment longer than the setup steps that need it.

### 9.4 Provision `insurance_db` and the shared `sema_readonly` role

**Never set `POSTGRES_READONLY_USER` to Render's own admin user** (§9.2's
`POSTGRES_USER`) — `sema_core`'s SQL-safety layer (`sema_core/agent/safety.py`)
trusts this role to be PHYSICALLY unable to write, not just told not to;
reusing the admin user silently turns every "read-only" guardrail into
nothing. `sema_readonly` is cluster-wide (one role, not one per database) —
create it once, then apply its grants to each tenant database separately,
since Postgres privileges are always scoped per-database.

Open ONE interactive `psql` session for this whole section (using §9.3's
temporary variable):

```powershell
psql $env:SEMA_TMP_DB_URL
```

Then, at the `psql` prompt:

```sql
-- Both tenants live on THIS SAME Render Postgres instance (one paid
-- service, not two) as separate databases -- never point `insurance` at
-- `ecommerce`'s own database, and never skip creating this one silently.
CREATE DATABASE insurance_db;

-- sema_db: create the role (idempotent, no password yet -- see the file's
-- own comments) and apply its CONNECT/USAGE/SELECT/default-SELECT grants.
\c sema_db
\i sql/create_readonly_role.sql

-- Set the role's password interactively -- NOT a command-line argument, so
-- it never appears in shell history or a process listing. Enter the EXACT
-- value already stored (or that you're about to store) as Render's
-- POSTGRES_READONLY_PASSWORD env var, so the database role and the app's
-- configured credential match.
\password sema_readonly

-- insurance_db: same script, same idempotent role (a no-op there since it
-- already exists), but its CONNECT/USAGE/SELECT grants are database-scoped
-- and so must be applied again, connected HERE.
\c insurance_db
\i sql/create_readonly_role.sql

\q
```

Set `POSTGRES_READONLY_USER=sema_readonly` and `POSTGRES_READONLY_PASSWORD`
(the exact value you just typed at `\password`) in the web service's
environment (dashboard → Environment, both `sync: false` in the Blueprint).
`POSTGRES_DB_INSURANCE` needs no manual step here — it's a fixed
(non-secret) value in `render.yaml` itself (§9.6).

### 9.5 Load both tenants' data, then reapply the read-only grants

From your own machine, temporarily, using process-scoped environment
variables (never a `.env` file pointed at Render, and never commit these
values) — `Read-Host` again for the password, same reasoning as §9.3:

```powershell
$env:POSTGRES_HOST = "<external host from the Connect tab>"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "<admin user from the Connect tab>"
$env:POSTGRES_PASSWORD = Read-Host "Render admin password"

$env:POSTGRES_DB = "sema_db"
.venv\Scripts\python.exe data\load_data.py

.venv\Scripts\python.exe data\insurance\load_data.py

Remove-Item Env:\POSTGRES_HOST, Env:\POSTGRES_PORT, Env:\POSTGRES_USER, Env:\POSTGRES_PASSWORD, Env:\POSTGRES_DB
```

(`data/insurance/load_data.py` reads `POSTGRES_DB_INSURANCE`, defaulting to
`insurance_db` — already correct, no override needed. It also re-grants
`sema_readonly` SELECT on its own tables automatically at the end; `data/
load_data.py` does not — see that file's own comment on why.)

Both loaders **drop and recreate their tables** (`sql/schema.sql` /
`sql/insurance/schema.sql`), which can leave `sema_readonly`'s explicit
`GRANT SELECT ON ALL TABLES` behind a table that no longer exists under
that grant. Reapply/verify it for both, uniformly, rather than trusting
`ALTER DEFAULT PRIVILEGES` alone or remembering which loader already did it:

```powershell
psql $env:SEMA_TMP_DB_URL -d sema_db -f sql/create_readonly_role.sql
psql $env:SEMA_TMP_DB_URL -d insurance_db -f sql/create_readonly_role.sql
```

(The script is idempotent — re-running it after the role already exists
and already has a password just reapplies the grants; it does not touch
or clear the password `\password` set in §9.4.)

**Verify now, while external access is still open** (§9.7 restricts it
right after) — this is the point in the workflow where every guarantee
this whole section exists for can actually be checked against real data.

Database-level isolation first (proves the two tenants are genuinely
separate databases, not just separately-labeled tables), admin connection:

```sql
\c sema_db
\dt
-- expect: customers, marketing_campaigns, orders, order_items, products, website_sessions
SELECT count(*) FROM orders;             -- non-zero
SELECT * FROM policies LIMIT 1;          -- EXPECTED TO ERROR: relation "policies" does not exist

\c insurance_db
\dt
-- expect: agents, claims, drivers, policies, policyholders, premium_payments, products, vehicles
SELECT count(*) FROM policies;           -- non-zero
SELECT count(*) FROM claims;             -- non-zero
SELECT * FROM orders LIMIT 1;            -- EXPECTED TO ERROR: relation "orders" does not exist
```

The last query in each block isn't optional cleverness — it's the actual
proof that the ecommerce connection cannot see insurance's tables and vice
versa: in Postgres, a connection to one database simply has no visibility
into another database's objects at all, so this always fails, by
construction, for any two separate databases (not something SEMA's own
code enforces — the isolation is structural).

Then `sema_readonly`'s privileges, connecting AS that role (same temporary
connection string, different role):

```powershell
psql $env:SEMA_TMP_DB_URL -U sema_readonly -d sema_db -W
```

(`-U`/`-d` override the connection string's admin username/database;
`-W` forces psql to prompt fresh rather than reuse the URI's embedded
ADMIN password, which belongs to a different role and would fail here.)

```sql
SELECT count(*) FROM orders;             -- succeeds
INSERT INTO orders DEFAULT VALUES;       -- EXPECTED TO ERROR: permission denied for table orders
UPDATE orders SET order_id = order_id;   -- EXPECTED TO ERROR: permission denied
DELETE FROM orders;                      -- EXPECTED TO ERROR: permission denied
TRUNCATE orders;                         -- EXPECTED TO ERROR: permission denied
DROP TABLE orders;                       -- EXPECTED TO ERROR: must be owner of table orders
```

Repeat against `insurance_db` (`psql $env:SEMA_TMP_DB_URL -U sema_readonly
-d insurance_db -W`, same five statements against `policies` or `claims`)
— every one of them must fail the same way. If any of them SUCCEEDS, stop:
something upstream (a stray `GRANT` run by hand, or the wrong role
connected) has broken the read-only guarantee, and it must be fixed
(re-run the `\i sql/create_readonly_role.sql` commands above, which REVOKE
write privileges unconditionally) before this pilot goes live — do not
proceed to §9.6/§9.7 with a failing check here.

**Caveat:** running these loaders from your own machine also runs their
`seed_org_users()` / SQLite-touching side effects against **your local**
`var/sema_state.db` (`SEMA_CONVERSATION_DB`), not Render's persisted disk —
they only load Postgres data remotely. That's expected; the app's own
demo-user seeding on Render is a separate, already-solved concern
(`sema_core.org_user_store`), not something this dataset load needs to
repeat.

### 9.6 `POSTGRES_DB_INSURANCE` is already set — confirm it

Unlike `POSTGRES_READONLY_USER`/`POSTGRES_READONLY_PASSWORD`, this one
needs no dashboard step: `render.yaml` declares
`POSTGRES_DB_INSURANCE=insurance_db` as a fixed, non-secret value (not
`sync: false`) — it's a plain database identifier, not a credential, and
both tenant databases are now provisioned and loaded (§9.4/§9.5), so
there's nothing left to fill in. This is what `config/clients.yaml`'s
`insurance` client (`db_env: POSTGRES_DB_INSURANCE`) resolves to reach its
own database, kept completely separate from `ecommerce`'s
`POSTGRES_DB=sema_db`. Confirm both are set correctly on the deployed
service (dashboard → Environment): `POSTGRES_DB=sema_db` and
`POSTGRES_DB_INSURANCE=insurance_db` — **never** the same value for both,
which would silently collapse the two tenants onto one database
(AGENTS.md: "never silently fall back to another tenant's data").

Both tenants are now fully provisioned and loaded for this pilot — unlike
an earlier draft of this doc, `insurance` is not a "loaded on request"
afterthought; §9.5 loads it every time §9.5 runs.

### 9.7 Restrict external database access again

§9.3–§9.5 above used Postgres's temporary **external** connection string.
Once done:

```powershell
Remove-Item Env:\SEMA_TMP_DB_URL
```

Then Render dashboard → `sema-pilot-db` → **Access Control**, remove any
external IP allow-list entries you added (or, if you never added one
beyond Render's default, confirm none exist). `sema-pilot`'s own connection
keeps working — it uses the **internal** hostname (§9.2), which is only
reachable from services in the same Render private network and is
unaffected by the external allow-list.

### 9.8 Restart or redeploy the Web Service

The dashboard env vars set in §9.4 (`POSTGRES_READONLY_USER`,
`POSTGRES_READONLY_PASSWORD`) trigger an automatic redeploy the moment you
save them — if you set both before this point, there's nothing further to
do here. (`POSTGRES_DB_INSURANCE` doesn't need this step at all anymore:
it's a fixed value in `render.yaml` itself, §9.6, applied whenever the
service deploys from the Blueprint rather than something you set by hand
per-deploy.) Otherwise: dashboard → `sema-pilot` → **Manual Deploy → Deploy
latest commit** (or **Restart** if only env vars changed, no new commit).
Wait for the deploy to report healthy (`/healthz`, §6) before moving to
§9.9.

### 9.9 Verify each tenant independently through SEMA

The database-level checks already ran in §9.5, while external access was
still open — this step is the application-level counterpart, through the
now-redeployed app itself, confirming `client_id` switching can't fall back
from one tenant to the other (enforced in code, `api/main.py`'s
`_resolve_client`, not just by the database being physically separate):

1. Open the deployed app, switch the client selector between "E-Commerce"
   and "Auto Insurance", and confirm each shows ITS OWN data (revenue/
   orders for ecommerce, policies/claims for insurance) — never the other
   tenant's numbers, never a blank/error state for either.
2. `curl https://<your-domain>/api/clients -H "X-API-Key: <your key>"` →
   confirm both `ecommerce` and `insurance` are listed.
3. `curl` gets awkward with a JSON body once PowerShell's own quoting rules
   are in play — `Invoke-RestMethod` (PowerShell-native) avoids that:
   ```powershell
   try {
       Invoke-RestMethod -Method Post -Uri "https://<your-domain>/api/client" `
         -Headers @{ "X-API-Key" = "<your key>" } `
         -ContentType "application/json" `
         -Body '{"client_id":"not-a-real-client"}'
   } catch {
       $_.Exception.Response.StatusCode.value__   # expect: 404
   }
   ```
   Never a silent fallback to either real tenant's data.

### 9.10 Configure the Render environment variables

Every `sync: false` var in `render.yaml` (§9.4 above, plus §9.11–§9.13
below) is set from the `sema-pilot` service's dashboard → **Environment**
tab, never by editing `render.yaml` with real values (that file is
committed to git). `POSTGRES_DB_INSURANCE` (§9.6) is the one exception —
it's a fixed, non-secret value declared directly in `render.yaml`, so
there's no dashboard entry to make for it.

### 9.11 Generate `SEMA_API_KEY`

Any high-entropy random string — this is the internal-pilot access-gate
value (§0), not a cryptographic key with a required format:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 9.12 Generate and validate `SEMA_SECRETS_KEY`

Must be a valid Fernet key specifically (`sema_core/settings.py`'s
`validate_for_production` checks this and refuses to boot otherwise):

```powershell
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Render's own "Generate" button on a text env var field does not know this
constraint** — it produces an arbitrary random string, not necessarily
Fernet-compatible. Always generate this one with the command above and
paste the result in; don't rely on the dashboard's generic generator for
this specific variable.

Never paste either generated value into chat, an issue, or a commit — enter
them directly in the Render dashboard's Environment tab.

### 9.13 Set `SEMA_PUBLIC_URL`

Unknown until the first deploy assigns your `*.onrender.com` URL (this is
why it's `sync: false` rather than guessed at in `render.yaml`). After the
first successful deploy: dashboard → Environment → set `SEMA_PUBLIC_URL` to
that exact URL (no trailing slash) → the resulting env change triggers a
redeploy automatically. Until this is set, CORS will reject the frontend's
own requests (§5).

### 9.14 Verify disk persistence

After the app is up with real data in it (a conversation, an uploaded
logo, a published semantic-model edit):

1. Dashboard → `sema-pilot` → **Manual Deploy → Restart** (a restart, not a
   rebuild) — confirm the conversation/logo/semantic edit are still there.
2. Trigger a real redeploy (push a commit, or **Manual Deploy → Deploy
   latest commit**) — confirm again. This exercises `sema_core.
   persist_bootstrap`'s "don't overwrite an already-seeded disk" path for
   real, not just the "first boot seeds it" path a restart alone doesn't
   touch.

### 9.15 Rotate the internal access key

Dashboard → Environment → change `SEMA_API_KEY` → save (triggers a
redeploy). Every existing browser tab's stored key (`sessionStorage`) stops
matching immediately: the next request any of them make gets a `401`,
which the frontend's gate (`lib/pilotAccess.ts`'s `revokeAccess`) turns into
"clear the stored key, show the access screen again" automatically — no
separate client-side rotation step needed. Share the new key with the pilot
group through whatever channel you'd share any short-lived secret (not
email in plaintext if you can avoid it).

### 9.16 The explicit upgrade gate before an external pilot

Everything in this document — including the access-key gate — targets an
**internal, trusted-group** pilot. Before inviting real external customers,
all of the following must ship first (`auth_login_prompt.md` Parts A+B):

- Real login and sessions (the email one-time-code + SSO flow the mocked
  `/login` page already has the UI shell for) — replacing the mock identity
  in `sema_core/current_user.py` entirely.
- Per-user authorization actually enforced server-side (today's
  `require_client_admin` etc. already have the shape; they're checking a
  MOCKED identity).
- Proven tenant isolation under real multi-org traffic, not just the
  single-org assumptions this pilot exercises.
- **No shared access key as the customer-facing authentication mechanism**
  — `SEMA_API_KEY` must go back to being an internal/infra concern (or be
  removed entirely) once real per-user auth exists; it must never be handed
  to an external customer as "their login."
