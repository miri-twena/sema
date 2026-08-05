# Task: hero demo card — "data connected" status indicator

User request (2026-08-05, with reference screenshot): the hero's live-demo card gets a
small connection-status indicator — green dot + label — in the style of the product's own
status chip: a subtle pill, muted text, solid green dot at the logical start of the label.

Scope: `website/` hero demo card only (`components/home/Hero.tsx` or the demo-card
component #38 extracted from it).

## Spec

- **Placement:** in the demo card's header bar (the row with the mark + "Live demo" /
  "תשובה חיה" label), on the opposite (logical end) side. One line, never wraps.
- **Content:** green dot + label. Strings via the dictionaries: en `Data connected`,
  he `הנתונים מחוברים`. Note the reference is a dark-bg chip; the demo card header is
  light — adapt: same structure (dot + quiet label), colors from the site's light palette.
- **Style:** dot 7–8px, solid green — reuse the site's existing success/positive green
  (the one already used for `+12%` deltas) rather than inventing a new hex. Label ~12px,
  muted text color, medium weight. Optional pill background: very light tint or none —
  match the header's quiet look; it must read as status, not as a button.
- **Motion:** the dot gets a gentle "live" pulse (opacity/scale loop, ~2.5s). Two rules:
  pulse animation only — no layout shift; inert under `prefers-reduced-motion` (dot
  renders static, fully opaque).
- **RTL:** in `/he/` the indicator sits on the logical end and the dot precedes the label
  in reading direction — logical properties only, the dot must not detach from the label.
- **Timing vs. the demo loop (#38):** the indicator is ALWAYS visible and static in
  content — it does not participate in the typing/answer loop, does not reset between
  cycles, and must not be part of any timer logic (see the #41 rule: nothing on a timer
  moves focus or scroll).

## Accept

- [ ] Indicator visible in both locales, correct side in RTL, never wraps or clips at any
      of the 4 QA breakpoints (375/768/1280/1680).
- [ ] Dot pulses subtly; static under reduced motion; zero layout shift either way.
- [ ] Green reuses the existing success color token/value; strings in both dictionaries.
- [ ] `npm run build` + lint green; scroll-hijack regression test (#41) still green.
