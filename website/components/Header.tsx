'use client';

import Logo from './Logo';
import { getDictionary, type Locale } from '@/lib/i18n';
import { homeHref, pricingHref } from '@/lib/urls';

function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (el) {
    const top = el.getBoundingClientRect().top + window.scrollY - 78;
    window.scrollTo({ top, behavior: 'smooth' });
  }
}

interface HeaderProps {
  locale: Locale;
  page: 'home' | 'pricing';
}

export default function Header({ locale, page }: HeaderProps) {
  const t = getDictionary(locale);
  const home = homeHref(locale);
  const pricing = pricingHref(locale);
  const enHref = page === 'pricing' ? pricingHref('en') : homeHref('en');
  const heHref = page === 'pricing' ? pricingHref('he') : homeHref('he');

  const navItems: { id: string; label: string }[] = [
    { id: 'features', label: t.navProduct },
    { id: 'how', label: t.navHow },
    { id: 'quotes', label: t.navCustomers },
  ];

  function navHandler(id: string) {
    return (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (id === 'bookform' || page === 'home') {
        e.preventDefault();
        scrollToId(id);
      }
    };
  }

  return (
    <header
      data-screen-label="Header"
      className="sticky top-0 z-50 border-b border-[#EFF0F5]"
      style={{ background: 'rgba(255,255,255,.92)', backdropFilter: 'blur(10px)' }}
    >
      <div className="mx-auto flex h-[68px] max-w-container items-center gap-7 px-6">
        <a href={home} className="flex flex-none items-center">
          <Logo />
        </a>
        <nav className="hidden items-center gap-[22px] text-sm font-semibold text-text-muted md:flex">
          {navItems.map((item) => (
            <a
              key={item.id}
              href={page === 'home' ? `#${item.id}` : `${home}#${item.id}`}
              onClick={navHandler(item.id)}
              className="cursor-pointer transition-colors duration-150 hover:text-text"
            >
              {item.label}
            </a>
          ))}
          <a href={pricing} className="cursor-pointer transition-colors duration-150 hover:text-text">
            {t.navPricing}
          </a>
        </nav>
        <div className="ms-auto flex items-center gap-3.5">
          <div dir="ltr" className="flex gap-0.5 rounded-full border border-border p-[3px]">
            <a
              href={enHref}
              className={`rounded-full px-3 py-[5px] text-xs font-bold no-underline ${
                locale === 'en' ? 'bg-brand-50 text-brand-deep' : 'text-text-faint'
              }`}
            >
              EN
            </a>
            <a
              href={heHref}
              className={`rounded-full px-3 py-[5px] text-xs font-bold no-underline ${
                locale === 'he' ? 'bg-brand-50 text-brand-deep' : 'text-text-faint'
              }`}
            >
              עב
            </a>
          </div>
          <a
            href={`#bookform`}
            onClick={navHandler('bookform')}
            className="rounded-[10px] bg-brand px-[18px] py-2.5 text-sm font-bold text-white no-underline transition-colors duration-150 hover:bg-brand-hover"
          >
            {t.cta}
          </a>
        </div>
      </div>
    </header>
  );
}
