import type { Metadata } from 'next';
import PricingPage from '@/components/PricingPage';
import { SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Pricing - SEMA',
  description: 'Simple pricing that scales with you. Start with a 14-day pilot on your own data, no credit card, no setup fee.',
  alternates: {
    canonical: `${SITE_URL}/pricing/`,
    languages: { en: `${SITE_URL}/pricing/`, he: `${SITE_URL}/he/pricing/` },
  },
};

export default function Page() {
  return <PricingPage locale="en" />;
}
