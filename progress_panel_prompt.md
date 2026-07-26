# Task: Compact live-progress indicator

Files: `frontend/src/components/ProgressPanel.tsx`, `frontend/src/lib/progress.ts`, used by `TurnView.tsx`. Follow `AGENTS.md`.

Problem: progress renders one row per backend event — a retried query produces 4+ rows ("Running query 1", "Query 1 failed", "Running query 1", "completed — 1 rows returned"). Too noisy.

## Spec

1. Default view = ONE live status line: spinner + current stage label, replacing itself as stages change. No stacked list.
2. Derive stages by merging events in `progress.ts`: run/complete/fail of the same query = one stage with a state. Retry renders as the same stage labeled "retrying…" then ✓. Multiple queries → one stage "Running queries (n/total)".
3. User-language labels only: no row counts, no query numbers in the default line (e.g. "Fetching data…", Hebrew per existing `lang` handling). Technical detail stays in the post-answer Evidence panel / NoticeBadges (already implemented — don't duplicate).
4. A stage shows only if it lasts >1.5s (timer before first paint of a new label).
5. Chevron toggle beside the line expands the full merged event log (current list styling). Collapsed by default; remember choice in localStorage `sema:progress:expanded`.
6. On answer arrival the indicator unmounts (as today via TurnView).
7. Failure end-state (no retry succeeded): line shows the failed stage in the existing orange style — error display itself stays TurnView's job.

Constraints: no new deps; RTL-safe (logical props, `dir` passed as today); keep `ProgressEvent` type/backend contract unchanged. Update `stageLabel`/add a `mergeEvents` helper with unit tests if a frontend test setup exists; otherwise skip tests. Run `npm run lint` && `npm run build`.

Accept: retried query = single line changing state; expanded log available; stages <1.5s never flash; Hebrew questions get Hebrew labels.
