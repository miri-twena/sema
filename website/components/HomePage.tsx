import Header from './Header';
import Footer from './Footer';
import SkipLink from './SkipLink';
import BookDemoSection from './BookDemoSection';
import HashScrollOnMount from './HashScrollOnMount';
import Hero from './home/Hero';
import Features from './home/Features';
import SemanticModel from './home/SemanticModel';
import ProductShowcase from './home/ProductShowcase';
import Proactive from './home/Proactive';
import HowItWorks from './home/HowItWorks';
import Testimonials from './home/Testimonials';
import type { Locale } from '@/lib/i18n';

export default function HomePage({ locale }: { locale: Locale }) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <HashScrollOnMount />
      <SkipLink locale={locale} />
      <Header locale={locale} page="home" />
      <main id="main-content">
        <Hero locale={locale} />
        <Features locale={locale} />
        <SemanticModel locale={locale} />
        <ProductShowcase locale={locale} />
        <Proactive locale={locale} />
        <HowItWorks locale={locale} />
        <Testimonials locale={locale} />
        <BookDemoSection locale={locale} />
      </main>
      <Footer locale={locale} />
    </div>
  );
}
