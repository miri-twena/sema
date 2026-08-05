'use client';

import { getDictionary, type Locale } from '@/lib/i18n';
import { AskVignette, DashboardVignette, InsightVignette } from './featureVignettes';
import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

const CARD_FADE_MS = 550;
const STAGGER_STEP_MS = 110;

function FeatureCard({
  index,
  barColor,
  icon,
  title,
  body,
}: {
  index: number;
  barColor: string;
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const show = reduced || inView;
  const delay = index * STAGGER_STEP_MS;

  return (
    <div
      ref={ref}
      className="flex flex-col overflow-hidden rounded-card border border-border-soft"
      style={{
        opacity: show ? 1 : 0,
        transform: show ? 'translateY(0)' : 'translateY(18px)',
        transition: reduced ? 'none' : `opacity ${CARD_FADE_MS}ms ease ${delay}ms, transform ${CARD_FADE_MS}ms ease ${delay}ms`,
      }}
    >
      <div
        className={barColor}
        style={{
          height: 4,
          width: show ? '100%' : 0,
          transition: reduced ? 'none' : `width 500ms ease ${delay + CARD_FADE_MS}ms`,
        }}
      />
      <div className="flex flex-col gap-3.5 px-6 py-[26px]">
        {icon}
        <h3 className="m-0 text-[19px] font-bold">{title}</h3>
        <p className="m-0 text-[14.5px] leading-[1.65] text-text-muted">{body}</p>
      </div>
    </div>
  );
}

export default function Features({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const cards = [
    { bar: 'bg-brand', icon: <AskVignette />, title: t.f1Title, body: t.f1Body },
    { bar: 'bg-mint', icon: <DashboardVignette />, title: t.f2Title, body: t.f2Body },
    { bar: 'bg-yellow', icon: <InsightVignette />, title: t.f3Title, body: t.f3Body },
  ];
  return (
    <section id="features" data-screen-label="Features" className="bg-white">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.featKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.featTitle}</h2>
        </div>
        <div className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
          {cards.map((c, i) => (
            <FeatureCard
              key={c.title}
              index={i}
              barColor={c.bar}
              icon={c.icon}
              title={c.title}
              body={c.body}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
