import { BRAND } from "../../lib/tokens";
import { MARK_FACETS } from "./markFacets";

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
