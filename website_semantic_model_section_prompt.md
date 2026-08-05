# Task: new homepage section — the semantic model ("SEMA's brain")

User request (2026-08-05) with approved copy and a visual reference. Add a new section to
the marketing homepage presenting the semantic model as SEMA's brain — why answers can be
trusted. Reference illustration: `website/design-refs/semantic-model-section.png` (match
its style, not pixel-for-pixel).

## Placement

Directly AFTER the Features section ("הבידול של SEMA") and before the carousel — it deepens
the differentiation story (feature card f1 already teases the semantic model; this section
expands it). Section id: `semantic-model`, `data-screen-label="Semantic model"`.

## Copy — Hebrew is the user's approved text, use VERBATIM

- Kicker: `המוח של SEMA`
- H2: `SEMA לא מנחשת למה התכוונתם.`
- Body: `המודל הסמנטי מחבר בין השפה העסקית לנתונים המאושרים של הארגון. הוא מלמד את SEMA איך העסק באמת עובד ומצמצם טעויות ופרשנויות שגויות.`
- Three checkmarks (✓, green — the site's success green):
  1. `הגדרות ומדדים שמותאמים ספציפית לעסק`
  2. `אותו חישוב עקבי בכל שאלה ובכל תשובה`
  3. `שקיפות מלאה לגבי הנתונים וההגדרות שנבדקו`

English (drafted to match — flag in the completion note that EN copy is a translation
awaiting the user's eye):

- Kicker: `SEMA's brain`
- H2: `SEMA doesn't guess what you meant.`
- Body: `The semantic model connects your business language to your organization's
  approved data. It teaches SEMA how your business actually works — reducing errors and
  misreadings.`
- Checks: `Definitions and metrics tailored to your business` / `The same consistent
  calculation in every question and answer` / `Full transparency about the data and
  definitions behind every answer`

All strings via `lib/i18n` (en + he + `types.ts` — the Dictionary type gates parity).

## Layout

Two-column like Hero/Proactive (text | visual), light background (white or the soft
`#F7F8FF` tint — pick whichever alternates correctly with the neighbors so two adjacent
sections don't share a background). Text column: kicker, H2, body, check list. Checkmarks
are list items with a green ✓ icon (logical-start aligned), 15px body text.

## The illustration (from the reference image)

A card mocking the semantic model mapping — business term → approved definition:

- Card header: small brand facet-mark + title `המודל הסמנטי של העסק שלכם` /
  `Your business's semantic model`, hairline divider below.
- Three mapping rows, hairline-separated. Each row: the business TERM in quotes on the
  logical start side (plain text, muted), a small arrow pointing toward the definition,
  and the DEFINITION in a soft lavender chip (bg `#EEF0FF`-family, brand-deep text,
  rounded-lg) on the logical end side.
  - he: `"הכנסות"` → `עסקאות ששולמו, ללא מע״מ וביטולים` · `"לקוח פעיל"` → `פעילות ב-90
    הימים האחרונים` · `"רווחיות"` → `הכנסה פחות עלות ישירה ומשלוח`
  - en: `"Revenue"` → `Paid transactions, excluding VAT and cancellations` · `"Active
    customer"` → `Activity in the last 90 days` · `"Profitability"` → `Revenue minus
    direct costs and shipping`
- **RTL note:** the arrow points in the READING direction toward the definition (← in
  Hebrew as in the reference, → in English). Use a logical-direction-aware arrow (flip per
  locale), not a hardcoded glyph.
- Motion, consistent with the rest of the page (#38 conventions): section reveals on
  scroll (fade-up stagger); the three mapping rows stagger in, and each arrow can draw
  itself briefly. Inert under `prefers-reduced-motion`. NOTHING on a timer after the
  entrance — no loops (the #41 rule).

## Housekeeping

- Header nav: do NOT add a nav item (the nav is full); the section is discoverable by
  scroll. If an anchor is wanted later, `#semantic-model` already works.
- `website_qa_prompt.md` (#40): if still open when this lands, add the new section to its
  RTL/visual checklists; if #40 already closed, run its §2/§4 checks yourself on this
  section (both locales, 4 breakpoints) and include the evidence in the completion note.

## Accept

- [ ] Section renders after Features, both locales, copy verbatim (he) / drafted (en).
- [ ] Illustration matches the reference style: header + 3 term→definition rows, chips,
      correct arrow direction per locale.
- [ ] Reveal motion consistent with the page, reduced-motion inert, no timer loops.
- [ ] `tsc` + lint + `npm run build` green; Dictionary parity (types.ts) enforced.
