import type { CSSProperties } from 'react';
import { getDictionary, type Locale } from '@/lib/i18n';
import HeroDemoCard from './hero/HeroDemoCard';
import FloatingFragments from './hero/FloatingFragments';

const ENTRANCE_STEP_MS = 120;

export default function Hero({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);

  const entrance = (index: number): CSSProperties => ({
    animation: `fade-up 600ms ease ${index * ENTRANCE_STEP_MS}ms both`,
  });

  return (
    <section
      data-screen-label="Hero"
      className="relative overflow-hidden"
      style={{ background: 'linear-gradient(180deg,#F7F8FF 0%,#FFFFFF 88%)' }}
    >
      <FloatingFragments />
      <div className="mx-auto grid max-w-container grid-cols-1 items-center gap-16 px-6 pb-20 pt-24 md:grid-cols-2">
        <div className="flex flex-col gap-[26px]">
          <span
            className="self-start rounded-full bg-brand-50 px-3.5 py-2 text-[13px] font-bold uppercase tracking-[.14em] text-brand-deep"
            style={entrance(0)}
          >
            {t.badge}
          </span>
          <h1
            className="m-0 text-[62px] font-extrabold leading-[1.06] tracking-[-.025em] text-text"
            style={entrance(1)}
          >
            {t.h1}
          </h1>
          <p className="m-0 max-w-[560px] text-xl leading-[1.65] text-text-muted" style={entrance(2)}>
            {t.sub}
          </p>
          <div className="mt-2 flex gap-3.5" style={entrance(3)}>
            <a
              href="#bookform"
              className="rounded-btn bg-brand px-7 py-4 text-base font-bold text-white no-underline transition-colors duration-150 hover:bg-brand-hover"
            >
              {t.cta}
            </a>
            <a
              href="#how"
              className="rounded-btn border border-border px-7 py-4 text-base font-bold text-text no-underline transition-colors duration-150 hover:bg-tint-bg"
            >
              {t.secondary}
            </a>
          </div>
        </div>

        <div style={entrance(2)}>
          <HeroDemoCard t={t} />
        </div>
      </div>
    </section>
  );
}
