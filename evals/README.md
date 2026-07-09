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
