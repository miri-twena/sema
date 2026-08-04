'use client';

import { useEffect } from 'react';

/** Corrects the browser's native anchor jump for the sticky 68px header + 10px breathing room. */
export default function HashScrollOnMount() {
  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (!hash) return;
    const el = document.getElementById(hash);
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY - 78;
    window.scrollTo({ top, behavior: 'smooth' });
  }, []);
  return null;
}
