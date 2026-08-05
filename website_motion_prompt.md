# Task: marketing site — motion layer + interactive sections + product screenshot carousel

Scope: `website/` only (the Next.js marketing site, en + he). Approved motion concept mockup
reviewed by the user 2026-08-04. Design language, copy, palette, and section ORDER stay as
they are — this adds motion, interactivity, and one new carousel block. No copy rewrites
beyond the strings this file adds.

Global rules:

- **`prefers-reduced-motion: reduce` disables every animation in this task** (elements land
  in their final state). Non-negotiable, applies to each item below.
- No animation library unless truly needed — CSS keyframes + IntersectionObserver cover
  almost everything here. If something genuinely needs more (the carousel drag), prefer a
  tiny dependency-free implementation over adding framer-motion for one component.
- All new strings go through `lib/i18n` (en + he). RTL: animations must not mirror
  incorrectly — translateX directions flip under `dir="rtl"` (use logical values or flip in
  CSS per dir).
- The site is statically exported (`out/`) — everything must work with no server.

## 1. Hero (approved mockup, part 1)

1. **Staggered entrance:** badge → H1 → sub → CTAs → stat row fade-up in sequence
   (~120ms apart) on load.
2. **Self-running demo in the hero card:** the demo question types itself letter by letter
   (~45ms/char, blinking caret), then the answer card fades in and its bars grow bottom-up
   with staggered delays (existing `BARS` data). Add a coral sparkline under the bars that
   draws itself (`stroke-dashoffset` animation). Loop: after ~8s idle, reset and replay with
   a SECOND question/answer pair (add one more Q + dataset to the dictionaries), alternating.
3. **Floating facet fragments:** 2 low-opacity (≤.10) fragments of the brand mark floating
   slowly (`translateY` ±10-14px, 7-9s ease-in-out loops) behind the hero. Use the existing
   `/brand/sema-mark-brand.svg` geometry (fragment = subset of polygons), `aria-hidden`.
4. **Alert toast:** a small toast slides in over the demo card's top-right corner every ~6s
   ("Alert: refund rate ↑ 3.1%" / "SEMA noticed before you asked" — add to dictionaries),
   visible ~4s, slides out. In `he` it anchors top-left (RTL logical).
5. **Stat row counters:** the three stats count up from 0 (~1s, requestAnimationFrame) when
   the hero enters the viewport. ONLY numbers we can stand behind — if a stat is
   invented, drop the stat rather than animate a fiction; ask the user for real values
   before shipping any new number that isn't already on the site.

## 2. Features — scroll reveal

Cards fade-up with stagger when scrolled into view (IntersectionObserver, once, no
re-trigger). Top color bar on each card grows width 0→100% right after its card lands.

## 3. NEW: product screenshot carousel (user request)

A new section between Features and Proactive: **"See SEMA in action"** (+ he equivalent) —
a screenshot carousel of the real product.

- **Assets:** `website/public/screens/*.png` — they do NOT exist yet. Generate them from
  the running dev stack (Playwright/Puppeteer against localhost, viewport 1440×900, both
  the demo tenants' seeded data): home dashboard, a chat answer with chart + KPI cards,
  the daily brief, admin › users, admin › semantic model. 5 shots, light mode, EN chrome.
  Script goes in `website/scripts/capture-screens.mjs` (rerunnable as the product evolves;
  document in the website README). If the dev stack isn't reachable when this task runs,
  stop and report — do NOT ship placeholder rectangles or mock screenshots.
- **Behavior:** center-mode carousel — active slide full opacity/scale, neighbors peeking
  at reduced scale (~.92) and opacity (~.6). Advance: arrows, click on a peeking slide,
  drag/swipe (pointer events), and keyboard (arrow keys when focused). Auto-advance every
  5s, PAUSED on hover/focus/`prefers-reduced-motion`. Dots + slide caption under the
  frame. Loop infinite. In `he` the direction follows RTL.
- **Chrome:** each screenshot sits in a browser-frame card (top bar, three dots, URL pill
  `app.sema.example`) with the site's card border/shadow tokens. `loading="lazy"`,
  explicit width/height (no CLS), `alt` = the caption.
- No library — pointer-events + CSS transforms.

## 4. How it works — interactive steps

Replace the static 3-card grid with a **click-through stepper** (same copy, same 3 steps):

- Step cards become tabs (still visually cards, in a row). The active card is accented
  (brand border + slight lift); clicking/keyboard-selecting a card shows a matching visual
  in a panel below (or beside on wide screens): step 1 → connect-data illustration (reuse
  the existing facet/icon language), step 2 → mini chat exchange, step 3 → mini alert cards
  (reuse Proactive's alert-card component style, smaller).
- The number chips draw a progress line 1→2→3 as steps are visited.
- Auto-advance every 5s until first interaction, then manual only. Roving tabindex,
  `role="tablist"` semantics, works in RTL.

## 5. Proactive (dark section) — live feel

- Alert cards slide in one by one (staggered, from the logical end) on scroll into view.
- After the initial three land, loop: every ~7s the LIST shifts — a new alert card (reuse
  the same 3, cycling) slides in on top while the oldest fades out — a living feed, not a
  static list. Pause on hover. Max 3 visible at all times (no layout growth).

## 6. Testimonials + BookDemo — light touch only

- Testimonial cards: fade-up stagger on scroll (same reveal used in Features, §2).
- BookDemo section: the section's heading underlines itself with a short brand-color
  stroke animation on reveal. Nothing else — the form must stay dead simple.

## 7. Acceptance

- [ ] Every animation inert under `prefers-reduced-motion: reduce` (test via emulation).
- [ ] Hero demo types, answers, grows bars, draws sparkline, loops with alternating Qs.
- [ ] Carousel: 5 real product screenshots, drag + arrows + keyboard + dots, auto-advance
      pauses on hover, RTL-correct in `he`, zero CLS (explicit dimensions).
- [ ] How-it-works stepper keyboard-accessible (`tablist` semantics, roving tabindex).
- [ ] Proactive feed cycles and pauses on hover.
- [ ] `npm run build` (static export) green; Lighthouse performance not degraded by more
      than ~5 points vs. baseline (measure before/after, report both numbers).
- [ ] Both locales verified visually (en LTR + he RTL) — screenshots in the report.
- [ ] No invented statistics anywhere (§1.5).
