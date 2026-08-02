# Task: Table pager arrows point the wrong way (RTL flip bug)

Screenshot: the in-answer table pager renders `>  Page 4 of 20  <` — chevrons reversed (next/prev point away from their action). Almost certainly the pager sits inside an RTL (`dir="auto"`) answer container, which mirrors the ROW ORDER of the controls while the chevron glyphs stay hardcoded — so they end up pointing outward.

1. Fix the pager so the chevron always points toward its action regardless of container direction: previous = chevron pointing toward "back" (left in LTR context), next = toward "forward". Simplest robust fix: isolate the pager row as `dir="ltr"` (digits/pager are LTR anyway per app conventions) OR use logical icons that flip with direction — pick ONE approach and apply it to EVERY pager instance (answer tables, drill tables, Audit log, Users pagination from `users_pagination_prompt.md` if already merged).
2. Verify in: a Hebrew answer's table, an English answer's table, Audit log, and at first/last page (disabled states still correct).
3. While there: confirm the click targets match the visual direction (the bug may be visual-only or functional — test both, report which it was).
4. `npm run lint`, `npm run build`; screenshot before/after.

Accept: [ ] In both languages, the left-pointing control goes back and the right-pointing control goes forward, everywhere a pager exists.
