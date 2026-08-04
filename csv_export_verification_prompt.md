# Task: VERIFICATION — does the CSV export really deliver all 22,100 rows?

Independent end-to-end verification of `full_data_export_prompt.md` (run AFTER it is done). This is a checking task, not a building task: verify against the LIVE dev stack and the REAL database, produce evidence, fix nothing beyond trivial issues found (report anything bigger).

## Live end-to-end check (the core)

1. Establish ground truth directly: `SELECT COUNT(*) FROM orders` on the live ecommerce Postgres (record the exact number — ~22,100, may differ after reseed).
2. In the app, ask (Hebrew): "תראי לי את כל ההזמנות במערכת" — confirm the on-screen table caps at the display limit and the export button reads "Export all N rows" with N equal to the ground-truth count.
3. Trigger the export. Verify the downloaded CSV: row count (minus header) EQUALS the ground-truth count exactly; spot-check first/last rows against direct SQL (same ORDER BY); no truncation at 1000; file encoding UTF-8 with Hebrew customer-facing values intact (if any) and Excel-openable (BOM per existing CSV conventions).
4. Repeat with a FILTERED question ("כל ההזמנות של יוני") — exported count equals the filtered DB count, not the global one.
5. Under-cap sanity: a small result (e.g. top 10 customers) — export contains exactly those rows, button shows plain "Export CSV".

## Guards verification

6. Scope re-check: as a user whose data scope blocks the queried domain (switch the mock identity's scope), the export endpoint denies politely and the denial lands in the Audit log.
7. Rate limit: burst past the hourly export limit → clean refusal, audited once.
8. Reference-only API: attempt a direct POST with raw SQL in the body → rejected (422/400), proving the no-client-SQL rule.
9. Memory behavior: export the full table while watching the API container's memory (docker stats) — flat-ish profile consistent with streaming, not a spike proportional to file size.

## Output

`docs/export_verification.md` — a short evidence report: ground-truth count, exported count, filtered case, all guard results, memory observation, pass/fail per item. Any failure → leave the queue item in_progress and list exactly what failed.

Accept: [ ] Evidence report shows exported rows == DB count for full and filtered cases, all guards hold, streaming confirmed. `pytest`, lint, build untouched-green.
