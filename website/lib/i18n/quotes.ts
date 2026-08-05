import type { Locale, Quote } from './types';

// YM/NA colors darkened from #2F8F63/#C05A4E: both failed WCAG AA (3.6:1, 3.8:1)
// as 13px bold initials on their tint background; #297C56/#B44C40 clear 4.5:1.
const base = [
  { init: 'DK', tint: '#EEEFFE', color: '#4E56D6' },
  { init: 'YM', tint: '#E4F6EC', color: '#297C56' },
  { init: 'NA', tint: '#FDEBE8', color: '#B44C40' },
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
