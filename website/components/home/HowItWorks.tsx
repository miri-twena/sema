import { getDictionary, type Locale } from '@/lib/i18n';

export default function HowItWorks({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const steps = [
    { n: 1, title: t.s1Title, body: t.s1Body },
    { n: 2, title: t.s2Title, body: t.s2Body },
    { n: 3, title: t.s3Title, body: t.s3Body },
  ];
  return (
    <section id="how" data-screen-label="How it works" className="border-y border-border-faint bg-tint-bg">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.howKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.howTitle}</h2>
        </div>
        <div className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="flex flex-col gap-3 rounded-card border border-border-soft bg-white px-6 py-[26px]">
              <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-brand text-[15px] font-extrabold text-white">
                {s.n}
              </span>
              <h3 className="m-0 text-lg font-bold">{s.title}</h3>
              <p className="m-0 text-[14.5px] leading-[1.65] text-text-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
