# Task: Seed the semantic layer's new sections with real content

The Semantic model screen and agent integration are fully built (`sema_core/semantic_*`, `api/main.py` semantic routes, `frontend/.../admin/semantic/`), but the new sections ship EMPTY: no `rules.yaml` / `knowledge.yaml` / `glossary.yaml` on disk for either tenant, no metric declares `synonyms`, and only `active_customers` declares `status`. This task is content, not features. Follow `AGENTS.md`.

## Ground rules

- Author the YAML files directly in `sql/semantic/` (e-commerce) and `sql/insurance/semantic/` (insurance tenant) — same schema the editor writes on publish (mirror the exact field names from `sema_core/semantic_editor.py` / `semantic_store.py` so a later publish round-trips cleanly). Then create a baseline version snapshot per tenant (`ensure_baseline`) so History shows v1 with this content.
- Every item must be TRUE for the demo databases — verify each SQL fragment / affected metric actually matches the schema and data (run the validate dry-run path or a quick query). No aspirational content that would make the agent cite false assumptions.
- Bilingual: `definition`/`description` fields in English (the agent answers in the user's language and needs canonical English), glossary carries both Hebrew and English terms.

## E-commerce tenant

1. **`rules.yaml` — 5 business rules**, each `{name, definition, logic?, applies_to, status: certified}`:
   - "Completed orders only": an order counts once status = completed; cancelled/refunded excluded → applies to revenue, aov, conversion_rate, revenue_by_category.
   - "Revenue is net of refunds": refunded amounts subtracted in the same period the refund occurred → revenue, gross_margin.
   - "VIP customer": lifetime spend threshold (use the actual threshold from `vip_customers.yaml`'s SQL) → vip_customers.
   - "Returning customer window": a customer is "returning" if a prior completed order exists any time before the period → returning_customers, churn_risk.
   - "Campaign ROI attribution": last-click, revenue attributed within the campaign window → campaign_roi.
2. **`knowledge.yaml` — 5 items** (dates must overlap ranges that exist in the demo data — check the data's date span first):
   - `recurring_event`: Black Friday + Cyber Monday week (recurrence: last week of November) — affects revenue, aov, conversion_rate.
   - `recurring_event`: Post-holiday returns spike (early January) — affects revenue (refund rule interaction).
   - `incident`: checkout outage on a specific date within the data (pick a real low-revenue day and note it as a plausible demo incident) — affects revenue, conversion_rate.
   - `incident`: marketing pixel misfire for a ~1-week window — affects campaign_roi (attribution undercount).
   - `note`: pricing update on a specific date (find a visible AOV shift in the data if one exists) — affects aov, gross_margin.
3. **`glossary.yaml` — ~12 entries**, Hebrew + English, each mapping to a canonical metric/entity. Include the ambiguous ones with explicit resolution: "מכירות"/"sales" → revenue (not order count); "רווח" → gross_margin (flag that net profit is not modeled); "לקוח חוזר" → returning_customers; "סל ממוצע"/"basket" → aov; "המרה" → conversion_rate; "נטישה" → churn_risk (customer-level, not cart abandonment — note the distinction); plus straightforward synonyms (GMV, turnover, מחזור, קטגוריות).
4. **Metrics:** add `status:` to all 10 (sensible mix — core metrics `certified`, churn_risk `draft`) and `synonyms: []` with 2-4 real synonyms each (Hebrew + English), consistent with the glossary.

## Insurance tenant

Same structure, smaller: 3 rules (e.g. "active policy" definition, "claim counts once approved", earned-vs-written premium), 2-3 knowledge items (regulatory change note, storm-event incident affecting claims), ~8 glossary entries (פוליסה/policy, תביעה/claim, פרמיה/premium, ביטול/lapse …), `status` + `synonyms` on all metrics. Verify against that tenant's actual metric files and schema.

## Verify (the point of the exercise)

- `pytest` (existing semantic tests must still pass — loader backward-compat).
- Dry-run: ask the agent (or run the eval harness) three questions against e-commerce and confirm: (a) a revenue question cites "Completed orders only" as an assumption; (b) a question whose range overlaps the checkout-outage incident gets the caveat; (c) "כמה מכירות היו החודש?" resolves via glossary to revenue without a clarification prompt.
- Semantic model screen shows the new content in all tabs; History shows baseline v1.

## Accept

- [ ] Both tenants have populated rules/knowledge/glossary YAMLs that validate and publish cleanly from the admin screen.
- [ ] All metrics carry status + synonyms; glossary and synonyms agree.
- [ ] The three dry-run behaviors above demonstrably work.
- [ ] `pytest`, lint, build pass.
