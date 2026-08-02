import { BRAND } from "../../lib/tokens";

export type LogoVariant = "primary" | "inverse" | "mono";

export interface LogoProps {
  /** 'primary' (light backgrounds, default), 'inverse' (dark #15161C
   * backgrounds), or 'mono' (single-ink print/invoice contexts -- every part
   * renders `currentColor`, so it recolors with the surrounding text). */
  variant?: LogoVariant;
  /** Mark height in px. Drives every other dimension (gap, wordmark size). */
  size?: number;
  /** Force mark-only (no wordmark), regardless of size. */
  markOnly?: boolean;
  /** 'AI BUSINESS ADVISOR' under a stacked lockup. Implies `stacked`. */
  tagline?: boolean;
  /** Mark above wordmark, centered, instead of the default horizontal row. */
  stacked?: boolean;
  className?: string;
}

// Shared mark geometry (48x48 viewBox): an ascending data path with three
// nodes -- start, one interior waypoint, and the coral "decision point" at
// the end. The path's OTHER interior vertex (from the `l9 5` segment) is
// deliberately left bare, no node -- it only shapes the path's rise, the same
// way a real line chart doesn't dot every vertex, only the ones that matter.
const MARK_PATH = "M7 37L19 26l9 5L40 13";
const NODE_START = { cx: 7, cy: 37, r: 3.4 };
const NODE_MID = { cx: 19, cy: 26, r: 3.4 };
const NODE_END = { cx: 40, cy: 13, r: 6 }; // the coral decision point

function markColors(variant: LogoVariant): { stroke: string; start: string; mid: string; end: string } {
  switch (variant) {
    case "inverse":
      // Middle node matches the stroke (both Lavender 400) -- the spec names
      // #949CFF as both "the stroke on dark" and "the middle node on light",
      // but doesn't say what the middle node becomes once the stroke itself
      // already IS that color; blending it into the line reads as the
      // natural extension of how the primary variant treats it (a lighter
      // tint riding the same line), rather than introducing a 4th hue.
      return { stroke: BRAND.lavender400, start: BRAND.lavender700, mid: BRAND.lavender400, end: BRAND.coral };
    case "mono":
      // True single-ink reproduction (print/invoices/letterhead): every part
      // is `currentColor`, including the coral decision node -- the "never
      // recolor coral" rule is for the colored variants, where the whole
      // point of mono is that a second spot color isn't available.
      return { stroke: "currentColor", start: "currentColor", mid: "currentColor", end: "currentColor" };
    default:
      return { stroke: BRAND.lavender, start: BRAND.lavender200, mid: BRAND.lavender400, end: BRAND.coral };
  }
}

function wordmarkColor(variant: LogoVariant): string {
  if (variant === "inverse") return "#FFFFFF";
  if (variant === "mono") return "currentColor";
  return BRAND.lavender;
}

function Mark({ variant, size }: { variant: LogoVariant; size: number }) {
  const c = markColors(variant);
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden focusable="false" style={{ flexShrink: 0 }}>
      <path d={MARK_PATH} stroke={c.stroke} strokeWidth={3.6} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={NODE_START.cx} cy={NODE_START.cy} r={NODE_START.r} fill={c.start} />
      <circle cx={NODE_MID.cx} cy={NODE_MID.cy} r={NODE_MID.r} fill={c.mid} />
      <circle cx={NODE_END.cx} cy={NODE_END.cy} r={NODE_END.r} fill={c.end} />
    </svg>
  );
}

/**
 * The SEMA brand lockup (mark + wordmark). Renders inline SVG (no SVGR/`?react`
 * import plugin in this build) so `currentColor` works for the mono variant
 * and the mark can share color logic with its wordmark.
 *
 * Clear space: this component adds no margin of its own -- give it
 * `size * 0.5` of clear space on every side at each call site.
 */
export function Logo({ variant = "primary", size = 24, markOnly = false, tagline = false, stacked = false, className }: LogoProps) {
  const effectiveStacked = stacked || tagline;
  const wordmarkPx = Math.round(size * 0.77);
  // Below 15px the wordmark's counters (the enclosed counters inside E/A)
  // close up in Syne 700 and "SEMA" reads as a smudge -- enforced here, not
  // left to call sites, so no consumer can accidentally ship an illegible
  // wordmark by picking too small a size.
  const effectiveMarkOnly = markOnly || wordmarkPx < 15;
  const gap = size * 0.27;

  if (effectiveMarkOnly) {
    return (
      <span dir="ltr" className={className} style={{ display: "inline-flex", unicodeBidi: "isolate" }}>
        <Mark variant={variant} size={size} />
      </span>
    );
  }

  // The literal string, not text-transform: uppercase (SEMA) so a copy/paste
  // of the DOM text is already correct, and the tagline follows the same
  // rule for the same reason.
  const wordmarkEl = (
    <span
      style={{
        fontFamily: "'Syne', system-ui, sans-serif",
        fontWeight: 700,
        fontSize: wordmarkPx,
        letterSpacing: "0.02em",
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
        style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap, unicodeBidi: "isolate" }}
      >
        <Mark variant={variant} size={size} />
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
      style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", unicodeBidi: "isolate" }}
    >
      <Mark variant={variant} size={size} />
      <span style={{ marginTop: gap, display: "inline-flex" }}>{wordmarkEl}</span>
      {tagline && (
        <span
          style={{
            marginTop: size * 0.2,
            fontFamily: "'Manrope', system-ui, sans-serif",
            fontWeight: 600,
            fontSize: 12,
            letterSpacing: "0.24em",
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
