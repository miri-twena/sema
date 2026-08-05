'use client';

import { useEffect, useState } from 'react';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';
import type { Dictionary } from '@/lib/i18n';

const CYCLE_MS = 6000;
const VISIBLE_MS = 4000;

export default function AlertToast({ t }: { t: Dictionary }) {
  const reduced = useReducedMotion();
  const [visible, setVisible] = useState(false);

  // RULE: nothing that runs on a timer may move focus or scroll the page -- these timers
  // only toggle `visible`, which is purely an opacity/transform transition; never add
  // focus()/scrollIntoView() here.
  useEffect(() => {
    if (reduced) return;
    const showTimer = setInterval(() => setVisible(true), CYCLE_MS);
    return () => clearInterval(showTimer);
  }, [reduced]);

  useEffect(() => {
    if (!visible) return;
    const hideTimer = setTimeout(() => setVisible(false), VISIBLE_MS);
    return () => clearTimeout(hideTimer);
  }, [visible]);

  if (reduced) return null;

  return (
    <div
      className="pointer-events-none absolute -top-4 end-3 z-10 flex max-w-[240px] flex-col gap-0.5 rounded-xl border border-border-soft bg-white px-3.5 py-3 shadow-hero transition-all duration-300"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(-10px)',
      }}
      aria-hidden="true"
    >
      {/* #C05A4E was 4.36:1 here, just under WCAG AA's 4.5:1 for this bold 12.5px text. */}
      <span className="text-[12.5px] font-bold text-[#B44C40]">{t.toastTitle}</span>
      <span className="text-[11px] text-text-faint">{t.toastCaption}</span>
    </div>
  );
}
