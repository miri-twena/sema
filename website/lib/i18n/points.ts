import type { Locale, TierPoints } from './types';

export function getPoints(locale: Locale): TierPoints {
  if (locale === 'he') {
    return {
      t1: ['עד 5 משתמשים', '2 מקורות נתונים', 'שאלות ללא הגבלה', 'תמיכה סטנדרטית'],
      t2: ['עד 25 משתמשים', '10 מקורות נתונים', 'דשבורדים חיים', 'תובנות יזומות', 'תמיכה בעדיפות'],
      t3: ['משתמשים ומקורות ללא הגבלה', 'SSO ויומן ביקורת', 'יועץ ייעודי', 'SLA מותאם'],
    };
  }
  return {
    t1: ['Up to 5 seats', '2 data sources', 'Unlimited questions', 'Standard support'],
    t2: ['Up to 25 seats', '10 data sources', 'Live dashboards', 'Proactive insights', 'Priority support'],
    t3: ['Unlimited seats & sources', 'SSO & audit log', 'Dedicated advisor', 'Custom SLA'],
  };
}
