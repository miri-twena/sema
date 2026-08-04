import type { Locale, Dictionary } from './types';
import { en } from './en';
import { he } from './he';

export type { Locale, Dictionary, TierPoints, Quote } from './types';
export { getPoints } from './points';
export { getQuotes } from './quotes';

const dictionaries: Record<Locale, Dictionary> = { en, he };

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}
