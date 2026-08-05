import { getDictionary, type Locale } from '@/lib/i18n';
import { getCarouselSlides } from './carousel/slides';
import ProductCarousel from './carousel/ProductCarousel';

export default function ProductShowcase({ locale }: { locale: Locale }) {
  const t = getDictionary(locale);
  const slides = getCarouselSlides(t);
  return (
    <section data-screen-label="Product showcase" className="bg-white">
      <div className="mx-auto flex max-w-container flex-col gap-12 px-6 py-24">
        <div className="flex max-w-[640px] flex-col gap-3 self-center text-center">
          <span className="text-xs font-bold uppercase tracking-[.14em] text-text-faint">{t.carouselKicker}</span>
          <h2 className="m-0 text-4xl font-extrabold leading-[1.15] tracking-[-.02em]">{t.carouselTitle}</h2>
        </div>
        <ProductCarousel slides={slides} locale={locale} />
      </div>
    </section>
  );
}
