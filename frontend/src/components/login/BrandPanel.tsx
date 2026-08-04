import type { CSSProperties, ReactNode } from "react";
import { LOGIN_COPY } from "../../lib/loginCopy";
import { Logo } from "../brand/Logo";
import { MARK_FACETS } from "../brand/markFacets";

const MARK_SIZE = 48;
// The mark's speech-bubble-tail tip sits at x=52 in its 219-wide viewBox
// (login_redesign_prompt.md §2.2, an approved design decision -- the
// tagline/value line/chips indent to THAT point, not the lockup's left
// edge). markWidth = size * (219/185) is Logo.tsx's own aspect-ratio
// derivation; indent = markWidth * (52/219), which cancels down to
// size * 52 / 185 -- computed here, never hardcoded, so it stays correct if
// MARK_SIZE ever changes.
const TAIL_TIP_INDENT = (MARK_SIZE * 52) / 185;

// A stable slice of the SAME facet geometry Logo.tsx exports -- fewer
// facets than the full mark, so the bottom-left decoration reads as a
// fragment bleeding off-frame, not a second complete logo.
const PARTIAL_FACETS = MARK_FACETS.slice(0, 7);

function DecorativeMark({
  facets,
  size,
  opacity,
  style,
}: {
  facets: typeof MARK_FACETS;
  size: number;
  opacity: number;
  style: CSSProperties;
}) {
  return (
    <svg
      viewBox="0 0 219 185"
      fill="none"
      aria-hidden
      style={{ height: size, width: "auto", aspectRatio: "219 / 185", position: "absolute", opacity, ...style }}
    >
      {facets.map((f, i) => (
        <polygon key={i} points={f.points} fill={f.inverse} />
      ))}
    </svg>
  );
}

function Chip({ bg, color, children }: { bg: string; color: string; children: ReactNode }) {
  return (
    <span
      className="whitespace-nowrap font-semibold"
      style={{ background: bg, color, borderRadius: 999, padding: "4px 10px", fontSize: 11 }}
    >
      {children}
    </span>
  );
}

/**
 * The login split shell's left panel (login_redesign_prompt.md). Static
 * content, always English (login stays LTR/English throughout -- AGENTS.md).
 *
 * One component covers both layouts via Tailwind breakpoints rather than a
 * `compact` prop + two call sites: below `md` it's a plain top strip (mark +
 * tagline only, decorative facets and the value line/chips hidden); at `md`
 * and up it's the full ~46%-width panel with everything.
 */
export function BrandPanel() {
  const t = LOGIN_COPY.en;
  return (
    <div className="relative overflow-hidden shrink-0 bg-[#15161C] flex flex-col justify-start md:justify-center md:w-[46%] px-6 py-6 md:px-[30px] md:py-0">
      <div className="hidden md:block">
        <DecorativeMark facets={MARK_FACETS} size={190} opacity={0.14} style={{ top: -40, right: -60 }} />
        <DecorativeMark facets={PARTIAL_FACETS} size={150} opacity={0.09} style={{ bottom: -50, left: -50 }} />
      </div>

      <div className="relative z-10 w-full max-w-[280px] flex flex-col items-start">
        <Logo size={MARK_SIZE} variant="inverse" />
        <p
          className="uppercase whitespace-nowrap"
          style={{
            marginInlineStart: TAIL_TIP_INDENT,
            marginTop: 12,
            fontFamily: "'Manrope', system-ui, sans-serif",
            fontWeight: 600,
            fontSize: 12,
            letterSpacing: "0.22em",
            color: "#8A8FA3",
          }}
        >
          {t.brandTagline}
        </p>
        <p
          className="hidden md:block"
          style={{
            marginInlineStart: TAIL_TIP_INDENT,
            marginTop: 20,
            fontSize: 13,
            lineHeight: 1.6,
            color: "#B9BECF",
          }}
        >
          {t.brandValueLine}
        </p>
        <div className="hidden md:flex items-center gap-2" style={{ marginInlineStart: TAIL_TIP_INDENT, marginTop: 16 }}>
          <Chip bg="rgba(148,156,255,.16)" color="#A6ADFF">
            {t.chipPlainLanguage}
          </Chip>
          <Chip bg="rgba(242,201,76,.14)" color="#F2C94C">
            {t.chipLiveData}
          </Chip>
        </div>
      </div>
    </div>
  );
}
