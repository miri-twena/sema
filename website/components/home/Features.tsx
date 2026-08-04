import { getDictionary, type Locale } from '@/lib/i18n';
import { ChatFacetIcon, BarChartFacetIcon, SparkFacetIcon } from '../icons';

export default function Features({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const cards = [
    { bar: 'bg-brand', iconBg: 'bg-brand-50', icon: <ChatFacetIcon />, title: t.f1Title, body: t.f1Body },
    { bar: 'bg-mint', iconBg: 'bg-[#E4F6EC]', icon: <BarChartFacetIcon />, title: t.f2Title, body: t.f2Body },
    { bar: 'bg-yellow', iconBg: 'bg-[#FBF3D9]', icon: <SparkFacetIcon />, title: t.f3Title, body: t.f3Body },
  ];
  return (
    <section id="features" data-screen-label="Features" className="bg-white">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.featKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.featTitle}</h2>
        </div>
        <div className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
          {cards.map((c) => (
            <div key={c.title} className="flex flex-col overflow-hidden rounded-card border border-border-soft">
              <div className={`h-1 ${c.bar}`} />
              <div className="flex flex-col gap-3.5 px-6 py-[26px]">
                <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${c.iconBg}`}>{c.icon}</div>
                <h3 className="m-0 text-[19px] font-bold">{c.title}</h3>
                <p className="m-0 text-[14.5px] leading-[1.65] text-text-muted">{c.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
