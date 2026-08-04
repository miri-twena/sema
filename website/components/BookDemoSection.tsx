import DemoForm from './DemoForm';
import { getDictionary, type Locale } from '@/lib/i18n';

export default function BookDemoSection({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  return (
    <section id="bookform" data-screen-label="Book a demo" className="bg-ink">
      <div className="mx-auto grid max-w-container grid-cols-1 items-center gap-14 px-6 py-16 md:grid-cols-2 md:py-[88px]">
        <div className="flex flex-col gap-[18px]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand/sema-mark-inverse.svg"
            alt=""
            style={{ height: 52, width: 'auto' }}
            className="self-start"
          />
          <h2 className="m-0 text-[36px] font-extrabold leading-[1.15] tracking-[-.02em] text-white">{t.ctaTitle}</h2>
          <p className="m-0 max-w-[420px] text-base leading-[1.65] text-[#A9ADC0]">{t.ctaSub}</p>
        </div>
        <DemoForm t={t} />
      </div>
    </section>
  );
}
