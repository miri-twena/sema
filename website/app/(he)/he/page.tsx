import type { Metadata } from 'next';
import HomePage from '@/components/HomePage';
import { SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'SEMA - יועץ עסקי מבוסס AI',
  description: 'SEMA מתחבר לנתונים שלכם ועונה על שאלות בשפה חופשית, עם גרפים חיים, דשבורדים ותובנות שמגיעות אליכם לפני שהספקתם לשאול.',
  alternates: {
    canonical: `${SITE_URL}/he/`,
    languages: { en: `${SITE_URL}/`, he: `${SITE_URL}/he/` },
  },
};

export default function Page() {
  return <HomePage locale="he" />;
}
