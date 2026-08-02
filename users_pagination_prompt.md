# Task: Users and permissions — pagination

Add paging to the Users screen (spec §8 of the main admin spec already calls for server-side pagination on tables). The Audit log screen already has server-side pagination at 50/page — reuse its pattern and components, don't invent a second pager.

1. **Backend:** `GET /api/admin/users` gains `page`/`page_size` (default 25 for users — denser rows than audit), returns `total` + page rows. Search + role filter keep working AS server-side filters combined with paging (filtered total, not global total). Sorting stays as-is.
2. **Frontend:** pager at the table bottom (same component/style as Audit log), "Showing 1-25 of N" line, page resets to 1 when search/filter changes. The pending-invite rows and the last-admin info line behave correctly across pages (invites sort/paginate with everyone else — no pinning).
3. Loading state: skeleton rows on page change (existing pattern). Empty page edge case (deleting the last user on the last page → jump back a page).
4. Tests: paging math (page 2 returns the right slice, filtered totals), page reset on filter change; `pytest`, `npm run lint`, `npm run build` green.

Accept: [ ] With >25 users (seed extra in a test fixture, not in the demo data), the table pages correctly, search+filter+paging compose, and the demo tenant (10 users) shows a single page with no pager noise (pager hidden when total ≤ page_size).
