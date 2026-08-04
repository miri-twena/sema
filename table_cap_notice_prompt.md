# Task: visible truncation notice on capped tables

Follow-up to `full_data_export_prompt.md` (#33, done). User request (2026-08-04): the current
cap indicator — the tiny "(capped)" with a hover tooltip in `DataTable.tsx`'s footer — is too
subtle. When a result is display-capped, the answer must carry an explicit, always-visible
note that only the first 1,000 rows are shown.

## Requirements

1. When `table.truncated`, render a clearly visible one-line notice attached to the table
   (above the footer, or as a caption row directly under the table):
   - EN: `Showing the first 1,000 rows of N — the display is capped; Export downloads everything.`
   - HE: `מוצגות 1,000 השורות הראשונות מתוך N — התצוגה מוגבלת; הייצוא מוריד את הכל.`
2. Both numbers come from real values — the applied display cap (`SEMA_ROW_LIMIT`, don't
   hardcode 1,000 in the string; pass it in) and the true total the server already returns
   (`table.total_rows`). Formatted with `toLocaleString()`.
3. Strings via the locale files (`en.ts` / `he.ts`, parity test passes); the notice's
   direction follows the answer language like the rest of the table chrome.
4. This is DETERMINISTIC UI — it appears on every capped table regardless of what the
   agent's text says (#33 item 6 remains the LLM-side counterpart). Uncapped tables never
   show it.
5. Replace the old "(capped)" marker — don't show both.
6. Styling: quiet but unmissable — e.g. the table-footer text size with a muted-warning tint
   (existing `warning` tokens), not an alert banner. No layout shift on uncapped tables.

## Accept

- [ ] Capped table (e.g. "כל ההזמנות") shows the notice with correct cap + true total, in
      both languages, correct direction.
- [ ] Uncapped table: no notice, no "(capped)" leftovers anywhere (`grep -rn "capped" frontend/src`).
- [ ] Build + typecheck + locale parity test pass.
