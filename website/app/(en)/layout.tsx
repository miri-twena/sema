import type { Metadata } from 'next';
import '../globals.css';
import { SITE_URL } from '@/lib/site';

// og:image intentionally omitted -- `/og.png` doesn't exist yet (no 1200x630
// marketing image has been designed), and a QA sweep found it shipping as a
// dead link that would 404 for any crawler/share preview. Add it back here
// once a real image exists (see docs/website_qa_report.md, Decisions needed).
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  icons: { icon: '/brand/sema-favicon.svg' },
};

export default function EnRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <body className="font-sans">{children}</body>
    </html>
  );
}
