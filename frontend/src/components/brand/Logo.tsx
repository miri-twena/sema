import { BRAND } from "../../lib/tokens";

export type LogoVariant = "brand" | "inverse" | "mono";

export interface LogoProps {
  /** 'brand' (light backgrounds, default), 'inverse' (dark backgrounds), or
   * 'mono' (single-ink print/invoice contexts -- every facet renders
   * `currentColor` at varying opacity, so it recolors with the surrounding
   * text). */
  variant?: LogoVariant;
  /** Mark HEIGHT in px -- the viewBox is wider than tall (219x185), so this
   * drives width via the SVG's own aspect ratio, plus wordmark size and gap. */
  size?: number;
  /** Force mark-only (no wordmark), regardless of size. */
  markOnly?: boolean;
  /** 'AI BUSINESS ADVISOR' under a stacked lockup. Implies `stacked`. */
  tagline?: boolean;
  /** Mark above wordmark, left-aligned, instead of the default horizontal row. */
  stacked?: boolean;
  className?: string;
}

// Facet geometry copied verbatim (point-for-point) from
// design_handoff_logo/assets/sema-mark-{brand,inverse,mono}.svg -- the three
// asset files share identical polygon points in identical order and differ
// only in fill, so a single array can drive all three variants.
const MARK_FACETS: { points: string; brand: string; inverse: string; monoOpacity: number }[] = [
  { points: "67.0,4.0 104.0,7.0 72.0,35.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.65 },
  { points: "120.0,4.0 157.0,7.0 143.0,37.0 119.0,7.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.8 },
  { points: "80.0,37.0 112.0,6.0 137.0,42.0 80.0,41.0", brand: BRAND.coral, inverse: "#F4998E", monoOpacity: 0.73 },
  { points: "163.0,7.0 211.0,54.0 211.0,58.0 150.0,43.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.9 },
  { points: "64.0,12.0 66.0,43.0 14.0,57.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.56 },
  { points: "77.0,45.0 140.0,47.0 106.0,106.0 101.0,103.0", brand: BRAND.lavender400, inverse: "#A3AAFF", monoOpacity: 0.72 },
  { points: "8.0,64.0 62.0,49.0 22.0,106.0 4.0,69.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.52 },
  { points: "26.0,106.0 69.0,49.0 75.0,54.0 98.0,110.0 26.0,110.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.61 },
  { points: "145.0,49.0 184.0,110.0 109.0,109.0", brand: BRAND.coral, inverse: "#F4998E", monoOpacity: 0.82 },
  { points: "153.0,49.0 215.0,67.0 192.0,107.0 187.0,105.0 152.0,52.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.92 },
  { points: "30.0,115.0 88.0,118.0 48.0,134.0 29.0,118.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.59 },
  { points: "107.0,115.0 159.0,119.0 102.0,130.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.77 },
  { points: "51.0,138.0 99.0,118.0 98.0,135.0 52.0,181.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.62 },
];

function wordmarkColor(variant: LogoVariant): string {
  if (variant === "inverse") return "#FFFFFF";
  if (variant === "mono") return "currentColor";
  return BRAND.lavender;
}

function Mark({ variant, size, markOnly }: { variant: LogoVariant; size: number; markOnly: boolean }) {
  return (
    <svg
      viewBox="0 0 219 185"
      fill="none"
      // `width="auto"` (the SVG attribute) does NOT derive width from the
      // viewBox aspect ratio here -- Chromium treats it as a plain block box
      // and stretches it to fill the available width instead. CSS
      // `aspect-ratio` + a definite `height` is the combination that's
      // actually spec-honored, so height/width live in `style`, not attrs.
      style={{ height: size, width: "auto", aspectRatio: "219 / 185", flexShrink: 0, display: "block" }}
      {...(markOnly ? { role: "img", "aria-label": "SEMA" } : { "aria-hidden": true, focusable: false })}
    >
      {MARK_FACETS.map((f, i) =>
        variant === "mono" ? (
          <polygon key={i} points={f.points} fill="currentColor" opacity={f.monoOpacity} />
        ) : (
          <polygon key={i} points={f.points} fill={variant === "inverse" ? f.inverse : f.brand} />
        ),
      )}
    </svg>
  );
}

/**
 * The SEMA brand lockup (mark + wordmark). Renders inline SVG (no SVGR/`?react`
 * import plugin in this build) so `currentColor` works for the mono variant.
 *
 * The lockup is flush-left and tight by construction -- `inline-flex` +
 * `width: fit-content` + `justifyContent: flex-start`, no `flex-grow` or
 * `margin-inline-start: auto` anywhere -- so no consumer can stretch it or
 * push the wordmark away from the mark by styling its own container.
 *
 * Clear space: this component adds no margin of its own -- give it
 * `size * 0.5` of clear space on every side at each call site.
 */
export function Logo({ variant = "brand", size = 24, markOnly = false, tagline = false, stacked = false, className }: LogoProps) {
  const effectiveStacked = stacked || tagline;
  const wordmarkPx = Math.round(size / 1.6);
  // Below 13px the wordmark reads as a smudge -- enforced here, not left to
  // call sites, so no consumer can accidentally ship an illegible wordmark.
  const effectiveMarkOnly = markOnly || wordmarkPx < 13;
  const gap = size * 0.25;

  if (effectiveMarkOnly) {
    return (
      <span
        dir="ltr"
        className={className}
        style={{ display: "inline-flex", width: "fit-content", unicodeBidi: "isolate" }}
      >
        <Mark variant={variant} size={size} markOnly />
      </span>
    );
  }

  // The literal string, not text-transform: uppercase (SEMA) so a copy/paste
  // of the DOM text is already correct, and the tagline follows the same
  // rule for the same reason.
  const wordmarkEl = (
    <span
      style={{
        fontFamily: "'Montserrat', system-ui, sans-serif",
        fontWeight: 800,
        fontSize: wordmarkPx,
        letterSpacing: "0.12em",
        lineHeight: 1,
        color: wordmarkColor(variant),
        whiteSpace: "nowrap",
      }}
    >
      SEMA
    </span>
  );

  if (!effectiveStacked) {
    return (
      <span
        dir="ltr"
        className={className}
        style={{
          display: "inline-flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "flex-start",
          gap,
          width: "fit-content",
          unicodeBidi: "isolate",
        }}
      >
        <Mark variant={variant} size={size} markOnly={false} />
        {wordmarkEl}
      </span>
    );
  }

  return (
    <span
      dir="ltr"
      className={className}
      // Column layout, but spacing is done with explicit marginTop on the
      // wordmark/tagline below rather than a container `gap` -- with 3
      // possible children (mark, wordmark, tagline) a shared `gap` would
      // apply between EVERY pair, double-spacing the tagline (its own
      // `size * 0.2` on top of the inherited `gap`). marginTop keeps each
      // gap independently controlled.
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-start",
        textAlign: "start",
        width: "fit-content",
        unicodeBidi: "isolate",
      }}
    >
      <Mark variant={variant} size={size} markOnly={false} />
      <span style={{ marginTop: gap, display: "inline-flex" }}>{wordmarkEl}</span>
      {tagline && (
        <span
          style={{
            marginTop: size * 0.2,
            fontFamily: "'Manrope', system-ui, sans-serif",
            fontWeight: 600,
            fontSize: 12,
            letterSpacing: "0.22em",
            color: "#8A8FA3",
            whiteSpace: "nowrap",
          }}
        >
          AI BUSINESS ADVISOR
        </span>
      )}
    </span>
  );
}
