import type { Metadata } from 'next';
import PricingPage from '@/components/PricingPage';
import { SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'תמחור - SEMA',
  description: 'תמחור פשוט שגדל איתכם. מתחילים בפיילוט של 14 יום על הנתונים שלכם, בלי כרטיס אשראי ובלי דמי הקמה.',
  alternates: {
    canonical: `${SITE_URL}/he/pricing/`,
    languages: { en: `${SITE_URL}/pricing/`, he: `${SITE_URL}/he/pricing/` },
  },
};

export default function Page() {
  return <PricingPage locale="he" />;
}
