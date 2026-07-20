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
- `expects_components: [table|chart|kpi]` -- the answer rendered each named
  component (catches "answered in prose without the expected widget").
- `faithful: true` -- no *large* number in the prose (>= 10,000, so years and
  percentages are ignored) is ungrounded: every one must match a KPI value or
  a result-table cell within 1%. Catches hallucinated revenue/count figures.
- `kpi_formats: [{label_contains, format}]` -- a KPI whose label contains the
  substring must carry that `format` (e.g. an ID metric must be `text`, so the
  UI never renders it with thousands separators).
- `mode: answer|clarification|cannot_answer|off_topic` -- the response mode,
  e.g. an ambiguous question should `clarification`, not guess.

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
