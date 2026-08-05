# Task: marketing site QA sweep — full pass, English + Hebrew, find and fix bugs

Scope: `website/` (the Next.js marketing site). Run AFTER #38 (`website_motion_prompt.md`)
so the motion layer and the screenshot carousel are covered by this sweep too. If #38 is
still pending when this is picked up, do #38 first per queue order.

Method requirement: this is a LIVE sweep, not a code read-through. Build the static export
(`npm run build`), serve `out/` locally, and drive a real browser (Playwright) through every
check below. Evidence for every finding: screenshot + file/line. Fix everything small
in-place; anything that needs a product decision goes in the report instead of guessed at.

## 1. Page × locale matrix

Every page in both locales, every check below:

| | en | he |
|---|---|---|
| Home `/` | ✓ | `/he/` |
| Pricing `/pricing/` | ✓ | `/he/pricing/` |
| 404 page | ✓ | ✓ |

## 2. Hebrew / RTL correctness (the likely bug nest)

- Every section renders correctly under `dir="rtl"`: text alignment, flex/grid order,
  icons that imply direction (arrows, chevrons) point the right way, logical properties
  (`ms-`/`me-`/`ps-`/`pe-`) used — flag any physical `ml-`/`mr-`/`left-`/`right-` that
  breaks mirroring.
- The SEMA logo lockup stays LTR and un-mirrored in RTL (brand rule from the product:
  the mark is never flipped).
- Mixed-direction strings: numbers, "SEMA", English product terms inside Hebrew sentences —
  no reversed brackets, stray punctuation, or flipped percentages (the product codebase's
  own history shows this class of bug: reversed pager chevrons, RTL bracket issues).
- Hebrew translation completeness: no English leaking into `/he/` (except deliberate brand
  terms), no missing dictionary keys rendering as raw key names or `undefined`.
- The language switcher: en↔he from every page lands on the SAME page in the other locale
  (not the homepage), and the `<html lang dir>` attributes actually change.
- #38's motion in RTL: carousel advances in the reading direction, toast anchors on the
  logical corner. (How-it-works is now a static 1-2-3 card grid — #42 removed its stepper/
  progress-line; only the fade-up-stagger reveal remains, so just confirm the stagger
  order reads correctly in RTL.)

## 3. Functional pass

- Every link and anchor: header nav, footer, CTAs, `#how` / `#bookform` hash scrolls
  (including cross-page `/he/#bookform`-style), no dead links, no `sema.example`
  placeholder hrefs shipping as real links (`lib/site.ts` has a TODO — flag every place
  that placeholder URL leaks into rendered output: canonical/OG tags, sitemap, JSON-LD).
- Demo form (`DemoForm.tsx`): required-field validation, invalid email, success and error
  paths, double-submit protection, and what actually happens to the submission — if it
  posts nowhere real, the report must say so explicitly (a pilot losing demo requests is a
  business bug, not a code bug).
- Carousel (#38): arrows, drag, keyboard, dots, auto-advance + pause-on-hover, no CLS.
- How-it-works cards: #42 simplified this to a static, non-interactive 1-2-3 grid (no
  tablist, no click/keyboard activation, no auto-advance) — just confirm the three cards
  render with correct copy and the scroll-reveal fade-up-stagger entrance still fires.
- `prefers-reduced-motion`: every animation inert, page still fully usable and complete.

## 4. Visual pass

At 4 widths (mobile 375, tablet 768, laptop 1280, wide 1680), both locales:

- No horizontal overflow/scrollbars, no clipped or overlapping text, no broken wraps
  (Hebrew headlines especially — long words at 62px hero size).
- Images/SVGs crisp, no missing assets (404s in the network log), favicons correct.
- Dark-section (Proactive) contrast: all text passes AA on `#15161C`.
- Consistent brand colors: facet palette (#6C74F0 / #4E56D6 / #949CFF / #F2887C / #F2C94C)
  — flag any off-palette hardcoded approximations.

## 5. Technical pass

- Zero console errors/warnings on any page (both locales, all widths).
- Static export integrity: every route in `out/` (including `/he/*`), no broken
  `next/image` or asset paths under static hosting assumptions.
- SEO/meta per page per locale: `<title>`, description, canonical, `og:*` + image,
  `hreflang` pairs between en/he twins, sitemap + robots present and correct.
- Lighthouse (mobile + desktop) on home en + he: performance / a11y / SEO / best-practices.
  Record numbers in the report; fix cheap wins (missing alt, contrast, unsized images).
- a11y quick pass: heading hierarchy, landmark roles, focus visible on all interactive
  elements, skip-to-content, carousel announces state to screen readers (how-it-works is
  now non-interactive static content, so no state to announce there).

## 6. Deliverables

1. Fixes committed for everything unambiguous (typos, RTL breaks, dead anchors, missing
   alt/meta, console errors, contrast) — each its own focused commit.
2. `docs/website_qa_report.md`: findings table — severity (blocker/bug/polish), page,
   locale, evidence screenshot, fixed-or-open, and for open items WHY (needs decision /
   needs asset / needs real domain). Lighthouse before/after numbers.
3. Anything requiring a human decision (placeholder domain, demo-form destination,
   invented-looking copy) listed under an explicit "Decisions needed" heading at the top.

## Accept

- [ ] Full matrix (§1) driven in a real browser with screenshot evidence, both locales.
- [ ] Zero console errors; zero English leaks in `/he/`; language switcher round-trips.
- [ ] All unambiguous bugs fixed and committed; report at `docs/website_qa_report.md`.
- [ ] `npm run build` green; Lighthouse recorded before/after.
