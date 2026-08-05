# SEMA marketing website

Next.js (App Router), static export, bilingual (en/he). Separate workspace from
`frontend/` (the product app) — this only builds the public marketing site.

## Develop

```
npm install
npm run dev
```

## Build (static export)

```
npm run build
```

Output goes to `out/`, deployable to any static host.

## Product screenshots (`public/screens/`)

The "See SEMA in action" carousel uses real screenshots of the running product,
not mockups. Regenerate them whenever the product's UI changes meaningfully:

```
npm run capture-screens
```

This drives the actual dev stack with Playwright (`scripts/capture-screens.mjs`),
so `frontend`/`api`/`postgres` must be running first (`docker compose up -d` from
the repo root, or the individual dev servers). It forces the product's chrome to
English, captures the home dashboard, the daily brief, an existing seeded
conversation with a chart, and two admin screens (users, semantic model) at
1440×900 — and redacts anything that looks like an email address in the users
table before capturing, since that screen shows real org member emails.

If the dev stack isn't reachable, the script exits with an error instead of
producing placeholder images.
