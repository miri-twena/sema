# BUGFIX (priority — take before anything else pending): scroll hijack on the marketing site

User report (2026-08-04, reproduced on the live site after #38's motion layer): scrolling
down toward the book-a-demo section, the page JUMPS back up on its own to an earlier
section (the Proactive/product-image area). Scroll position is being stolen from the user.
This must be fixed before any other pending work on the site.

## Likely culprits (verify, don't assume — find the actual one)

All three #38 features run on timers and are prime suspects; any of them scrolls the page
if implemented with focus/scroll side effects:

1. **Carousel auto-advance** — advancing the active slide with `.focus()` (no
   `preventScroll`) or `scrollIntoView()` yanks the viewport to the carousel every 5s.
2. **How-it-works stepper auto-advance** — same: moving `tabindex`/focus on a timer.
3. **Proactive feed cycling** — inserting/removing alert cards every ~7s: if the list
   isn't height-stable, or the animation uses `scrollIntoView`, layout shift moves the
   page under the user (matches the reported "jumps to the image area" — this section IS
   the screenshot in the user's report).
4. Also check `HashScrollOnMount` — it must run once on mount only, never re-trigger on
   state changes the timers cause.

## The rule to enforce (and comment in the code)

**Nothing that runs on a timer may move focus or scroll.** `element.focus()` only inside
user-initiated handlers (click/keydown), and always `focus({ preventScroll: true })` unless
scrolling is the explicit purpose. `scrollIntoView` only in direct response to user
interaction (anchor click). Auto-advance changes state/classes — never focus, never
scroll. Cycling lists must be height-stable (fixed container height; animate transforms
and opacity, not layout).

## Regression test (must be part of the fix)

Playwright, against the static export, both locales:

1. Load home, scroll steadily to `#bookform`, then idle 20s (≥3 carousel advances, ≥2 feed
   cycles). Assert `window.scrollY` never changes by more than ±2px without user input.
2. Same idle check while resting mid-page (carousel in view).
3. Anchor navigation still works: clicking "See how it works" scrolls to `#how` (the rule
   kills timer scrolling, not user scrolling).

## Accept

- [ ] Root cause identified and named in the commit message (which mechanism, which line).
- [ ] User can scroll anywhere and stay there indefinitely; timers keep animating in place.
- [ ] Regression test in place and green; `npm run build` green; reduced-motion still inert.
- [ ] The no-focus/no-scroll-from-timers rule commented at each timer site.
