import { getDictionary, type Locale } from '@/lib/i18n';
import ProactiveFeed from './ProactiveFeed';

export default function Proactive({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const alerts = [
    // tagFg values are darkened from the original coral/gold (#C05A4E, #B48A0A):
    // both failed WCAG AA (3.8:1, 2.9:1) against their pastel tagBg pill at this
    // 10.5px bold size. #B44C40/#896908 clear 4.5:1 while keeping the same hue.
    { bar: '#F2887C', tagBg: '#FDEBE8', tagFg: '#B44C40', tag: t.a1Tag, time: t.a1Time, text: t.a1Text },
    { bar: '#6C74F0', tagBg: '#EEEFFE', tagFg: '#4E56D6', tag: t.a2Tag, time: t.a2Time, text: t.a2Text },
    { bar: '#F2C94C', tagBg: '#FBF3D9', tagFg: '#896908', tag: t.a3Tag, time: t.a3Time, text: t.a3Text },
  ];
  return (
    <section id="proactive" data-screen-label="Proactive" className="bg-ink">
      <div className="mx-auto grid max-w-container grid-cols-1 items-center gap-14 px-6 py-24 md:grid-cols-2">
        <div className="flex flex-col gap-[18px]">
          <span
            className="self-start rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-[.14em] text-brand-400"
            style={{ background: 'rgba(148,156,255,.12)' }}
          >
            {t.proKicker}
          </span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em] text-white">{t.proTitle}</h2>
          <p className="m-0 max-w-[440px] text-[16.5px] leading-[1.7] text-[#A9ADC0]">{t.proSub}</p>
        </div>

        <div className="overflow-hidden rounded-card-lg bg-white shadow-proactive">
          <div className="flex items-center gap-2.5 border-b border-border-faint px-5 py-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/sema-mark-brand.svg" alt="" style={{ height: 20, width: 'auto' }} />
            <div className="flex flex-col">
              <span className="text-[14.5px] font-bold text-text">{t.homeGreeting}</span>
              <span className="text-[11.5px] text-text-faint">{t.homeSub}</span>
            </div>
          </div>
          <div className="bg-tint-bg px-[18px] py-4">
            <ProactiveFeed alerts={alerts} />
          </div>
        </div>
      </div>
    </section>
  );
}
