import { getDictionary, type Locale } from '@/lib/i18n';

/**
 * Visually hidden until focused (keyboard Tab from page load lands here first).
 * Targets #main-content, which HomePage/PricingPage wrap their body content in.
 */
export default function SkipLink({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  return (
    <a
      href="#main-content"
      className="fixed start-3 top-3 z-[100] -translate-y-16 rounded-[10px] bg-brand px-4 py-2.5 text-sm font-bold text-white no-underline transition-transform duration-150 focus:translate-y-0"
    >
      {t.skipToContent}
    </a>
  );
}
