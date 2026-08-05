'use client';

import { useEffect, useState, type CSSProperties } from 'react';
import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

const CYCLE_MS = 7000;
const STAGGER_STEP_MS = 140;

export interface FeedAlert {
  bar: string;
  tagBg: string;
  tagFg: string;
  tag: string;
  time: string;
  text: string;
}

// Cycling swaps which alert (different text length) lands in a given slot, so the alert
// text must reserve a constant 2-line box regardless of how many lines it actually needs --
// otherwise a short alert followed by a long one changes this card's height, which (since
// this section sits above the fold once the user has scrolled further down the page) shows
// up as the page itself shifting under the user every cycle. 3em == 2 lines at the
// text's own 1.5 line-height, so this is stable across locales/copy changes, not tuned to
// today's specific alert strings.
const TEXT_CLAMP_STYLE: CSSProperties = {
  minHeight: '3em',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

function CardBody({ alert }: { alert: FeedAlert }) {
  return (
    <>
      <div className="h-[3px]" style={{ background: alert.bar }} />
      <div className="flex flex-col gap-1.5 px-[15px] py-3">
        <div className="flex items-center gap-2">
          <span
            className="rounded-full px-2 py-0.5 text-[10.5px] font-bold"
            style={{ background: alert.tagBg, color: alert.tagFg }}
          >
            {alert.tag}
          </span>
          <span className="ms-auto text-[11px] text-text-faint">{alert.time}</span>
        </div>
        <span className="text-[13.5px] font-semibold leading-[1.5] text-text" style={TEXT_CLAMP_STYLE}>
          {alert.text}
        </span>
      </div>
    </>
  );
}

function AlertCard({ alert, slot }: { alert: FeedAlert; slot: number }) {
  const reduced = useReducedMotion();
  return (
    <div
      key={alert.tag}
      className="overflow-hidden rounded-xl border border-border-soft bg-white"
      style={{ animation: reduced ? 'none' : `${slot === 0 ? 'feed-slide-in-top' : 'feed-fade-in'} 450ms ease both` }}
    >
      <CardBody alert={alert} />
    </div>
  );
}

export default function ProactiveFeed({ alerts }: { alerts: FeedAlert[] }) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const [tick, setTick] = useState(0);
  const [hovered, setHovered] = useState(false);
  const show = reduced || inView;

  // tick can only advance once `inView` has fired at least once, since the interval
  // below requires it — inView is sticky-true (useInView never un-triggers), so by
  // the time tick > 0 the initial reveal has already necessarily played.
  // RULE: nothing that runs on a timer may move focus or scroll the page -- this interval
  // only bumps `tick`, which swaps card content/plays an entrance animation. The card list
  // is height-stable (always exactly 3 slots of the same card markup/height), so cycling
  // never causes a layout shift that could move the page under the user; never add
  // focus()/scrollIntoView() here.
  useEffect(() => {
    if (reduced || !inView || hovered) return;
    const timer = window.setInterval(() => setTick((c) => c + 1), CYCLE_MS);
    return () => window.clearInterval(timer);
  }, [inView, hovered, reduced]);

  const slots = [0, 1, 2].map((slot) => alerts[(tick + slot) % alerts.length]);

  return (
    <div
      ref={ref}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="flex flex-col gap-[11px]"
    >
      {slots.map((alert, slot) =>
        tick === 0 ? (
          <div
            key={alert.tag}
            className={`reveal-end ${show ? 'is-visible' : ''}`}
            style={{ transitionDelay: reduced ? '0ms' : `${slot * STAGGER_STEP_MS}ms` }}
          >
            <AlertCardStatic alert={alert} />
          </div>
        ) : (
          <AlertCard key={`${alert.tag}-${tick}`} alert={alert} slot={slot} />
        ),
      )}
    </div>
  );
}

function AlertCardStatic({ alert }: { alert: FeedAlert }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border-soft bg-white">
      <CardBody alert={alert} />
    </div>
  );
}
