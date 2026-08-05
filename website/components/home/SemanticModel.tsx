'use client';

import { getDictionary, type Locale } from '@/lib/i18n';
import Reveal from '../Reveal';
import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

const ROW_STAGGER_MS = 130;

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="mt-0.5 flex-none">
      <circle cx="12" cy="12" r="12" fill="#E4F6EC" />
      <path d="M7.5 12.5l3 3 6-6.5" stroke="#297C56" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

function DefinitionArrow({ isRtl, show, reduced, delay }: { isRtl: boolean; show: boolean; reduced: boolean; delay: number }) {
  // Points in the reading direction, toward the definition chip: right in LTR, left in RTL --
  // a hardcoded glyph (e.g. an arrow character) would only flip visually via bidi reordering
  // of the surrounding text, not on its own, so the two point sets are picked explicitly.
  const points = isRtl ? '15,4 7,12 15,20' : '9,4 17,12 9,20';
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="flex-none text-text-faint">
      <polyline
        points={points}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        style={{
          strokeDasharray: 24,
          strokeDashoffset: reduced || show ? 0 : 24,
          transition: reduced ? 'none' : `stroke-dashoffset 450ms ease ${delay + 150}ms`,
        }}
      />
    </svg>
  );
}

function MappingRow({ term, definition, index, isRtl }: { term: string; definition: string; index: number; isRtl: boolean }) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const show = reduced || inView;
  const delay = index * ROW_STAGGER_MS;

  return (
    <div
      ref={ref}
      className="flex items-center justify-between gap-4 px-6 py-4"
      style={{
        opacity: show ? 1 : 0,
        transform: show ? 'translateY(0)' : 'translateY(12px)',
        transition: reduced ? 'none' : `opacity 500ms ease ${delay}ms, transform 500ms ease ${delay}ms`,
      }}
    >
      <span className="flex-none text-[14.5px] text-text-muted">{term}</span>
      <DefinitionArrow isRtl={isRtl} show={show} reduced={reduced} delay={delay} />
      <span className="rounded-lg bg-brand-50 px-3.5 py-2 text-[13.5px] font-semibold leading-[1.4] text-brand-deep">
        {definition}
      </span>
    </div>
  );
}

export default function SemanticModel({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const isRtl = locale === 'he';
  const rows = [
    { term: t.smTerm1, definition: t.smDef1 },
    { term: t.smTerm2, definition: t.smDef2 },
    { term: t.smTerm3, definition: t.smDef3 },
  ];
  const checks = [t.smCheck1, t.smCheck2, t.smCheck3];

  return (
    <section id="semantic-model" data-screen-label="Semantic model" className="bg-tint-hero">
      <div className="mx-auto grid max-w-container grid-cols-1 items-center gap-14 px-6 py-24 md:grid-cols-2">
        <Reveal>
          <div className="flex flex-col gap-[18px]">
            <span className="self-start rounded-full bg-brand-50 px-3.5 py-2 text-[13px] font-bold uppercase tracking-[.14em] text-brand-deep">
              {t.smKicker}
            </span>
            <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em] text-text">{t.smTitle}</h2>
            <p className="m-0 max-w-[480px] text-[16px] leading-[1.7] text-text-muted">{t.smBody}</p>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {checks.map((check) => (
                <li key={check} className="flex items-start gap-2.5">
                  <CheckIcon />
                  <span className="text-[15px] leading-[1.5] text-text">{check}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Reveal index={1}>
          <div className="overflow-hidden rounded-card-lg border border-border bg-white shadow-hero">
            <div className="flex items-center gap-2.5 border-b border-border-faint px-6 py-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/brand/sema-mark-brand.svg" alt="" style={{ height: 20, width: 'auto' }} />
              <span className="text-[14.5px] font-bold text-text">{t.smCardTitle}</span>
            </div>
            <div className="divide-y divide-border-faint">
              {rows.map((row, i) => (
                <MappingRow key={row.term} term={row.term} definition={row.definition} index={i} isRtl={isRtl} />
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
