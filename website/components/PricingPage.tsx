import Header from './Header';
import Footer from './Footer';
import BookDemoSection from './BookDemoSection';
import { DiamondBulletIcon } from './icons';
import { getDictionary, getPoints, type Locale } from '@/lib/i18n';

export default function PricingPage({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const points = getPoints(locale);

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Header locale={locale} page="pricing" />

      <section data-screen-label="Pricing" style={{ background: 'linear-gradient(180deg,#F7F8FF 0%,#FFFFFF 60%)' }}>
        <div className="mx-auto flex max-w-container flex-col gap-[52px] px-6 pb-24 pt-[84px]">
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="rounded-full bg-brand-50 px-3 py-1.5 text-xs font-bold uppercase tracking-[.14em] text-brand-deep">
              {t.navPricing}
            </span>
            <h1 className="m-0 text-[44px] font-extrabold leading-[1.1] tracking-[-.025em]">{t.priceTitle}</h1>
            <p className="m-0 max-w-[520px] text-[17px] text-text-muted">{t.priceSub}</p>
          </div>

          <div className="grid grid-cols-1 items-stretch gap-[22px] md:grid-cols-3">
            {/* Starter */}
            <div className="flex flex-col gap-5 rounded-card-lg border border-border-soft bg-white px-7 py-[30px]">
              <div className="flex flex-col gap-1.5">
                <span className="text-[15px] font-bold text-text-muted">{t.tier1Name}</span>
                <div dir="ltr" className="flex items-baseline gap-1.5">
                  <span className="text-[38px] font-extrabold tracking-[-.02em]">$490</span>
                  <span className="text-sm text-text-faint">{t.perMonth}</span>
                </div>
                <span className="text-[13.5px] text-text-faint">{t.tier1Sub}</span>
              </div>
              <div className="flex flex-col gap-[11px]">
                {points.t1.map((p) => (
                  <div key={p} className="flex items-center gap-2.5 text-sm text-[#3B3F4E]">
                    <DiamondBulletIcon />
                    <span>{p}</span>
                  </div>
                ))}
              </div>
              <a
                href="#bookform"
                className="mt-auto rounded-[11px] border border-border py-3 text-center text-[14.5px] font-bold text-text no-underline transition-colors duration-150 hover:bg-tint-bg"
              >
                {t.cta}
              </a>
            </div>

            {/* Growth (highlighted) */}
            <div className="relative flex flex-col gap-5 rounded-card-lg border-2 border-brand bg-white px-7 py-[30px] shadow-growth">
              <span className="absolute -top-[13px] start-7 rounded-full bg-brand px-3 py-[5px] text-[11px] font-bold uppercase tracking-[.08em] text-white">
                {t.popular}
              </span>
              <div className="flex flex-col gap-1.5">
                <span className="text-[15px] font-bold text-brand-deep">{t.tier2Name}</span>
                <div dir="ltr" className="flex items-baseline gap-1.5">
                  <span className="text-[38px] font-extrabold tracking-[-.02em]">$1,290</span>
                  <span className="text-sm text-text-faint">{t.perMonth}</span>
                </div>
                <span className="text-[13.5px] text-text-faint">{t.tier2Sub}</span>
              </div>
              <div className="flex flex-col gap-[11px]">
                {points.t2.map((p) => (
                  <div key={p} className="flex items-center gap-2.5 text-sm text-[#3B3F4E]">
                    <DiamondBulletIcon />
                    <span>{p}</span>
                  </div>
                ))}
              </div>
              <a
                href="#bookform"
                className="mt-auto rounded-[11px] bg-brand py-3 text-center text-[14.5px] font-bold text-white no-underline transition-colors duration-150 hover:bg-brand-hover"
              >
                {t.cta}
              </a>
            </div>

            {/* Enterprise (dark) */}
            <div className="flex flex-col gap-5 rounded-card-lg bg-ink px-7 py-[30px]">
              <div className="flex flex-col gap-1.5">
                <span className="text-[15px] font-bold text-brand-400">{t.tier3Name}</span>
                <div className="text-[38px] font-extrabold tracking-[-.02em] text-white">{t.custom}</div>
                <span className="text-[13.5px] text-text-faint">{t.tier3Sub}</span>
              </div>
              <div className="flex flex-col gap-[11px]">
                {points.t3.map((p) => (
                  <div key={p} className="flex items-center gap-2.5 text-sm text-[#C9CBDA]">
                    <DiamondBulletIcon tone="dark" />
                    <span>{p}</span>
                  </div>
                ))}
              </div>
              <a
                href="#bookform"
                className="mt-auto rounded-[11px] bg-white py-3 text-center text-[14.5px] font-bold text-text no-underline transition-colors duration-150 hover:bg-brand-50"
              >
                {t.talkSales}
              </a>
            </div>
          </div>

          <p className="m-0 text-center text-[13.5px] text-text-faint">{t.priceNote}</p>
        </div>
      </section>

      <BookDemoSection locale={locale} />
      <Footer locale={locale} />
    </div>
  );
}
