'use client';

import { getDictionary, type Locale } from '@/lib/i18n';
import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

const CARD_FADE_MS = 550;
const STAGGER_STEP_MS = 110;

function StepCard({ index, title, body }: { index: number; title: string; body: string }) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const show = reduced || inView;
  const delay = index * STAGGER_STEP_MS;

  return (
    <div
      ref={ref}
      className="flex flex-col gap-3 rounded-card border border-border-soft bg-white px-6 py-[26px]"
      style={{
        opacity: show ? 1 : 0,
        transform: show ? 'translateY(0)' : 'translateY(18px)',
        transition: reduced ? 'none' : `opacity ${CARD_FADE_MS}ms ease ${delay}ms, transform ${CARD_FADE_MS}ms ease ${delay}ms`,
      }}
    >
      <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-brand text-[15px] font-extrabold text-white">
        {index + 1}
      </span>
      <h3 className="m-0 text-lg font-bold">{title}</h3>
      <p className="m-0 text-[14.5px] leading-[1.65] text-text-muted">{body}</p>
    </div>
  );
}

export default function HowItWorks({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const steps = [
    { title: t.s1Title, body: t.s1Body },
    { title: t.s2Title, body: t.s2Body },
    { title: t.s3Title, body: t.s3Body },
  ];
  return (
    <section id="how" data-screen-label="How it works" className="border-y border-border-faint bg-tint-bg">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.howKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.howTitle}</h2>
        </div>
        <div className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
          {steps.map((step, i) => (
            <StepCard key={step.title} index={i} title={step.title} body={step.body} />
          ))}
        </div>
      </div>
    </section>
  );
}
