# SEMA website — replace the three feature icons ONLY

Scope: the three cards in the **Features** section of the marketing site (`website/`).
Touch NOTHING else — no other sections, no copy, no colors, no layout, no other icons.
If the Features section currently renders an icon tile (44x44 rounded square with a small icon inside), remove that tile entirely and put the new SVG in its place.

Each card gets a "micro-UI vignette": a tiny piece of real product UI as an inline SVG, instead of an icon. Copy the markup below EXACTLY, including the `<animate>` elements (SMIL animations: blinking cursor, pulsing alert dot). Do not convert to an icon library, do not simplify, do not strip the animations.

## Card 1 — Ask in plain language

```html
<svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true"><rect x="1" y="12" width="68" height="24" rx="12" fill="#FFFFFF" stroke="#E0E2EE" stroke-width="1.5"></rect><rect x="12" y="21.5" width="26" height="5" rx="2.5" fill="#C7CDFF"></rect><rect x="40" y="22" width="2" height="10" fill="#6C74F0"><animate attributeName="opacity" values="1;0;1" dur="1.2s" repeatCount="indefinite"></animate></rect><circle cx="56" cy="24" r="8" fill="#6C74F0"></circle><path d="M53 24h6m-2.5-2.5L59 24l-2.5 2.5" stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path></svg>
```

## Card 2 — Dashboards that build themselves

```html
<svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true"><rect x="3" y="4" width="30" height="40" rx="6" fill="#FFFFFF" stroke="#E0E2EE" stroke-width="1.5"></rect><rect x="3" y="4" width="30" height="3" rx="1.5" fill="#6C74F0"></rect><rect x="9" y="14" width="12" height="4" rx="2" fill="#DADCEA"></rect><rect x="9" y="22" width="18" height="6" rx="2" fill="#3B3F4E"></rect><rect x="9" y="33" width="4" height="7" rx="1.5" fill="#C7CDFF"></rect><rect x="15" y="30" width="4" height="10" rx="1.5" fill="#949CFF"></rect><rect x="21" y="26" width="4" height="14" rx="1.5" fill="#6C74F0"></rect><rect x="37" y="4" width="30" height="40" rx="6" fill="#FFFFFF" stroke="#E0E2EE" stroke-width="1.5"></rect><rect x="37" y="4" width="30" height="3" rx="1.5" fill="#F2C94C"></rect><rect x="43" y="14" width="12" height="4" rx="2" fill="#DADCEA"></rect><rect x="43" y="22" width="14" height="6" rx="2" fill="#3B3F4E"></rect><path d="M43 38l6-5 4 2.5 8-7.5" stroke="#F2887C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path></svg>
```

## Card 3 — Insights before you ask

```html
<svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true"><rect x="1" y="4" width="62" height="18" rx="9" fill="#FFFFFF" stroke="#E0E2EE" stroke-width="1.5"></rect><circle cx="12" cy="13" r="4" fill="#F2887C"></circle><circle cx="12" cy="13" r="4" fill="none" stroke="#F2887C" stroke-width="1.2" opacity=".5"><animate attributeName="r" values="4;8" dur="1.6s" repeatCount="indefinite"></animate><animate attributeName="opacity" values=".5;0" dur="1.6s" repeatCount="indefinite"></animate></circle><rect x="21" y="9" width="30" height="3.5" rx="1.75" fill="#3B3F4E"></rect><rect x="21" y="15" width="20" height="3" rx="1.5" fill="#DADCEA"></rect><rect x="7" y="28" width="62" height="18" rx="9" fill="#FFFFFF" stroke="#E0E2EE" stroke-width="1.5" opacity=".65"></rect><circle cx="18" cy="37" r="4" fill="#F2C94C" opacity=".8"></circle><rect x="27" y="33" width="26" height="3.5" rx="1.75" fill="#B9BCCB"></rect><rect x="27" y="39" width="16" height="3" rx="1.5" fill="#E3E5EF"></rect></svg>
```

## Placement

Inside each feature card, the SVG sits where the old icon tile was: first element in the card body, above the title, with the card's existing padding and vertical gap unchanged. The SVG is left-aligned (inline-start in RTL) at its natural size (70x48).

## Acceptance

- The three Features cards show the vignettes; the cursor blinks and the alert dot pulses.
- `git diff` shows changes ONLY in the Features section markup (and its extracted icon components, if any). No other file or section changed.
- Both locales (EN/HE) show the same vignettes; no mirroring in RTL.
