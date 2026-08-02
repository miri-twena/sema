# SEMA golden-question evals

A regression suite for the *agent's answers*, not the code. `pytest` proves
the plumbing works with fakes (no DB, no API key); this proves the agent
still tells the right story against the real dataset after you touch the
system prompt, the model, or a semantic-layer YAML.

## Run it

Needs the Postgres container running (`docker compose up -d`) and
`ANTHROPIC_API_KEY` set in `.env` -- it makes real, billed LLM calls.

```
.venv\Scripts\python.exe evals\run_evals.py            # defaults to ecommerce
.venv\Scripts\python.exe evals\run_evals.py insurance   # once insurance has a golden file
```

Prints a PASS/FAIL line per question (with the failing assertion's detail),
then a token/cost summary pulled from the same structured log line
(`obs.py`'s `agent_run` event) production logging already emits.

## How a question is scored

Each entry in `evals/golden/<client>.yaml` is a question plus assertions
checked against `wiring.get_response()`'s response dict:

- `contains_any: [...]` -- at least one phrase appears in the answer text
  (case-insensitive).
- `direction: up | down` -- the answer uses an up/down word (crude but
  cheap; catches a prompt regression that inverts a trend).
- `numeric_within: [{value, tolerance_pct}]` -- some number in the answer
  text or a KPI value is within `tolerance_pct` of `value`.
- `expects_sql: true` -- `sql_used` is non-empty, i.e. the agent actually
  queried the database rather than answering from thin air.
- `expects_no_sql: true` -- the inverse: no query ran. For off-topic cases,
  which must ground their redirect only in context already in the prompt.
- `expects_components: [table|chart|kpi]` -- the answer rendered each named
  component (catches "answered in prose without the expected widget").
- `faithful: true` -- no *large* number in the prose (>= 10,000, so years and
  percentages are ignored) is ungrounded: every one must match a KPI value or
  a result-table cell within 1%. Catches hallucinated revenue/count figures.
- `kpi_formats: [{label_contains, format}]` -- a KPI whose label contains the
  substring must carry that `format` (e.g. an ID metric must be `text`, so the
  UI never renders it with thousands separators).
- `expects_structured_actions: true` -- every `recommended_actions` entry is
  the structured `{action, why, expected_impact, effort}` shape (not a bare
  legacy string) and at least one carries a `why`. Catches a prompt
  regression that reverts the recommendation engine to generic strings.
- `no_truism_actions: true` -- no recommended action matches the harness's
  built-in filler-phrase blocklist (`_TRUISM_PHRASES` in run_evals.py) --
  e.g. "improve customer retention" with nothing specific behind it.
- `mode: answer|clarification|cannot_answer|off_topic|access_denied` -- the
  response mode, e.g. an ambiguous question should `clarification`, not
  guess; a question outside the requester's data-access scope should
  `access_denied`, not a silent answer.
- `expects_chart_kind: line | bar | grouped_bar | donut` -- the returned
  chart's `kind` matches exactly (trend_line_charts_prompt.md: a time-axis
  question -- "revenue by month" -- must render `line`, a categorical one
  -- "revenue by category" -- `bar`/`grouped_bar`/`donut`). Fails if no
  chart was rendered at all.
- `summary_language: he | en` -- the `summary` field's dominant script (crude
  Hebrew-vs-Latin letter count, not a real language classifier) matches the
  given language. Meant for `drill` cases (below) where the parent turn and
  the drill-down's [SEMA-CONTEXT] text may be in a different language than
  THIS turn's question -- catches the model anchoring the summary to the
  wrong one.

### Drill-down cases

A case can carry an optional `drill` block to simulate a follow-up asked
from a drill-down panel, instead of a fresh standalone question:

```yaml
- id: my_drill_case
  question: "..."          # the CURRENT turn, asked from the drill panel
  drill:
    parent_question: "..."   # the main-chat question that produced the widget
    parent_answer: "..."     # its answer text (becomes one prior history turn)
    context_kind: kpi          # kpi | chart | table | action
    context_title: "..."      # the widget's title, exactly as the UI shows it
    context_detail: "..."     # the widget's detail text (see build_drill_context)
  assertions: {...}
```

The harness turns this into the SAME shape a real drill-down produces: one
prior history turn (`parent_question`/`parent_answer`, Claude API format) plus
`internal_context` built via the real `sema_core.agent.prompts.build_drill_context`
-- never a hand-written free-text context block, so the eval exercises the
exact code path production uses.

> **Formatting note.** The eval harness grades the *response dict*, so it can
> only check the data-level side of formatting (a KPI's `format`, a full result
> table vs. a prose summary). The actual rendering rules -- comma-less IDs, the
> `K`/`M` abbreviation, SQL shown LTR, ghost-text input, per-component Copy --
> live in the React layer and are covered by `frontend/` component tests, not
> here.

## Run-to-run diff (and CI)

Each run writes `{case_id: passed}` to `evals/.last_run/<client>.json`
(gitignored) and, on the next run, prints a **diff**: which cases regressed
(were passing, now failing), got fixed, were added, or removed. **A regression
fails the run** (exit 1) even if the absolute pass count looks fine -- so a
prompt/model change that breaks a previously-green case is caught explicitly.

This is a **nightly / pre-merge gate, not a per-commit CI check**: every case
makes a real, billed LLM call against the live database, so it can't run in an
ordinary sandboxed CI job. Wire it into a scheduled job (or a manual
pre-release step) with `ANTHROPIC_API_KEY` and the Postgres container
available; the exit code gates the pipeline.

The pure scoring/diff logic (no DB, no key) is unit-tested in
`tests/test_evals_scoring.py`, which *does* run in ordinary CI.

## Adding a question

1. **Verify the expected value against the live database first** -- don't
   copy a number from `data/README.md` without checking; its summary
   numbers describe the data generator's intent, not always the exact
   metric a question asks (see the note at the top of
   `evals/golden/ecommerce.yaml` for a case where they diverged).
2. Add an entry with a unique `id`, the `question` text, and 1-3 loose
   assertions -- loose on purpose, since the model's exact phrasing varies
   run to run; you're checking it got the *story* right, not matching text.
3. Run `run_evals.py` a couple of times (LLM answers aren't fully
   deterministic) before trusting a new assertion.
