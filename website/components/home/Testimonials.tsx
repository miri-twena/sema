import { getDictionary, getQuotes, type Locale } from '@/lib/i18n';

export default function Testimonials({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const quotes = getQuotes(locale);
  return (
    <section id="quotes" data-screen-label="Testimonials" className="bg-white">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.quoteKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.quoteTitle}</h2>
        </div>
        <div className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
          {quotes.map((q) => (
            <div key={q.name} className="flex flex-col gap-[18px] rounded-card border border-border-soft px-6 py-[26px]">
              <p className="m-0 text-[15px] leading-[1.7] text-text">&ldquo;{q.text}&rdquo;</p>
              <div className="mt-auto flex items-center gap-[11px]">
                <span
                  className="flex h-[38px] w-[38px] flex-none items-center justify-center rounded-full text-[13px] font-bold"
                  style={{ background: q.tint, color: q.color }}
                >
                  {q.init}
                </span>
                <div className="flex flex-col">
                  <span className="text-[13.5px] font-bold">{q.name}</span>
                  <span className="text-xs text-text-faint">{q.role}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
