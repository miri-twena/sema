import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';
import { homeHref, pricingHref } from '@/lib/urls';

export const dynamic = 'force-static';

// Every real, indexable route in both locales, each pointing at its own-locale
// hreflang twin (mirrors the per-page `alternates.languages` metadata).
export default function sitemap(): MetadataRoute.Sitemap {
  const routes: { en: string; he: string }[] = [
    { en: homeHref('en'), he: homeHref('he') },
    { en: pricingHref('en'), he: pricingHref('he') },
  ];

  return routes.flatMap(({ en, he }) => {
    const languages = { en: `${SITE_URL}${en}`, he: `${SITE_URL}${he}` };
    return [
      { url: `${SITE_URL}${en}`, alternates: { languages } },
      { url: `${SITE_URL}${he}`, alternates: { languages } },
    ];
  });
}
