'use client';

import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';
import { AskBarIcon, DashboardWidgetsIcon, InsightRowsIcon } from '../icons';
import type { Locale } from '@/lib/i18n';

const AUTO_ADVANCE_MS = 5000;

interface Step {
  title: string;
  body: string;
}

function ConnectDataPanel(_props: { locale: Locale }) {
  return (
    <div className="flex items-center justify-center gap-4 py-6" dir="ltr">
      {[AskBarIcon, DashboardWidgetsIcon, InsightRowsIcon].map((Icon, i) => (
        <div key={i} className="flex h-14 w-14 items-center justify-center">
          <Icon />
        </div>
      ))}
      <svg width="40" height="2" viewBox="0 0 40 2" aria-hidden="true">
        <line x1="0" y1="1" x2="40" y2="1" stroke="#C7CDFF" strokeWidth="2" strokeDasharray="4 4" />
      </svg>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand text-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/sema-mark-inverse.svg" alt="" style={{ height: 22, width: 'auto' }} />
      </div>
    </div>
  );
}

function AskAnythingPanel({ locale }: { locale: Locale }) {
  const question = locale === 'he' ? 'איזה אזור מוביל אצלנו במכירות?' : "What's our best-performing region?";
  return (
    <div className="flex flex-col gap-2.5 py-6">
      <div
        className="self-end rounded-ss-2xl rounded-se-2xl rounded-ee-md rounded-es-2xl bg-brand-50 px-3.5 py-2 text-[13px] font-semibold text-[#3A41A8]"
        style={{ maxWidth: '75%' }}
      >
        {question}
      </div>
      <div dir="ltr" className="flex items-end gap-1.5 self-start rounded-2xl border border-border-soft px-3.5 py-2.5">
        {[14, 22, 18, 28].map((h, i) => (
          <div key={i} className="w-2.5 rounded-t bg-brand" style={{ height: h }} />
        ))}
      </div>
    </div>
  );
}

function ActOnInsightsPanel({ locale }: { locale: Locale }) {
  const alerts =
    locale === 'he'
      ? [
          { bar: '#F2887C', tagBg: '#FDEBE8', tagFg: '#C05A4E', tag: 'חריגה', text: 'שיעור הזיכויים קפץ ב-3.1%', time: 'לפני 8 דק׳' },
          { bar: '#F2C94C', tagBg: '#FBF3D9', tagFg: '#B48A0A', tag: 'הזדמנות', text: 'המלאי מספיק ל-12 יום בלבד', time: 'אתמול' },
        ]
      : [
          { bar: '#F2887C', tagBg: '#FDEBE8', tagFg: '#C05A4E', tag: 'Anomaly', text: 'Refund rate spiked 3.1%', time: '8m ago' },
          { bar: '#F2C94C', tagBg: '#FBF3D9', tagFg: '#B48A0A', tag: 'Opportunity', text: 'Inventory covers 12 days', time: 'Yesterday' },
        ];
  return (
    <div className="flex w-full max-w-md flex-col gap-3">
      {alerts.map((a) => (
        <div key={a.tag} className="overflow-hidden rounded-xl border border-border-soft bg-white">
          <div className="h-[3px]" style={{ background: a.bar }} />
          <div className="flex flex-col gap-1.5 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="rounded-full px-2 py-0.5 text-[10.5px] font-bold" style={{ background: a.tagBg, color: a.tagFg }}>
                {a.tag}
              </span>
              <span className="ms-auto text-[11px] text-text-faint">{a.time}</span>
            </div>
            <span className="text-[13.5px] font-semibold leading-[1.5] text-text">{a.text}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

const PANELS = [ConnectDataPanel, AskAnythingPanel, ActOnInsightsPanel];

export default function HowItWorksStepper({ steps, locale }: { steps: Step[]; locale: Locale }) {
  const reduced = useReducedMotion();
  const isRtl = locale === 'he';
  const [active, setActive] = useState(0);
  const [maxVisited, setMaxVisited] = useState(0);
  const [interacted, setInteracted] = useState(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // RULE: nothing that runs on a timer may move focus or scroll the page -- this interval
  // only sets `active` (a style/aria-selected change); it must never call
  // element.focus()/scrollIntoView() the way `select()` below does for user interaction.
  useEffect(() => {
    if (reduced || interacted) return;
    const timer = window.setInterval(() => {
      setActive((a) => (a + 1) % steps.length);
    }, AUTO_ADVANCE_MS);
    return () => window.clearInterval(timer);
  }, [reduced, interacted, steps.length]);

  useEffect(() => {
    setMaxVisited((m) => Math.max(m, active));
  }, [active]);

  // Only ever called from click/keydown handlers below -- never from the timer -- so
  // moving focus here is allowed by the no-focus/no-scroll-from-timers rule.
  function select(index: number, focus = false) {
    setActive(index);
    setInteracted(true);
    if (focus) tabRefs.current[index]?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent, index: number) {
    let next = index;
    if (e.key === 'ArrowRight') next = isRtl ? index - 1 : index + 1;
    else if (e.key === 'ArrowLeft') next = isRtl ? index + 1 : index - 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = steps.length - 1;
    else return;
    e.preventDefault();
    next = (next + steps.length) % steps.length;
    select(next, true);
  }

  const progressPct = (maxVisited / (steps.length - 1)) * 100;

  return (
    <div className="flex flex-col gap-8">
      <div role="tablist" aria-label="How it works" className="grid grid-cols-1 gap-[22px] md:grid-cols-3">
        {steps.map((step, i) => {
          const isActive = i === active;
          return (
            <button
              key={step.title}
              ref={(el) => {
                tabRefs.current[i] = el;
              }}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls={`how-panel-${i}`}
              id={`how-tab-${i}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => select(i)}
              onKeyDown={(e) => handleKeyDown(e, i)}
              className="flex flex-col gap-3 rounded-card border bg-white px-6 py-[26px] text-start transition-all duration-200"
              // borderWidth is intentionally constant (never 1 vs 2) -- this button re-renders
              // on the auto-advance timer above, and a border-width change is a layout change
              // (it resizes the box), which caused the browser's scroll anchoring to shift the
              // whole page while this section sat above the viewport (part of the scroll-hijack
              // bug). The extra "active" weight is faked with an inset box-shadow instead, which
              // is paint-only and never affects layout.
              style={{
                borderColor: isActive ? '#6C74F0' : '#EDEEF4',
                borderWidth: 1,
                transform: isActive ? 'translateY(-3px)' : 'translateY(0)',
                boxShadow: isActive
                  ? 'inset 0 0 0 1px #6C74F0, 0 12px 28px rgba(78,86,214,.14)'
                  : 'none',
              }}
            >
              <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-brand text-[15px] font-extrabold text-white">
                {i + 1}
              </span>
              <h3 className="m-0 text-lg font-bold">{step.title}</h3>
              <p className="m-0 text-[14.5px] leading-[1.65] text-text-muted">{step.body}</p>
            </button>
          );
        })}
      </div>

      <div dir="ltr" className="h-1 w-full overflow-hidden rounded-full bg-border-soft">
        <div
          className="h-full bg-brand"
          style={{ width: `${progressPct}%`, transition: reduced ? 'none' : 'width 400ms ease' }}
        />
      </div>

      {steps.map((step, i) => {
        const PanelComponent = PANELS[i];
        const isActive = i === active;
        return (
          <div
            key={step.title}
            id={`how-panel-${i}`}
            role="tabpanel"
            aria-labelledby={`how-tab-${i}`}
            hidden={!isActive}
            // Fixed height (not min-height): the three mockup panels have different
            // natural content heights (measured ~220/245/244px), and this panel swaps
            // between them on the auto-advance timer above. A height that varies by
            // which panel is showing is exactly the "cycling content isn't height-stable"
            // case the no-scroll-from-timers rule calls out -- it moved the page via the
            // browser's scroll anchoring once this section scrolled above the viewport.
            // overflow-hidden is a safety net if future copy pushes a panel past 248px.
            className={
              isActive
                ? 'flex h-[248px] w-full items-center justify-center overflow-hidden rounded-card border border-border-soft bg-tint-bg px-8 py-10'
                : 'hidden'
            }
          >
            {isActive && <PanelComponent locale={locale} />}
          </div>
        );
      })}
    </div>
  );
}
