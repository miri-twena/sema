'use client';

import { useEffect } from 'react';

/**
 * Corrects the browser's native anchor jump for the sticky 68px header + 10px breathing room.
 * Deliberately runs once on mount only (empty dep array) and must stay that way -- this must
 * never re-run in response to state the motion-layer timers change, or it would re-trigger a
 * scroll to the URL's hash out from under the user while they're scrolling elsewhere on the page.
 */
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
