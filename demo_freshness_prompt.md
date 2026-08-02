# Task: Demo data never ages — relative END_DATE in the generator

Today `data/generate_data.py` has `END_DATE = date(2026, 6, 30)` (line ~67). The demo data ends there forever, so "data age" grows daily, "this month" questions go empty over time, and the daily brief loses relevance. Fix: the demo should always look fresh.

1. `END_DATE` becomes relative: yesterday (`date.today() - timedelta(days=1)`), overridable via env/CLI arg (`--end-date`) for reproducible test fixtures. `START_DATE` shifts to keep the same total span. `CHURN_CUTOFF_DATE` already derives from END_DATE — verify all other derived dates (campaign windows, monthly targets, seasonal patterns like Black Friday placement) also derive relative and stay coherent (Black Friday must still land on actual late-November dates within the span, not shift randomly).
2. Keep generation deterministic for a GIVEN end date (same seed → same data), so tests with a pinned `--end-date` stay stable.
3. Apply the same change to the insurance generator (`data/insurance/`).
4. **Semantic knowledge alignment (careful):** `sql/semantic/knowledge.yaml` items reference concrete dates chosen to match the data (checkout-outage incident on a real low-revenue day, pricing-update note). After making dates relative, either (a) make the generator EMIT/refresh these knowledge dates as part of seeding so they always match, or (b) regenerate the knowledge items' date_ranges relative to END_DATE with the generator planting matching anomalies. Choose one, document it — the incident-caveat behavior (test exists) must keep working.
5. Regenerate + reload both tenants' demo data locally; verify: data age shows "1 day ago" on the Data sources screen, the daily brief pulse has fresh days, "מה קרה החודש?" returns real numbers, and the existing eval questions still behave.
6. Update any test/eval pinned to 2026-06 dates to use the pinned `--end-date` fixture path instead of literals where feasible.

Accept: [ ] Fresh seed → data age "1 day ago", brief alive, incident caveat still fires on its (relative) window; `pytest`, lint, build green.
