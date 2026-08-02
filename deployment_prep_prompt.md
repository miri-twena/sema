# Task: Production readiness — code-side prep for first real deployment

Code-only prep so the repo deploys cleanly to a Docker platform (Railway/Render) with HTTPS. Companion to the human checklist (`SEMA-Deployment-Checklist.pdf`). NO auth work here — that stays in `auth_login_prompt.md` Parts A+B (blocked until the host exists). Follow `AGENTS.md`.

1. **Production container(s):** a production-grade Dockerfile path — frontend built (`npm run build`) and served either by the API (static mount) or as a separate static service; document both options in the compose/README and pick ONE as default (prefer API-served for a single-service pilot: fewer moving parts, no CORS). Multi-stage build, no dev servers, no source maps required, `NODE_ENV=production`.
2. **Environment contract:** complete `.env.example` with EVERY variable the app reads, grouped and commented: LLM key, Postgres (both tenants), `SEMA_SECRETS_KEY`, `SEMA_AUTH_MODE`, `SEMA_RETENTION_ENABLED`, SMTP_* (placeholder values), and a new `SEMA_ENV=dev|production`. Startup validation: in `production`, fail fast with a clear message if a required var is missing.
3. **Demo/dev endpoint hardening:** audit all routes and dev affordances for anything that must not exist in production — seed/reset endpoints, the login dev-state panel, any internal/dev status-transition endpoints (e.g. source_requests transitions), mock-identity conveniences. Gate them on `SEMA_ENV != production` (server-side, not build-time only). List every gated route in the final report.
4. **Cookie/CORS/origin config:** base URL from env (`SEMA_PUBLIC_URL`); CORS allowlist derived from it; cookie settings ready for HTTPS (Secure flag active in production) — WITHOUT implementing sessions (auth comes later; this is the configuration surface it will use).
5. **Health + logs:** `GET /healthz` (checks DB reachability, returns version/commit if available, no auth); production log level via env; no secrets ever logged (add a test that greps captured logs from a request cycle for the configured secret values).
6. **Persistence notes:** confirm everything stateful lives under `var/` (SQLite state, logos, uploads) and document the single-volume mount requirement in the README's deployment section; verify a container restart with a mounted `var/` loses nothing (test locally).
7. **Docs:** a `docs/deployment.md` — platform-agnostic steps matching the checklist PDF (services, env vars, volume, domain, smoke test). Keep it short and factual.
8. Tests: env validation (missing var in production mode fails, dev mode doesn't), gated endpoints return 404 in production mode, healthz works in both modes. `pytest`, `npm run lint`, `npm run build` green.

Accept:
- [ ] `docker compose -f <prod compose> up` locally serves the full app on one port, production mode, demo endpoints 404, healthz green.
- [ ] `.env.example` complete; startup fails informatively on missing production config.
- [ ] Restart with mounted `var/` preserves state; README/deployment doc updated.
