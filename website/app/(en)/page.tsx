import type { Metadata } from 'next';
import HomePage from '@/components/HomePage';
import { SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'SEMA - AI Business Advisor',
  description:
    'SEMA connects to your data and answers questions in plain language, with live charts, dashboards, and insights that find you first.',
  alternates: {
    canonical: `${SITE_URL}/`,
    languages: { en: `${SITE_URL}/`, he: `${SITE_URL}/he/` },
  },
};

export default function Page() {
  return <HomePage locale="en" />;
}
