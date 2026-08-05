# SEMA marketing website — QA sweep report

Queue item #40. Live Playwright sweep (headless Chromium, real static export served
locally) over `website/`, both locales, home/pricing/404. Baseline for this sweep is
commit `860867e` (the previously-uncommitted #38 motion-layer work, committed as-is at
the start of this task). All fixes below are separate commits on top of it.

Method note: the Claude_Browser MCP pane in this environment kept
`document.visibilityState: 'hidden'`, which breaks timer-driven behavior (autoplay,
the hero typing loop, the Proactive feed cycle). Per this repo's conventions, all
checks were driven instead through real headless Chromium via Playwright scripts
(reusing `scripts/serve-static.mjs` from queue item #41), which does not have that
limitation.

## Decisions needed

These need a product/design call, not a code fix — listed here rather than guessed at.

1. **Primary brand color fails WCAG AA contrast.** `#6C74F0` (`bg-brand` /
   `text-brand`) is 3.89:1 both as white-text-on-brand-fill (every "Book a demo"
   button, site-wide) and as brand-text-on-white (the SEMA wordmark in the header/
   footer logo, nav hover states) — AA requires 4.5:1 for this text size. This is the
   core brand hue used everywhere, so recoloring it is a brand decision, not something
   to change unilaterally. Two shades **already in the design system** would clear AA
   without introducing a new color: `brand.hover` (`#5B62DE`, 4.95:1) or `brand.deep`
   (`#4E56D6`, 5.79:1). Confirmed via Lighthouse's `color-contrast` audit (see
   Lighthouse section) and manual contrast calculation.
2. **Demo form has no real destination.** `DemoForm.tsx` has no backend — submitting
   builds a `mailto:hello@sema.example` link (a domain that doesn't resolve). Native
   HTML validation (required fields, email format) works correctly, but there is no
   success/error state, no double-submit protection, and no real lead capture. A pilot
   losing every demo request to an unreliable mailto handoff is a business risk, not a
   code bug — this needs a real form endpoint before launch. (Already flagged with a
   `TODO` in the source.)
3. **Placeholder production domain.** `lib/site.ts`'s `SITE_URL = 'https://sema.example'`
   (already flagged with a TODO) flows into canonical URLs, OG tags, hreflang pairs,
   and now the new sitemap.xml/robots.txt. All correctly wired, but every one of them
   will need updating once a real domain exists.
4. **No real OG/social-share image.** Removed the `openGraph.images: ['/og.png']`
   reference (see Fixed #5) because the file was never added — but a real 1200×630
   marketing image still needs to be designed before OG previews will work at all.
5. **Footer "Privacy"/"Terms" aren't links.** They're `<span>` elements styled to look
   clickable (cursor-pointer, hover state) with no `href` and no destination page.
   Not a broken link exactly (nothing 404s), but a UI affordance promising a
   destination that doesn't exist. Needs real Privacy/Terms pages (or copy) before
   they should become real links.
6. **Static-export 404 is single and English-only.** Fixed the bare, unbranded default
   (see Fixed #6), but a Next.js static export with this repo's two-route-group
   locale architecture (`(en)/layout.tsx` and `(he)/layout.tsx` each independently
   render their own root `<html>`, since there's no shared root layout) can only serve
   one physical `404.html` for every unmatched path in every locale. The improved
   page's own `<html>` tag also has no `lang`/`dir` (confirmed: this route isn't
   inside either locale's layout tree, so Next falls back to a synthesized minimal
   wrapper). A true `/he/*` 404 would need restructuring that architecture — riskier
   than this sweep's scope (it risks regressing the correctly-working per-locale
   `lang`/`dir` on every real page), so it's flagged rather than attempted.

## Findings

| # | Severity | Page/Locale | Finding | Status | File:line |
|---|----------|-------------|---------|--------|-----------|
| 1 | bug | all, both locales | `text-faint` (#8A8FA3, 3.2:1) and several pastel tag/avatar colors (coral, gold, mint) failed WCAG AA 4.5:1 on their backgrounds | **Fixed** `64611d4` | `tailwind.config.js:28`, `components/Footer.tsx`, `components/home/Proactive.tsx:7-9`, `lib/i18n/quotes.ts:3-7`, `components/home/hero/AlertToast.tsx:40`, `components/home/hero/HeroDemoCard.tsx:162` |
| 2 | bug | all, both locales | No `<main>` landmark anywhere; no skip-to-content link | **Fixed** `12932dd` | `components/HomePage.tsx`, `components/PricingPage.tsx`, new `components/SkipLink.tsx` |
| 3 | polish | Home, RTL | Hero's decorative floating fragments used physical `-left-6`/`-right-8`, pinned to the same corner instead of mirroring in RTL | **Fixed** `79efc32` | `components/home/hero/FloatingFragments.tsx:9,21` |
| 4 | bug | all | No `robots.txt`/`sitemap.xml` at all | **Fixed** `8afecd1` | new `app/robots.ts`, `app/sitemap.ts` |
| 5 | bug | all | `openGraph.images: ['/og.png']` referenced a file that doesn't exist in `public/` — every social-share preview loads a 404 | **Fixed** `8afecd1` | `app/(en)/layout.tsx`, `app/(he)/layout.tsx` |
| 6 | bug | 404, both locales | Default Next.js 404: no branding, no header/footer, generic "This page could not be found", plain serif text | **Fixed** `7db5ec5` (partially — see Decisions needed #6) | new `app/not-found.tsx` |
| 7 | bug | Home, mobile | Carousel dot buttons were an 8×8px (22×8px active) touch target — Lighthouse `target-size` flagged all 5 as under the 24×24px minimum | **Fixed** `75aa064` | `components/home/carousel/ProductCarousel.tsx:232-255` |
| 8 | blocker (open) | all | Primary brand color `#6C74F0` fails AA contrast as button-fill-with-white-text and as text-on-white (SEMA wordmark) | **Open** — Decisions needed #1 | `tailwind.config.js:16` |
| 9 | bug (open) | Home | Demo form has no real backend (`mailto:` to a placeholder domain) | **Open** — Decisions needed #2 | `components/DemoForm.tsx:7,23` |
| 10 | polish (open) | 404 | Single locale-neutral English 404 page; its own `<html>` has no `lang`/`dir` | **Open** — Decisions needed #6 | `app/not-found.tsx` |
| 11 | n/a (reviewed, no bug) | Home carousel | Carousel product screenshots ship English UI chrome regardless of site locale, and the browser-frame's `app.sema.example` URL pill is decorative mockup text | **By design** — matches the original #38 motion-layer spec verbatim; not a leak in the sense this sweep was checking for (canonical/OG/sitemap), just plain non-link text | `components/home/carousel/BrowserFrame.tsx:13` |

### Everything checked and confirmed correct (no bug found)

- **Full page × locale matrix** (home/pricing/404, en+he) driven at 4 widths (375/768/
  1280/1680): zero console errors or warnings, zero failed network requests, zero
  horizontal overflow at any combination.
- **Language switcher** round-trips correctly from every page (verified
  programmatically: `/pricing/` ↔ `/he/pricing/`, not dropping to homepage), and
  `<html lang dir>` flips correctly on every real page.
- **RTL correctness**: logo stays LTR/unmirrored per `Logo.tsx`'s explicit `dir="ltr"`;
  carousel prev/next chevrons flip (`scaleX(-1)`) so they still point outward after
  their physical position swaps; header/nav/grid/dot ordering all mirror correctly
  (verified visually — pricing tier cards, how-it-works numbered steps, hero
  grid, footer link order); Proactive feed's reveal-from-the-logical-end animation is
  direction-aware via `:dir(rtl)` in `globals.css`; AlertToast anchors via logical
  `end-3`; numeric prices/percentages stay `dir="ltr"` inside Hebrew sentences.
- **Hebrew translation completeness**: `Dictionary` is a TypeScript interface shared by
  `en.ts`/`he.ts` — a missing key is a compile error, not a runtime `undefined`, so
  structural completeness is enforced by the build itself (confirmed: build is green).
- **Demo form validation**: native required-field and email-format validation
  triggers correctly and blocks submission (verified: empty submit → "Please fill out
  this field", invalid email → "Please include an '@'...").
- **Alt text**: 0 images missing an `alt` attribute across all 4 real pages/locales.
- **Heading hierarchy**: single `h1` per page, no skipped levels, sequential `h2`/`h3`
  nesting matches the visual section/card structure.
- **`prefers-reduced-motion: reduce`**: hero badge/h1/sub reach `opacity: 1`
  immediately; the demo card's bars/sparkline/KPI block stays `visibility: visible`
  (not hidden); the typed question renders the full text with no stuck mid-typing
  state; `AlertToast` returns `null` outright (it's `aria-hidden` decoration, so this
  doesn't remove real content).
- **No invented statistics**: the original motion-layer spec asked for an animated
  hero stat row but explicitly said to drop it rather than invent a number if none was
  supplied — confirmed the #38 implementation did exactly that (no stat row exists).
- Off-palette color check: grepped every hardcoded hex across `components/`; nothing
  found that's a near-miss approximation of the five facet colors.

## Lighthouse (home page, both locales, mobile + desktop)

"Before" = baseline commit `860867e` (pre-QA-sweep), built and served from a
temporary git worktree on a separate port. "After" = final state, all fixes applied
(commit `75aa064`).

| Page | Performance (before → after) | Accessibility (before → after) | Best Practices | SEO |
|---|---|---|---|---|
| Home (en), mobile | 77 → 76 | 90 → 96 | 100 → 100 | 100 → 100 |
| Home (en), desktop | 98 → 98 | 90 → 96 | 100 → 100 | 100 → 100 |
| Home (he), mobile | 75 → 75 | 90 → 96 | 100 → 100 | 100 → 100 |
| Home (he), desktop | 98 → 98 | 90 → 96 | 100 → 100 | 100 → 100 |

Performance is flat (±1 point, within run-to-run noise — well inside the acceptance
criterion's ~5-point budget; none of this sweep's fixes touch bundle size or render
path). Accessibility improved +6 points from the contrast and touch-target fixes.
The remaining accessibility gap (96, not 100) is entirely the brand-color contrast
issue in Decisions needed #1 — Lighthouse's `color-contrast` audit still flags the
"Book a demo" buttons and the SEMA wordmark, which this sweep did not recolor
unilaterally.

## Build

`npm run build` is green (static export to `out/`) as of the final commit.
