# Prompt: Extend Both Synthetic Databases to Today

Copy everything below this line into Claude Code.

---

## Goal

Extend both synthetic datasets — **ecommerce** (`data/generate_data.py`)
and **insurance** (`data/insurance/generate_data.py`) — so they run up to
today (**2026-07-16**), strictly following the existing generator logic and
conventions, and add a few new *plausible, documented* business scenarios
in the newly generated months. Then reload both databases and make sure
nothing downstream (docs, evals, semantic layer) silently breaks.

## Current state (verify before changing)

- Ecommerce: `SEED = 42`, `START_DATE = 2025-06-01`, `END_DATE = 2026-05-31`.
  Ground-truth patterns: `MONTH_SEASONALITY` (Nov/Dec peak), the March-2026
  revenue dip, the VIP Pareto, and a churn-risk cohort defined **relative
  to END_DATE** (last 90 days inactive).
- Insurance: `SEED = 42`, `START_DATE = 2024-01-01`, `END_DATE = 2026-05-31`,
  `TODAY = 2026-06-16`. Ground truth: Jan-2026 weather-event loss-ratio
  spike in the North region.

## Task 1 — extend the date ranges

- Both generators: `END_DATE = 2026-06-30`, i.e. **full months only**,
  keeping the project's existing convention ("ending the month before
  today"). Do NOT generate a partial July — partial months poison every
  MoM comparison the agent makes.
- Insurance: `TODAY = 2026-07-16` (it drives claim-settlement status).
- Keep `SEED = 42` and keep dates as explicit constants — do NOT make
  END_DATE dynamic (`date.today()`); reproducibility of the dataset against
  the documented ground truth matters more than auto-freshness.
- Check for hidden END_DATE dependencies before running: the churn cutoff
  windows, campaign windows, and any constant derived from END_DATE now
  shift by one month. List them all first.

## Task 2 — new scenarios in the new months (the interesting part)

Add scenarios ONLY in the newly generated period, so all existing ground
truth (March dip, Jan weather event, seasonality) stays byte-comparable in
spirit. Each scenario must follow the existing pattern-injection style:
named constants at the top, a comment block explaining the business story,
and a line in the end-of-run printed checklist.

**Ecommerce (implement all three):**

1. **June recovery with a catch** — overall revenue in June 2026 recovers
   from the spring level, BUT the recovery is driven by a "Summer Sale"
   campaign with heavy discounting: orders up, AOV *down* ~8-10%,
   campaign ROI mediocre. Story the agent should find: "growth, but bought
   growth."
2. **Category price increase** — one category (pick Electronics) raises
   prices ~7% from June 1: its AOV up, its conversion rate down, revenue
   roughly flat. A classic "was the price increase worth it?" question.
3. **Email channel improvement** — Email traffic conversion rate improves
   noticeably in June (e.g. a new flow), making it the best-performing
   channel that month. Gives "which channel should I invest in?" a
   time-sensitive answer.

**Insurance (implement both):**

1. **June-2026 heatwave event** — a second, smaller catastrophe: extra
   Weather/Fire claims in the **South** region in June 2026 (different
   region + smaller magnitude than Jan, so "compare the two events" is a
   real question).
2. **Rate action** — a ~5% written-premium rate increase effective
   June 2026 renewals, with a small retention dip in the renewing cohort.
   Sets up "did the rate increase help the loss ratio, and what did it
   cost us in retention?"

If you think a scenario conflicts with existing logic, say so and propose
an alternative — don't silently bend the existing patterns.

## Task 3 — reload and verify

1. Regenerate both datasets; run both loaders
   (`data/load_data.py`, `data/insurance/load_data.py`) against the Docker
   Postgres (see CLAUDE.md "Running SEMA Locally").
2. Verify each injected scenario with direct SQL (use
   `sql/validation_queries.sql` style): print the numbers that prove each
   story exists in the DB, old ones AND new ones.
3. **Re-verify documented figures** — extending the range changes computed
   stats. Specifically re-check the VIP top-5% revenue share (CLAUDE.md
   documents 48.5% verified against the old range) and the row counts
   in `data/README.md`. Update both docs with the new verified numbers.
4. Update `data/README.md` (and the insurance equivalent docstring) with
   the new date range and a ground-truth section per new scenario — these
   docs are the answer key for evals.
5. Run `pytest` (should be unaffected — flag it if not), then run
   `evals/run_evals.py` for both clients. Expect churn-window and
   "last month" golden answers to shift; update `evals/golden/*.yaml`
   assertions where the *correct* answer legitimately changed — never
   loosen an assertion just to make it pass.

## Rules

- Follow the existing code style of the generators: named constants,
  "why" comments for every injected pattern, printed checklist at the end.
- No schema changes, no new dependencies, no changes to `sema_core/`.
- Show me the plan (constants you'll add/change, files touched) before
  implementing. Do not commit — show `git diff` and wait for approval.
- Finish with a short report: date ranges, scenario verification numbers,
  updated doc figures, eval results.
