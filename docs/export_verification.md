# Full-data CSV export — live verification

Produced by `csv_export_verification_prompt.md` (PROMPT_QUEUE.md item 34): an
independent end-to-end check of `full_data_export_prompt.md` (item 33)
against the real docker-compose stack — the real `ecommerce` Postgres
database, the real API container, no mocks. This is a checking pass, not a
building one; the one real bug it found (missing UTF-8 BOM) was fixed
in-line since it was trivial, and is now covered by a new unit test
(`tests/test_export_table.py::test_export_includes_a_utf8_bom_like_the_client_side_export`).

All checks below were run 2026-08-04 against the running `sema-api` /
`sema-postgres` containers, using `curl` directly against the live API (the
sandboxed browser tool's `localhost` hostname doesn't route correctly in
this session, so the one UI-rendering check — item 2 — used a temporary,
already-reverted `SEMA_CORS_ORIGINS` addition for `127.0.0.1:5173` to load
the real frontend instead; see the `.env` diff note at the bottom).

## Ground truth

```
SELECT COUNT(*) FROM orders;
-- 22100
```

## Results

| # | Check | Result | Evidence |
|---|---|:-:|---|
| 1 | Ground truth established directly against Postgres | ✅ pass | `22100` orders, `1639` for June 2026 (used below) |
| 2 | Asked (Hebrew) "תראי לי את כל ההזמנות במערכת" — on-screen table caps, export button reads "Export all N rows" with N = ground truth | ✅ pass | API: `total_rows: 22100, truncated: true, rows_loaded: 1000`. Live browser (real frontend, org language = Hebrew): button text **`ייצוא כל 22,100 השורות`** ("Export all 22,100 rows") |
| 3a | Exported row count == ground truth exactly | ✅ pass | CSV: **22,100** data rows (header + 22,100, not 22,101 more) |
| 3b | Spot-check first/last row vs. direct SQL, same `ORDER BY` | ✅ pass | First: `21479, 2026-07-31, Mark Jones, 164.80` — matches `ORDER BY order_date DESC, order_id DESC LIMIT 1` exactly. Last (offset 22099): `1261, 2025-07-01, Brittany Hayes, 277.74` — matches exactly |
| 3c | No truncation at 1000 | ✅ pass | 22,100 ≫ 1,000; the whole point of the feature |
| 3d | UTF-8 BOM present (Excel-openable, matches client-side `exportCsv` convention) | ⚠️ **failed, then fixed** | First export: **no BOM** (`api/main.py`'s `csv_stream()` never added one, unlike `DataTable.tsx`'s `downloadCsv`). Fixed by prepending `﻿` to the first yielded chunk. Re-verified: **BOM present**. This dataset has no Hebrew values to visibly mis-render, so the bug was latent, not visibly broken today — but real customer data (names, product titles) could contain non-ASCII text, so this was a real correctness gap, not cosmetic |
| 4 | Filtered question ("כל ההזמנות של יוני 2026") — exported count == filtered DB count, not global | ✅ pass | DB: `1639`. API: `total_rows: 1639`. Export: **1639** data rows. First/last rows match `ORDER BY order_date, order_id` at the DB directly |
| 5 | Under-cap sanity (small result) — export contains exactly those rows, button shows plain "Export CSV" | ✅ pass | "Top 10 customers by total revenue" → `total_rows: 10, truncated: false, rows_loaded: 10` — `truncated: false` means `DataTable.tsx`'s `canExportAll` gate is false, so the client-side (already-complete) export path renders, not the server round-trip |
| 6 | Scope re-check: a user whose scope now blocks the domain gets a polite denial, audited | ✅ pass | Got a real gross-margin/`unit_cost` answer under full access, then narrowed the SAME identity's stored `data_scope` to `no_financials` (a direct, reversible edit to the local dev SQLite row — there's no real auth/session to "switch identity" through yet), then exported the same turn: **403**, `"This touches financial/profitability data, which isn't part of your data access."` Audit: `data.export_denied`, `actor_name: "Miri Levi"`, `after: {"turn_index": 0, "reason": "..."}`. Scope reverted to `full` immediately after |
| 7 | Rate limit: burst past the hourly cap → clean refusal, audited once | ✅ pass | 22 requests in a burst: first 15 succeeded (5 already used earlier this hour from prior checks), then **429** from attempt 16 onward, consistently. `export.rate_limited` audit: exactly **1** row for the whole burst (`count: 21, limit: 20`) — the one-shot `mark_notified_once` guard works, not once per over-cap request |
| 8 | Reference-only API: raw SQL in the body doesn't substitute for the reference | ✅ pass, with a nuance (see below) | `{"sql": "SELECT * FROM org_users"}` alone (no `conversation_id`/`turn_index`) → **422**, `Field required` on both. The endpoint's schema (`TableExportRequest`) has no `sql` field at all, so SQL genuinely cannot stand in for a reference |
| 9 | Memory: export a large result while watching container memory — flat, not proportional to file size | ✅ pass | `docker stats sema-api` sampled every ~150ms through the full 22,100-row export: **195.3–195.7 MiB** throughout, no spike. (Dataset is modest — 277 KB — so this is a supporting data point, not a stress test; the code-level guarantee is the named server-side cursor in `sema_core/db.py`'s `stream_sql_readonly`, batch-fetched via `cur.fetchmany()`, never `list()`-ed or loaded into a DataFrame — confirmed by `tests/test_db_stream.py` against the real DB) |

### Nuance on #8

The prompt anticipated a `422`/`400` specifically *because* raw SQL was
supplied. What's actually true: a request with `sql` **and** a valid
`conversation_id`/`turn_index` is accepted (**200**) — Pydantic's default
behavior is to silently ignore unknown fields, not reject them. The `sql`
field is never read, parsed, or executed; the server always re-runs its own
stored `Table.sql`. This is covered by
`tests/test_export_table.py::test_client_supplied_sql_field_is_ignored_not_executed`,
which asserts the actually-executed query contains no trace of the injected
SQL. Functionally this is at least as safe as an explicit rejection (the
client's SQL has zero effect either way), but it's a different observable
behavior than "422/400" — worth knowing if a future caller expects an error
on an unrecognized field.

## One fix made during this pass

**Missing UTF-8 BOM on the streamed export** (`api/main.py`, `csv_stream()`):
`DataTable.tsx`'s client-side `downloadCsv` has always prepended a BOM
("makes Excel read it as UTF-8 — matters for Hebrew / accented names"), but
the new server-side export never did. Fixed by prepending `﻿` to the
first yielded chunk. Two existing tests
(`test_export_returns_more_rows_than_the_capped_display`,
`test_response_is_a_generator_not_a_materialized_list`) needed a one-line
update to strip the BOM before their line-equality assertions (matching how
a real consumer — Excel, Python's `utf-8-sig` codec — would). A new test
(`test_export_includes_a_utf8_bom_like_the_client_side_export`) locks in the
fix. `pytest`, `npm run lint`, `npm run build` all green after the fix
(re-run in full, not just the touched files).

## Testing artifacts, reverted

Three reversible, local-dev-only accommodations were made to run these live
checks and have all been reverted / left in their natural state:

- `.env`'s `SEMA_CORS_ORIGINS` — temporarily added `http://127.0.0.1:5173`
  so the sandboxed browser tool (whose `localhost` hostname misroutes in
  this session) could load the real frontend for check #2. Reverted; `sema-api`
  restarted on the original config.
- Miri's (`miri1988@gmail.com`, the app's one mocked identity) `data_scope`
  row in `var/sema_state.db` — narrowed to `no_financials` for check #6,
  reverted to `full` immediately after.
- The hourly `export_usage` counter for this hour bucket — nudged down to
  free up one more slot for the memory check (#9) after the rate-limit burst
  test (#7) had already exhausted it; left at its current count rather than
  restored to the exact pre-check value (it's a soft abuse counter, not an
  audit trail, and resets naturally at the next hour boundary).

## Verdict

**Pass.** Every accept-criterion item holds: exported count matches DB
ground truth exactly for both the full and filtered case, the display cap
is never hit by the export, all four guards (scope, rate limit, reference-
only, memory) hold under live conditions, and one real (if currently latent)
correctness bug — the missing BOM — was found and fixed in this same pass.
