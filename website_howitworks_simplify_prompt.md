# Task: simplify the How-it-works section — cards only

User decision (2026-08-04, after reviewing #38's built stepper): the How-it-works section
went too far. Strip it back — **keep only the three numbered cards (1-2-3). Remove the
progress line and the whole visual panel below the cards** (the chat-bubble/chart
illustrations).

## What to do (`website/components/home/HowItWorks.tsx`)

1. **Delete the visual panel** under the cards — the per-step illustration area (mini chat
   exchange, connect-data illustration, alert cards) goes away entirely, including its
   components/assets if nothing else uses them.
2. **Delete the progress line** (the brand-color line drawn under/between the step cards).
3. The three cards revert to a plain informational grid: same copy, same numbered chips,
   same card styling. With no panel to drive, the tab behavior is meaningless — remove the
   `tablist`/roving-tabindex semantics, the click-to-activate state, the active-card accent,
   and the auto-advance timer. Cards are not interactive anymore.
4. **Keep** the scroll-reveal entrance (fade-up stagger, §2 of #38) — that stays consistent
   with the rest of the page and the user liked the overall motion.
5. Both locales; remove any now-unused dictionary keys (en+he together — parity).
6. Housekeeping: `website_qa_prompt.md` (#40, still pending) references the stepper in §2
   and §3 — update those lines to match this simplification so #40 doesn't chase a feature
   that no longer exists. Note the change in your completion note.

Side benefit worth verifying while here: the stepper's auto-advance was one of the
suspects in #41 (scroll hijack). If #41 already ran, confirm its regression test still
passes after this removal; if it hasn't run yet, this task removes one suspect — say so in
the completion note so #41's investigation starts with the remaining two.

## Accept

- [ ] Section shows exactly: kicker, heading, three static cards. No line, no
      illustrations, no interactivity beyond the entrance reveal.
- [ ] No dead code/assets/dictionary keys left (`npm run build` + lint green, both locales
      render).
- [ ] #40's prompt file updated to match.
