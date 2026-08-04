import type { Locale, Quote } from './types';

const base = [
  { init: 'DK', tint: '#EEEFFE', color: '#4E56D6' },
  { init: 'YM', tint: '#E4F6EC', color: '#2F8F63' },
  { init: 'NA', tint: '#FDEBE8', color: '#C05A4E' },
];

const en = [
  {
    name: 'Dana Klein',
    role: 'CFO, Northwind',
    text: 'Board prep went from three days to one question. SEMA is the first tool our finance team actually opens every morning.',
  },
  {
    name: 'Yoav Mizrahi',
    role: 'COO, Borealis',
    text: 'The proactive alerts caught a margin drop two weeks before our monthly review would have. That alone paid for the year.',
  },
  {
    name: 'Noa Adler',
    role: 'VP Data, Lumina',
    text: 'Our analysts stopped being a report factory. Business users ask SEMA directly, and the team finally does real analysis.',
  },
];

const he = [
  {
    name: 'דנה קליין',
    role: 'סמנכ״לית כספים, Northwind',
    text: 'ההכנה לדירקטוריון ירדה משלושה ימים לשאלה אחת. SEMA הוא הכלי הראשון שצוות הכספים באמת פותח כל בוקר.',
  },
  {
    name: 'יואב מזרחי',
    role: 'סמנכ״ל תפעול, Borealis',
    text: 'ההתראות היזומות תפסו ירידה בשוליים שבועיים לפני שהסקירה החודשית הייתה מגלה אותה. זה לבד החזיר את ההשקעה.',
  },
  {
    name: 'נועה אדלר',
    role: 'VP Data, Lumina',
    text: 'האנליסטים שלנו הפסיקו להיות מפעל דוחות. אנשי העסקים שואלים את SEMA ישירות, והצוות סוף סוף עושה אנליזה אמיתית.',
  },
];

export function getQuotes(locale: Locale): Quote[] {
  const list = locale === 'he' ? he : en;
  return list.map((q, i) => ({ ...q, ...base[i] }));
}
