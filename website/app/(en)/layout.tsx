import type { Metadata } from 'next';
import '../globals.css';
import { SITE_URL } from '@/lib/site';

// TODO: replace with a real 1200x630 marketing image once one is designed.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  icons: { icon: '/brand/sema-favicon.svg' },
  openGraph: { images: ['/og.png'] },
};

export default function EnRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <body className="font-sans">{children}</body>
    </html>
  );
}
