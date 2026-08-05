'use client';

import { useEffect, useState, type CSSProperties } from 'react';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';
import { getHeroScenes } from './scenes';
import AlertToast from './AlertToast';
import type { Dictionary } from '@/lib/i18n';

const TYPE_MS_PER_CHAR = 45;
const POST_TYPE_PAUSE_MS = 300;
const IDLE_HOLD_MS = 8000;

function Sparkline({ bars }: { bars: { height: number }[] }) {
  const heights = bars.map((b) => b.height);
  const min = Math.min(...heights);
  const max = Math.max(...heights);
  const points = bars
    .map((b, i) => {
      const x = (i / (bars.length - 1)) * 100;
      const y = 26 - ((b.height - min) / (max - min || 1)) * 22 - 2;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg viewBox="0 0 100 28" preserveAspectRatio="none" className="h-7 w-full" aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke="#F2887C"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={
          {
            strokeDasharray: 220,
            animation: 'draw-line 700ms ease 950ms both',
            '--dash-length': 220,
          } as CSSProperties
        }
      />
    </svg>
  );
}

export default function HeroDemoCard({ t }: { t: Dictionary }) {
  const reduced = useReducedMotion();
  const scenes = getHeroScenes(t);
  const [cycle, setCycle] = useState(0);
  const [typed, setTyped] = useState('');
  const [phase, setPhase] = useState<'typing' | 'answered'>('typing');
  const scene = scenes[cycle % scenes.length];

  // RULE: nothing that runs on a timer may move focus or scroll the page -- these timers
  // (typing effect, post-type pause, idle hold before the next scene) only set component
  // state that renders as text/opacity changes; never add focus()/scrollIntoView() here.
  useEffect(() => {
    if (reduced) {
      setTyped(scene.question);
      setPhase('answered');
      return;
    }
    setPhase('typing');
    setTyped('');
    let i = 0;
    const typeTimer = setInterval(() => {
      i += 1;
      setTyped(scene.question.slice(0, i));
      if (i >= scene.question.length) {
        clearInterval(typeTimer);
        window.setTimeout(() => setPhase('answered'), POST_TYPE_PAUSE_MS);
      }
    }, TYPE_MS_PER_CHAR);
    return () => clearInterval(typeTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cycle, reduced]);

  useEffect(() => {
    if (reduced || phase !== 'answered') return;
    const idleTimer = window.setTimeout(() => setCycle((c) => c + 1), IDLE_HOLD_MS);
    return () => window.clearTimeout(idleTimer);
  }, [phase, reduced]);

  return (
    <div className="relative">
      <AlertToast t={t} />
      <div className="overflow-hidden rounded-card-lg border border-border bg-white shadow-hero">
      <div className="flex items-center gap-2.5 border-b border-border-faint px-6 py-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/sema-mark-brand.svg" alt="" style={{ height: 21, width: 'auto' }} />
        <span className="text-[13px] font-bold uppercase tracking-[.08em] text-text-faint">{t.demoLabel}</span>
      </div>
      <div className="flex flex-col gap-4 p-6">
        <div
          className="self-end rounded-ss-[16px] rounded-se-[16px] rounded-ee-[5px] rounded-es-[16px] bg-brand-50 px-4 py-3 text-[15px] font-semibold text-[#3A41A8]"
          style={{ maxWidth: '82%', minHeight: '1.7em' }}
        >
          {typed}
          {phase === 'typing' && !reduced && (
            <span
              className="ms-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] bg-[#3A41A8] align-middle"
              style={{ animation: 'caret-blink 1s step-end infinite' }}
            />
          )}
        </div>

        {
          /*
           * This block used to be conditionally mounted only while phase === 'answered',
           * unmounting entirely (height 0) during the ~2s 'typing' phase. That made this
           * whole card cycle between two very different heights every ~10s -- and since
           * this is a two-column grid with items-center, the *row* (and the whole Hero
           * section) grew/shrank right along with it. Once the user scrolled further down
           * the page, that height change (via the browser's scroll anchoring) moved the
           * page under them: the same "cycling content isn't height-stable" failure mode
           * as the how-it-works panel and the proactive feed, just one level up in this
           * component. Fix: always mount this box and use `visibility: hidden` (which
           * still reserves its layout box) while typing, instead of unmounting it. The key
           * still switches only when a fresh "answered" phase begins, so the fade-up
           * entrance animation keeps firing at the same moment it always did.
           */
        }
        <div
          key={phase === 'answered' ? `answered-${cycle}` : 'pending'}
          className="flex flex-col gap-3.5 rounded-2xl border border-border-faint px-5 py-4"
          style={{
            visibility: phase === 'answered' ? 'visible' : 'hidden',
            animation: reduced || phase !== 'answered' ? 'none' : 'fade-up 400ms ease both',
          }}
        >
            <div className="text-[15px] font-bold text-text">{scene.title}</div>
            <div dir="ltr" className="flex h-[140px] items-end gap-4 px-1">
              {scene.bars.map((bar, i) => {
                const isLast = i === scene.bars.length - 1;
                return (
                  <div key={bar.month} className="flex flex-1 flex-col items-center gap-1.5">
                    <span className={`text-xs font-bold ${isLast ? 'text-brand-deep' : 'text-text-muted'}`}>
                      {bar.value}
                    </span>
                    <div
                      className={`w-full rounded-t-md ${isLast ? 'bg-brand-deep' : 'bg-brand'}`}
                      style={{
                        height: bar.height,
                        animation: reduced ? 'none' : `grow-bar 550ms cubic-bezier(.22,.9,.32,1) ${i * 80}ms both`,
                      }}
                    />
                    <span className="text-[11px] text-text-faint">{bar.month}</span>
                  </div>
                );
              })}
            </div>
            <div dir="ltr">
              <Sparkline bars={scene.bars} />
            </div>
            <div dir="ltr" className="flex gap-3">
              {scene.kpis.map((kpi) => (
                <div key={kpi.label} className="flex-1 overflow-hidden rounded-xl border border-border-soft">
                  <div className="h-1" style={{ background: kpi.topColor }} />
                  <div className="px-3.5 py-3">
                    <div className="text-[11px] text-text-faint">{kpi.label}</div>
                    <div className="text-lg font-extrabold text-text">
                      {/* #2F8F63 was 3.9:1 on white for this bold xs text; #297C56 clears 4.5:1. */}
                      {kpi.value} <span className="text-xs font-bold text-[#297C56]">{kpi.delta}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
        </div>
      </div>
      </div>
    </div>
  );
}
