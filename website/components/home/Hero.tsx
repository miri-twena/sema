import { getDictionary, type Locale } from '@/lib/i18n';

const BARS = [
  { value: '3.2', height: 52, month: 'Jan' },
  { value: '3.6', height: 62, month: 'Feb' },
  { value: '3.4', height: 57, month: 'Mar' },
  { value: '4.1', height: 74, month: 'Apr' },
  { value: '4.6', height: 88, month: 'May' },
  { value: '5.9', height: 114, month: 'Jun' },
];

export default function Hero({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  return (
    <section data-screen-label="Hero" style={{ background: 'linear-gradient(180deg,#F7F8FF 0%,#FFFFFF 88%)' }}>
      <div className="mx-auto grid max-w-container grid-cols-1 items-center gap-16 px-6 pb-20 pt-24 md:grid-cols-2">
        <div className="flex flex-col gap-[26px]">
          <span className="self-start rounded-full bg-brand-50 px-3.5 py-2 text-[13px] font-bold uppercase tracking-[.14em] text-brand-deep">
            {t.badge}
          </span>
          <h1 className="m-0 text-[62px] font-extrabold leading-[1.06] tracking-[-.025em] text-text">{t.h1}</h1>
          <p className="m-0 max-w-[560px] text-xl leading-[1.65] text-text-muted">{t.sub}</p>
          <div className="mt-2 flex gap-3.5">
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

        <div className="overflow-hidden rounded-card-lg border border-border bg-white shadow-hero">
          <div className="flex items-center gap-2.5 border-b border-border-faint px-6 py-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/sema-mark-brand.svg" alt="" style={{ height: 21, width: 'auto' }} />
            <span className="text-[13px] font-bold uppercase tracking-[.08em] text-text-faint">{t.demoLabel}</span>
          </div>
          <div className="flex flex-col gap-4 p-6">
            <div
              className="self-end rounded-ss-[16px] rounded-se-[16px] rounded-ee-[5px] rounded-es-[16px] bg-brand-50 px-4 py-3 text-[15px] font-semibold text-[#3A41A8]"
              style={{ maxWidth: '82%' }}
            >
              {t.demoQ}
            </div>
            <div className="flex flex-col gap-3.5 rounded-2xl border border-border-faint px-5 py-4">
              <div className="text-[15px] font-bold text-text">{t.demoTitle}</div>
              <div dir="ltr" className="flex h-[140px] items-end gap-4 px-1">
                {BARS.map((bar, i) => {
                  const isLast = i === BARS.length - 1;
                  return (
                    <div key={bar.month} className="flex flex-1 flex-col items-center gap-1.5">
                      <span className={`text-xs font-bold ${isLast ? 'text-brand-deep' : 'text-text-muted'}`}>
                        {bar.value}
                      </span>
                      <div
                        className={`w-full rounded-t-md ${isLast ? 'bg-brand-deep' : 'bg-brand'}`}
                        style={{ height: bar.height }}
                      />
                      <span className="text-[11px] text-text-faint">{bar.month}</span>
                    </div>
                  );
                })}
              </div>
              <div dir="ltr" className="flex gap-3">
                <div className="flex-1 overflow-hidden rounded-xl border border-border-soft">
                  <div className="h-1 bg-brand" />
                  <div className="px-3.5 py-3">
                    <div className="text-[11px] text-text-faint">Revenue H1</div>
                    <div className="text-lg font-extrabold text-text">
                      24.8M <span className="text-xs font-bold text-[#2F8F63]">+12%</span>
                    </div>
                  </div>
                </div>
                <div className="flex-1 overflow-hidden rounded-xl border border-border-soft">
                  <div className="h-1 bg-yellow" />
                  <div className="px-3.5 py-3">
                    <div className="text-[11px] text-text-faint">Gross margin</div>
                    <div className="text-lg font-extrabold text-text">
                      31% <span className="text-xs font-bold text-[#2F8F63]">+2.4</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
