# SEMA — implement the new brand mark & wordmark

Source of truth: `design_handoff_logo/` at the repo root (already unzipped).

- `design_handoff_logo/PROMPT.md` — the designer's spec. **Read it, but the file paths and
  a few repo claims in it are wrong** — this document corrects them. Where the two disagree,
  this document wins on *repo facts*; PROMPT.md wins on *design intent*.
- `design_handoff_logo/assets/*.svg` — the mark geometry. Copy verbatim, never redraw.
- `design_handoff_logo/SEMA Logo.dc.html` — visual reference canvas (open in a browser).

This is a brand asset + display font change only. Do not restyle screens or components
beyond swapping the logo and its font.

---

## 0. What already exists (read before you start)

There is a **previous logo implementation** in the repo — the "rising path" mark in Syne 700.
It must be fully removed, not layered over.

```
frontend/src/components/brand/Logo.tsx          # old impl: MARK_PATH, 3 nodes, Syne
frontend/src/components/brand/logo-mark.svg     # old, delete
frontend/src/components/brand/logo-mark-inverse.svg   # old, delete
frontend/src/components/brand/logo-mark-mono.svg      # old, delete
frontend/public/favicon.svg                     # old mark, replace
frontend/public/favicon-16.svg                  # old mark, replace  ← PROMPT.md misses this one
```

Existing call sites (all of them — none passes a `variant`, so renaming the variant
breaks nothing):

| File | Line | Current call | Change to |
| --- | --- | --- | --- |
| `frontend/src/components/Sidebar.tsx` | ~175 | `<Logo size={24} />` | `<Logo size={26} />` |
| `frontend/src/components/admin/AdminPanel.tsx` | ~60 | `<Logo size={22} />` | see §3 (7c row) |
| `frontend/src/components/login/EmailStep.tsx` | ~42 | `<Logo size={52} stacked tagline />` | `<Logo size={44} />` — see §3a |
| `frontend/src/components/login/CodeStep.tsx` | ~27 | `<Logo size={52} stacked tagline />` | `<Logo size={44} />` — see §3a |
| `frontend/src/components/login/ErrorScreen.tsx` | ~30 | `<Logo size={40} stacked />` | `<Logo size={44} />` — see §3a |

---

## 1. Corrections to PROMPT.md — apply these, do not follow PROMPT.md literally

**Paths.** PROMPT.md's "Files to create" and "Where the logo goes" tables use paths that
don't exist in this repo:

| PROMPT.md says | Actual path |
| --- | --- |
| `frontend/src/login/LoginPage.tsx` | login lockup lives in `frontend/src/components/login/EmailStep.tsx` **and** `CodeStep.tsx` — `LoginPage.tsx` renders no Logo. Update both steps. |
| `frontend/src/login/ErrorScreen.tsx` | `frontend/src/components/login/ErrorScreen.tsx` |
| `frontend/src/admin/AdminPanel.tsx` | `frontend/src/components/admin/AdminPanel.tsx` |
| `frontend/src/components/brand/sema-mark-*.svg` | correct — but **delete** the old `logo-mark*.svg` in that folder |

**Colors.** PROMPT.md claims the five facet colors are "all already in
`frontend/src/lib/tokens.ts` (`ACTION` and `CHART_PALETTE`)". That is not true:

- There is **no `ACTION` export** in `tokens.ts`.
- `CHART_PALETTE` is `["#7C8CFF", "#7EE6C3", "#9ED8FF", "#FFB4A2", "#F2C94C", "#C9A0FF"]` —
  only `#F2C94C` overlaps.
- `BRAND` already has `lavender: "#6C74F0"`, `lavender400: "#949CFF"`, `coral: "#F2887C"`.
- `#4E56D6` (the darkest facet, 4 polygons) exists nowhere.

→ Add `lavender600: "#4E56D6"` and `yellow: "#F2C94C"` to the `BRAND` object in
`frontend/src/lib/tokens.ts`, and have the inlined mark reference `BRAND.*` for all five
facet colors. Keep the existing `BRAND` keys — they're used elsewhere.

**Body font.** PROMPT.md says "UI text stays Manrope (Latin) / Heebo (Hebrew) exactly as
today." Wrong: body copy in this repo is **Inter** (`@import` at the top of
`frontend/src/index.css`). Manrope 600 is loaded *only* for the Logo tagline. Leave both
alone — the point stands that Montserrat must not leak into UI text.

**Alignment.** PROMPT.md's lockup rules say the stacked lockup is "centered". Overridden by
direct design review: **every lockup is left-aligned and tight** — see §2. Whatever a
reference render shows, the mark and wordmark are never spread apart.

**Sidebar collapsed state.** PROMPT.md lists a "Collapsed sidebar → `markOnly`" row.
`Sidebar.tsx` has **no collapse control** (see its header comment); the mobile drawer mounts
the same full sidebar. Skip that row. `markOnly` still ships as a prop and is exercised by
the admin header (§3) and the small-size rule.

---

## 2. `Logo.tsx` — rewrite

Replace the file's contents entirely (same path, same named export `Logo`).

```tsx
type LogoProps = {
  variant?: 'brand' | 'inverse' | 'mono';  // default 'brand'
  size?: number;        // mark HEIGHT in px, default 24
  markOnly?: boolean;   // default false
  stacked?: boolean;    // default false
  tagline?: boolean;    // implies stacked
  className?: string;   // keep — the old API had it
};
```

- **Rename the variant** `'primary'` → `'brand'`. Also rename the exported
  `LogoVariant`/`LogoProps` types' union accordingly. No call site passes `variant` today,
  so no consumer updates are needed — but grep to confirm before assuming.
- Mark geometry: copy the polygons from `design_handoff_logo/assets/sema-mark-brand.svg`
  verbatim. `viewBox="0 0 219 185"` — **wider than tall, so size by height**
  (`height={size}`, `width="auto"`, and let the viewBox handle the ratio).
- Wordmark font-size = `Math.round(size / 1.6)`; gap = `size * 0.25` via flex `gap`.
- **The lockup is flush-left and tight — this is a hard requirement.** Some reference renders
  of the lockup show the mark and the wordmark pushed to opposite ends of a wide box; that is
  wrong. The two elements sit next to each other, separated by exactly `size * 0.25` and
  nothing more, and the pair hugs the start edge of whatever contains it. Concretely, on the
  lockup wrapper:
  - `display: inline-flex` (not `flex`) and `width: fit-content` — the component must never
    stretch to its parent's width.
  - `justifyContent: 'flex-start'`. Never `space-between`, `center`, or `space-around`.
  - No `flex: 1`, no `flexGrow`, no `marginLeft: auto`/`marginInlineStart: auto` on the
    wordmark or the mark.
  - No fixed `width` on the wrapper or on the mark's `<svg>` (height drives width).
  - This applies to **all** variants and both orientations — horizontal *and* stacked. In the
    stacked lockup the mark, wordmark, and tagline are left-aligned
    (`alignItems: 'flex-start'`, `textAlign: 'start'`), not centered.

  Enforce it inside `Logo.tsx` so no consumer can reintroduce the gap by styling its own
  container. Do not add a prop to opt out.
- Enforce mark-only when the computed wordmark size would be < 13px.
- `letter-spacing: 0.12em`, literal uppercase string `SEMA` (not `text-transform`).
- Wordmark color: `#6C74F0` (`BRAND.lavender`) for brand, `#FFFFFF` for inverse,
  `currentColor` for mono.
- Tagline `AI BUSINESS ADVISOR`: Manrope 600, 12px, `letter-spacing: .22em`, `#8A8FA3`.
- Wrap the whole lockup in `<span dir="ltr" style={{unicodeBidi:'isolate'}}>`. Never mirror
  the mark in RTL.
- Keep a comment documenting clear space = 0.5× mark height (consumers add it).
- `role="img"` + `aria-label="SEMA"` on the SVG when `markOnly`; when the wordmark renders as
  text, the SVG should be `aria-hidden` so screen readers don't say "SEMA" twice.

Also drop the three `sema-mark-*.svg` files into `frontend/src/components/brand/` as
standalone assets (brand / inverse / mono), per PROMPT.md §2. Do **not** ship
`sema-mark-exact.svg`.

---

## 3a. Login card — kill the duplicate tagline, go horizontal

There is a **live bug** here, independent of the logo work. `EmailStep.tsx` and `CodeStep.tsx`
both render:

```tsx
<Logo size={64} stacked tagline />   {/* renders "AI BUSINESS ADVISOR" */}
<p className="text-[13.5px] text-muted mt-2">{t.headline}</p>
```

…and `t.headline` in `frontend/src/lib/loginCopy.ts` is **also** `"AI Business Advisor"` — in
both `en` and `he`. So the phrase renders twice, stacked directly on top of itself.

Fix, in all three login surfaces (`EmailStep.tsx`, `CodeStep.tsx`, `ErrorScreen.tsx`):

- Drop `stacked` and `tagline`. Use the **horizontal** lockup: `<Logo size={44} />` — mark and
  the word `SEMA` on one line, per §2's flush-left rule.
- Keep exactly **one** "AI Business Advisor". Keep the `<p>{t.headline}</p>` line (it lives in
  the locale file and is the localizable one) and let the tagline disappear with `tagline`.
  Do not delete `t.headline` from `loginCopy.ts`.
- `ErrorScreen.tsx` never had a tagline — it just moves from `stacked` to horizontal so the
  three login surfaces match.
- The lockup **block** stays horizontally centered in the login card (the parent's
  `flex flex-col items-center` is unchanged). §2's flush-left rule governs the *inside* of the
  lockup — the gap between mark and wordmark — not where the block sits on the card.
- `44` is a starting value chosen to suit a horizontal lockup in a `max-w-sm` card; the old
  `52`/`64` were sized for a stacked one. Adjust if it reads too large, and say so.

After this, no call site passes `stacked` or `tagline`. **Keep both props implemented anyway**
(the handoff specifies them and they're covered by §2) — just don't add a consumer for them.

## 3. Admin aside header (7c)

In `frontend/src/components/admin/AdminPanel.tsx`, the aside header currently renders
`<Logo size={22} />` followed by an `Organization admin` label. Replace those two blocks with
a single row:

```tsx
<div style={{display:'flex', alignItems:'center', gap:8}}>
  <Logo size={20} markOnly />
  <span /* Montserrat 800, 12.5px, letterSpacing .11em, #6C74F0 */>SEMA</span>
  <span /* keep the existing label classes: text-[0.7rem] font-semibold uppercase tracking-wide text-faint */>Admin</span>
</div>
```

Keep the `Back to SEMA` button above it unchanged. The admin shell stays LTR.

---

## 4. Favicon

- Replace `frontend/public/favicon.svg` with `design_handoff_logo/assets/sema-favicon.svg`
  (white facets on a lavender `rx=15/64` tile, `viewBox="0 0 64 64"`).
- `frontend/index.html` already declares **two** icons:
  ```html
  <link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg" />
  <link rel="icon" type="image/svg+xml" sizes="16x16" href="/favicon-16.svg" />
  ```
  Either produce a simplified 16px variant of the new mark for `favicon-16.svg` (fewer
  facets, still legible), or delete the `16x16` link and its file and keep only
  `favicon.svg`. Pick one and say which in your summary — do not leave the old mark
  sitting in `favicon-16.svg`.

---

## 5. Font: Syne out, Montserrat 800 in

1. `npm i @fontsource/montserrat` and `npm uninstall @fontsource/syne`.
2. In `frontend/src/main.tsx`, replace `import "@fontsource/syne/700.css";` with
   `import "@fontsource/montserrat/800.css";`. **Keep it as a JS side-effect import** —
   `frontend/src/index.css` documents why (`postcss-import` 500s on bare `@fontsource/...`
   specifiers on this Vite version). Keep `@fontsource/manrope/600.css` for the tagline.
3. `frontend/tailwind.config.js` declares `fontFamily.display = ["Syne", "system-ui",
   "sans-serif"]`. Change it to `["Montserrat", "system-ui", "sans-serif"]` (Logo.tsx sets the
   family inline, but the token must not drift).
4. Update the stale comments in `main.tsx`, at the top of `index.css`, and above the
   `display` token in `tailwind.config.js` — all three name "Syne 700".
5. Fallback stack: `Montserrat, 'Manrope', system-ui, sans-serif`, `font-display: swap`
   (fontsource sets this).
6. Montserrat 800 is used by the wordmark and the admin `SEMA` text in §3 — nowhere else.

---

## 6. Acceptance

Verify each, and report anything you couldn't:

- [ ] Sidebar shows mark + SEMA at 26px; coral and yellow facets visible and crisp.
- [ ] `<Logo size={12} />` renders mark-only.
- [ ] Alignment: at every size and in both orientations, the gap between mark and wordmark is
      exactly `size * 0.25` and the lockup is flush to the start edge. Test by dropping
      `<Logo size={64} />` into a 900px-wide container — it must stay hugging the left with a
      16px gap, not spread across the container.
- [ ] `<div className="text-white"><Logo variant="mono" /></div>` renders white.
- [ ] Admin aside header matches 7c: 20px mark + `SEMA` + `Admin`; `Back to SEMA` intact;
      the old `Organization admin` label text is gone.
- [ ] Login: EmailStep, CodeStep, and ErrorScreen each show a horizontal 44px lockup — mark
      and `SEMA` on one line — with the block centered in the card.
- [ ] "AI Business Advisor" appears **exactly once** per login screen. Check both `en` and
      `he`.
- [ ] Both favicon files resolved per §4; no old-mark SVG left in `frontend/public/`.
- [ ] `grep -rni "syne" frontend/` returns nothing (including package.json, package-lock,
      and comments).
- [ ] `grep -rn "logo-mark" frontend/` returns nothing — old SVGs deleted.
- [ ] `grep -rn "primary" frontend/src/components/brand/` — no leftover variant name.
- [ ] Montserrat appears only in `Logo.tsx`, the admin `SEMA` span, and the `main.tsx` import.
- [ ] `npm run build` and the typecheck pass.
- [ ] The mark is never mirrored on RTL screens.

Report the diff summary and the favicon-16 decision when done.
