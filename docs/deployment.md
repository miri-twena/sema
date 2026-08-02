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
| `SEMA_API_KEY` | Empty = the entire API has NO authentication |
| `SEMA_PUBLIC_URL` | Drives the CORS allowlist |
| `POSTGRES_PASSWORD` / `POSTGRES_READONLY_PASSWORD` | Must not be the well-known local-dev defaults |

`SEMA_ENV=production` also makes cookies (once sessions exist) default to
`Secure`, and is what api/main.py's mock-identity warning above checks for.

## 4. Persistent storage — what MUST be on a volume

Everything stateful lives under two paths inside the container. Losing
either without a volume means losing real data on every restart/recreate:

- **`/app/var`** — a single SQLite file (`sema_state.db`) backing
  conversations, org users, org settings, the audit log, home-screen
  config, alerts, data-source connection/request/upload metadata, and
  answer feedback — plus `/app/var/logos` (uploaded org logos).
- **`/app/sql`** — the semantic model's `*.yaml` files
  (`sql/semantic/`, `sql/insurance/semantic/`). **Easy to miss**: these look
  like static config checked into git, but the admin panel's Publish/
  Restore flow (`sema_core/semantic_editor.py`) rewrites them on disk at
  runtime. Without this on a volume too, a published semantic-model change
  survives only until the container is recreated, then silently reverts to
  whatever was baked into the image.

`docker-compose.prod.yml` mounts both as named Docker volumes
(`sema_var_prod`, `sema_semantic_prod`); on a managed platform, mount its
persistent-disk equivalent at those same two container paths. Uploaded
CSV/xlsx row data does NOT need a volume — it's written into the tenant's
own Postgres database (already durable via that database's own storage),
only the upload's *metadata* lives in `/app/var`.

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
