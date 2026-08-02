# Task: Time-series questions get LINE charts, not bars

User rule (July 2026, screenshot: "הכנסות Accessories לפי חודש" rendered as bars): when the user asks about dates, periods, or trends — anything whose x-axis is TIME (days/weeks/months/quarters) — the chart must be a line chart. Bars are for categorical comparisons (revenue by category, top products, by channel).

1. **Agent layer (primary fix):** in `prompts.py`'s chart guidance, add an explicit type rule: x-axis is a date/period sequence → `type: line`; x-axis is categories/entities → `type: bar`. The rule applies in main answers AND drill threads. If the chart schema in `present_answer` doesn't carry a `type` field yet, add it (`line`/`bar`, backward-compatible default `bar` for stored answers).
2. **Frontend:** render `type: line` with the existing charting stack — line with point markers, same tint/tokens as bars, value labels only on hover/last point (a line with a label per point gets noisy; follow the existing sparkline conventions where sensible). Time axis labels keep current formatting.
3. **Deterministic safety net:** server-side, when binding the chart to a result whose x column is a date/month type and the model still said `bar`, coerce to `line` (log it) — the rule shouldn't depend on model compliance alone.
4. Old conversations keep rendering as stored (bars) — no migration.
5. Evals/tests: "הכנסות לפי חודש" → line; "הכנסות לפי קטגוריה" → bar; coercion test for the safety net; frontend renders both types.

Accept: [ ] Trend question (Hebrew + English) renders a line chart in main chat and drill; categorical stays bar; safety net covered by test; `pytest`, lint, build green.
