# SEMA — login split-panel redesign

**Run AFTER `logo_implementation_prompt.md` (#35).** This task consumes the new `Logo`
component (inverse variant, horizontal lockup) that #35 creates. Approved mockup: split-panel
login — dark brand panel left, form right.

Scope: `frontend/src/components/login/` + `frontend/src/lib/loginCopy.ts` only. The mocked
state machine (`useLoginFlow`), `DevStatePanel`, the invite-org context, and all step
logic/states are untouched — this is a layout + copy reskin of the same flow.

---

## 1. Layout: LoginPage owns a split shell

> **AMENDED 2026-08-04 (user review of the built full-viewport version — supersedes the
> original §1):** the split must NOT stretch across the whole viewport. It becomes a
> **contained split card, centered on the regular product background.** If the full-height
> version is already built, refit it: the split moves from the page to a card; the panels'
> internal content (§2, §3) is unchanged.

Structure:

- **Page:** `min-h-screen`, background `bg` (`#F8FAFC` — the standard product background),
  split card centered both axes (`flex items-center justify-center`), `padding: 24px` so the
  card never touches viewport edges.
- **Split card:** `width: min(92vw, 860px)`, `min-height: 520px` (content-driven beyond
  that), `border-radius` = the existing `loginCard` token (16px), `overflow-hidden`,
  `border border-line`, `shadow-loginCard`. The card contains the two panels side by side.
- **Left panel — brand.** ~46% of the card width, background `BRAND.ink` (`#15161C` from
  `frontend/src/lib/tokens.ts`), content vertically centered, `padding-inline: 30px`,
  content column max-width ~280px. Decorative facets clip against the card's rounded
  corners (the card's `overflow-hidden` handles it).
- **Right panel — form.** Remaining width, background `surface` (white — reads as the
  card's own surface; the page behind stays `#F8FAFC`), the step content (EmailStep /
  CodeStep) centered both axes at ~min(84%, 300px) width. **No inner card chrome**: the old
  `rounded-loginCard border shadow-loginCard` wrapper stays gone — the split card itself is
  now the only card.
- The split shell renders for the `email` and `code` steps and the `redirecting` beat.
- **ErrorScreen** is not split, but change its `<Logo size={44} stacked />` to the
  horizontal `<Logo size={44} />` so it matches the new brand direction.
- **Note:** #35 was completed with the login steps still on the stacked-with-tagline lockup
  (`<Logo size={64} stacked tagline />` + a duplicate `{t.headline}` line right under it —
  the same phrase twice). That duplication is resolved by THIS task: both disappear when the
  card is replaced by the split shell (§2–§3). Don't look for a separate dedup fix in #35.
- Login remains LTR/English throughout (existing `lang = "en"` decision stands).

**Responsive:** below `md` (~768px), the card stays (narrower, `min(92vw, 420px)`) and the
brand panel collapses to a top strip inside it: horizontal lockup + tagline only, `py-6`,
decorative facets hidden, form below it. Never side-by-side squeezed.

## 2. Brand panel contents (top to bottom)

All content left-aligned. Implementation lives in `LoginPage.tsx` (or a small
`BrandPanel.tsx` in the same folder).

1. **Lockup:** `<Logo size={48} variant="inverse" />` — horizontal, flush-left per #35 §2.
2. **Tagline:** `AI BUSINESS ADVISOR` — Manrope 600, 12px at full scale (9.5px was mockup
   scale; use 12px real), `letter-spacing: .22em`, uppercase, `#8A8FA3`, `margin-top: 12px`.
   **Alignment (approved design decision):** the tagline's left edge starts exactly under
   the tip of the mark's speech-bubble tail — NOT at the lockup's left edge. The tail tip is
   at x=52 in the mark's 219-wide viewBox, so indent = `markWidth * (52/219)` where
   `markWidth = size * (219/185)`. For size=48 that's ≈13.5px. Compute it from the size
   constant, don't hardcode 13.5, and comment the derivation.
3. **Value line** (same indent as tagline), `margin-top: 20px`, ~13px, line-height 1.6,
   color `#B9BECF`: **"Plain questions. Answers from your data."** — approved copy, do not
   improvise. Add it to `loginCopy.ts` as `brandValueLine` (en; mirror a Hebrew translation
   in `he` for parity even though login renders en).
4. **Feature chips** (same indent), `margin-top: 16px`, two pills:
   - `Plain language` — bg `rgba(148,156,255,.16)`, text `#A6ADFF`
   - `Live data` — bg `rgba(242,201,76,.14)`, text `#F2C94C`
   Pill: 999px radius, ~11px semibold, `padding: 4px 10px`. Add both labels to
   `loginCopy.ts` too.
5. **Decorative facets:** two absolutely-positioned copies of the mark geometry (inverse
   fills), clipped by the panel (`overflow-hidden`): one top-right (~190px tall, opacity
   .14, offset out of frame right/top), one bottom-left (partial facet subset, ~150px,
   opacity .09, offset out of frame left/bottom). `aria-hidden`. Import the geometry from
   the brand SVG assets #35 added — do not redraw. Real content sits above them
   (`position: relative`).

The single "AI Business Advisor" phrase for these screens now lives here (the tagline).
Remove the `<p>{t.headline}</p>` line from both steps (§3) — `headline` stays in
`loginCopy.ts`, unused, like `LOGIN_COPY.he`.

## 3. Form panel contents

**EmailStep:**

- Heading `Welcome back` — ~17px, semibold, ink. Below it `Sign in with your work email.` —
  ~12.5px, muted. Both new `loginCopy.ts` keys (`welcomeTitle`, `welcomeSubtitle`).
- Then the existing form, unchanged: email label + input (mail icon, focus ring), primary
  `Continue` button, `or` divider, Google/Microsoft SSO buttons, trouble link. Keep every
  existing state (submitting, validation, comingSoonTooltip, etc.).
- The invite-org block (`Joining X` + org logo) renders above the heading, left-aligned,
  when present.

**CodeStep:** same shell; heading stays the `codeSentTo(email)` line (keep it — it's
informative), just restyled to sit where `Welcome back` sits. Code input, resend, change
email, attempts/error states all unchanged.

**Redirecting beat:** keep the current spinner treatment, centered in the form panel.

## 4. Acceptance

- [ ] Email + code steps render the split CARD — centered, `min(92vw, 860px)`, rounded,
      on the standard `#F8FAFC` page background; nothing about the login stretches
      full-viewport. Error screen unchanged from #35 (plus horizontal lockup).
- [ ] Brand panel: inverse 48px horizontal lockup, tagline/value/chips all starting at the
      computed tail-tip indent, two decorative facet layers behind content.
- [ ] "AI Business Advisor" appears exactly once (brand panel tagline); `t.headline` is no
      longer rendered anywhere.
- [ ] Value line reads exactly "Plain questions. Answers from your data."
- [ ] Every login state still reachable: validation error, sending, wrong code, exhausted
      attempts, resend cooldown, change email, coming-soon tooltip, invite-org context
      (`?client_id=ecommerce`), DevStatePanel.
- [ ] <768px: brand strip on top, form below, nothing clipped.
- [ ] No hardcoded copy in TSX — all new strings go through `loginCopy.ts` (en + he parity;
      the parity test in the locales suite must still pass if it covers this file).
- [ ] `npm run build` + typecheck pass.
