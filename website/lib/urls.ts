import type { Locale } from './i18n';

export function homeHref(locale: Locale): string {
  return locale === 'he' ? '/he/' : '/';
}

export function pricingHref(locale: Locale): string {
  return locale === 'he' ? '/he/pricing/' : '/pricing/';
}
