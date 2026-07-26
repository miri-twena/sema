# Task: Rebuild the Daily Brief as a two-layer, daily-fresh section

Rework ONLY the existing "Daily brief" section at the top of the home screen (`frontend/src/components/HomeDashboard.tsx`). Section title stays **"Daily brief"** exactly as today; the rest of the home page is untouched. Read `AGENTS.md`; backend in `sema_core/` + `api/`, frontend in `frontend/`.

## Concept

Separate freshness from insight:

- **Layer 1 — Daily pulse (always renders, changes every day):** yesterday's key numbers with 14-day sparklines. Honest status, no pretense of insight.
- **Layer 2 — Attention cards (event-driven, render only past thresholds):** ranked findings. On a quiet day: a single calm "all normal" line — never filler cards.

No LLM calls anywhere in this path; deterministic SQL only, read-only role, same query-layer patterns as `/api/overview` and `/api/alerts`. "Yesterday" and "as of" derive from `MAX(order_date)` in the data, never the server clock.

## Backend — `GET /api/brief?client_id=...`

Response:

```json
{
  "as_of": "2026-06-30",
  "pulse": [
    { "metric": "revenue", "label": "Yesterday revenue", "value": 54885, "format": "currency",
      "spark": [41200, 39800, "... 14 daily values ..."],
      "status": "above", "status_label": "+25% vs typical Tue" },
    { "metric": "orders", "label": "Orders", "value": 89, "format": "number",
      "spark": ["..."], "status": "normal", "status_label": "In normal range" },
    { "metric": "conversion", "label": "Conversion", "value": 2.4, "format": "percent",
      "spark": ["..."], "status": "normal", "status_label": "In normal range" }
  ],
  "insights": [
    { "kind": "campaign_negative_roi", "icon": "warning",
      "headline": "Summer Sale campaign has run at negative ROI for 14 days",
      "detail": "Spend $8,400 against $6,100 attributed revenue since Jun 16.",
      "severity": 2 }
  ]
}
```

**Pulse:** revenue, orders, conversion (sessions data) for the last complete day + previous 14 days. `status` = deviation vs the same-weekday average of the prior 4 weeks: `above`/`below` past ±20%, else `normal`.

**Insight generators** (each a SQL check; compute all, rank, return top 3 max):

1. `yesterday_anomaly` — pulse metric past ±20% (severity ∝ deviation).
2. `campaign_negative_roi` — campaign with negative ROI ≥ 14 consecutive days.
3. `vip_inactive` — VIP customers (existing semantic definition) with no order in 60+ days; include their trailing-12-month revenue in `detail`.
4. `record_day` — yesterday was the best/worst day for a metric since ≥ 60 days.
5. `product_rank_shift` — a product entered the top 3 sellers this month that wasn't there last month.
6. `mtd_pace` — month-to-date vs same days of previous month, ONLY when |delta| ≥ 10% (it's an insight only when notable). Skip during the first 2 days of a month.

Diversity rule: max one insight per underlying metric. Empty `insights` array = quiet day. Cache per client per `as_of` date if a caching pattern exists; otherwise skip.

## Frontend

Replace the current Daily Brief card row's internals; keep the section header row ("Daily brief" label + existing icon) as is, and add `As of {date}` right-aligned in the header (remove per-card as-of).

1. **Pulse strip:** grid of compact stat tiles — label (12px muted), value (20px medium), inline SVG sparkline (~64×24, polyline, `stroke` colored by status: success when `above`, danger when `below`, muted gray when `normal`), status line under the value (11px; colored only when non-normal). Tiles are NOT clickable drill targets unless trivially wired to the existing `onDrill`.
2. **Attention cards:** vertical list, each: lucide icon by `icon` field (`warning` → `AlertTriangle` in warning color, `customers` → user icon, etc.), one bold headline line, one small muted detail line, "Tell me more →" using the existing brief CTA behavior (question built server-side or via existing drill flow — no client-side string assembly).
3. **Quiet state:** when `insights` is empty — single row, check icon in success color, "All metrics in their normal range today". The row replaces the cards, pulse still shows.
4. Loading: pulse-skeleton like Business overview. Endpoint error: hide the whole section (existing convention).
5. Everything else on the home page (greeting, chips, Business overview, Top recommendation, Start a conversation) stays exactly as is.

## Constraints

- RTL-safe: logical properties; `unicodeBidi: "plaintext"` on free-text lines.
- Sparkline SVGs: `aria-hidden`, no library — plain polyline.
- Tests: generator thresholds (anomaly ±20%, quiet day, diversity rule, first-2-days guard), pulse same-weekday baseline math. Run `pytest`, `npm run lint`, `npm run build`.

## Acceptance

- [ ] Pulse strip shows every day with fresh values + sparklines; normal days say "In normal range" in muted gray.
- [ ] Attention cards appear only past thresholds, max 3, one per metric; quiet days show the single calm line.
- [ ] Section header reads "Daily brief" with one right-aligned "As of" date; no per-card as-of.
- [ ] Rest of the home page unchanged.
- [ ] `pytest`, `npm run lint`, `npm run build` pass.
