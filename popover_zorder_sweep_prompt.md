# Task: Popover/kebab z-order sweep — one shared portal pattern, everywhere

Recurring bug class: kebab (⋯) and popover menus render clipped/behind sibling elements when opened inside scroll containers. Fixed once for the conversation sidebar (portal pattern, `sidebar_improvements_prompt.md`); user now reports the SAME bug in the Users screen row menu (screenshot: View details / Suspend user menu sliding under the next row). Fix the class, not the instance.

1. **Extract the sidebar's portal-menu solution into ONE shared component/hook** (portal to body, positioned to trigger, flip-up near viewport bottom, `useDismiss`, keyboard nav) — if the sidebar fix already created something reusable, promote it; otherwise build it from that implementation.
2. **Audit every popover-like menu in the app and migrate each to the shared pattern.** Known/likely instances: Users screen row kebab (the reported bug), UserDetailDrawer actions if any, Data sources card menus/report-problem confirm, alert card menus, semantic model item menus/History actions, Audit log row affordances, sidebar user-row menu + gear menu (verify they use the portal already), DrillChat/thread menus. Grep for the existing popover/confirm patterns to build the full list — report it in the final summary with before/after status per instance.
3. Confirm popovers (delete/suspend confirmations) are included — same clipping risk.
4. Verify each migrated menu: last row of a long list, mid-scroll, narrow sidebar width, and 1280px viewport. No behavioral changes beyond stacking/positioning.
5. `npm run lint`, `npm run build`, existing tests green; screenshot the Users-row menu fixed (the reported case) in the final report.

Accept: [ ] One shared portal menu implementation; every listed instance migrated; the Users screen menu renders fully above all rows in all positions.
