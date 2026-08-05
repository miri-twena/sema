import Logo from './Logo';
import { getDictionary, type Locale } from '@/lib/i18n';

export default function Footer({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  return (
    <footer data-screen-label="Footer" className="border-t border-[#23242E] bg-ink-footer">
      <div className="mx-auto flex max-w-container flex-wrap items-center gap-6 px-6 py-9">
        <Logo variant="inverse" markHeight={20} wordmarkSize={12.5} />
        {/* #6E7284/text-faint both fail 4.5:1 on this dark ink-footer bg (3.98:1 and,
            once darkened for light-bg AA, worse) -- #A9ADC0 is the same muted tone
            already used for body copy on dark sections (Proactive/BookDemo) and
            clears AA comfortably here (8.5:1). */}
        <span className="text-[12.5px] text-[#A9ADC0]">{t.footTag}</span>
        <div className="ms-auto flex gap-5 text-[12.5px] text-[#A9ADC0]">
          <span className="cursor-pointer transition-colors duration-150 hover:text-white">{t.footPrivacy}</span>
          <span className="cursor-pointer transition-colors duration-150 hover:text-white">{t.footTerms}</span>
          <span dir="ltr">© 2026 SEMA</span>
        </div>
      </div>
    </footer>
  );
}
