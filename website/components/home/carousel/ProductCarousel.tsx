'use client';

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import BrowserFrame from './BrowserFrame';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';
import type { Slide } from './slides';
import type { Locale } from '@/lib/i18n';

const AUTOPLAY_MS = 5000;

function ChevronIcon({ dir }: { dir: 'prev' | 'next' }) {
  // Points visually left for "prev" / right for "next"; flipped again for RTL below.
  const points = dir === 'prev' ? '15,4 7,12 15,20' : '9,4 17,12 9,20';
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polyline points={points} stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

export default function ProductCarousel({ slides, locale }: { slides: Slide[]; locale: Locale }) {
  const reduced = useReducedMotion();
  const isRtl = locale === 'he';
  const trackRef = useRef<HTMLDivElement>(null);
  const slideRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const dragState = useRef<{ startX: number; startScrollLeft: number } | null>(null);

  // Nearest-to-center tracking via offsetLeft (untransformed layout position), not
  // getBoundingClientRect -- the peeking slides carry a CSS scale() transform, which
  // getBoundingClientRect reflects but offsetLeft does not, so it stayed accurate as
  // slides scaled in and out. Comparing against scrollLeft + clientWidth/2 keeps both
  // sides of the comparison in the track's own content coordinate space.
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    let raf = 0;
    function computeActive() {
      raf = 0;
      if (!track) return;
      const centerPoint = track.scrollLeft + track.clientWidth / 2;
      let closest = 0;
      let closestDist = Infinity;
      slideRefs.current.forEach((el, i) => {
        if (!el) return;
        const elCenter = el.offsetLeft + el.offsetWidth / 2;
        const dist = Math.abs(elCenter - centerPoint);
        if (dist < closestDist) {
          closestDist = dist;
          closest = i;
        }
      });
      setActive(closest);
    }
    function onScroll() {
      if (raf) return;
      raf = requestAnimationFrame(computeActive);
    }
    track.addEventListener('scroll', onScroll, { passive: true });
    // Deferred to a rAF, not called synchronously: at mount time the browser hasn't
    // necessarily finished layout for the just-rendered slides yet, which was
    // producing a wrong initial "active" index that then never got a `scroll`
    // event to correct it.
    const initialFrame = requestAnimationFrame(computeActive);
    return () => {
      track.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(initialFrame);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // User-initiated navigation (click/keyboard) -- scrollIntoView here is a direct response
  // to user interaction, which the no-scroll-from-timers rule (see autoAdvanceTrack below)
  // explicitly allows.
  function scrollToIndex(i: number) {
    const el = slideRefs.current[(i + slides.length) % slides.length];
    el?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', inline: 'center', block: 'nearest' });
  }

  // RULE: nothing that runs on a timer may move focus or scroll the page. This is the
  // autoplay path (called only from the setInterval below), so it must never call
  // scrollIntoView()/focus(): scrollIntoView() walks every scrollable ancestor including
  // <html>/<body>, and `block: 'nearest'` still scrolls the *page* vertically back to the
  // carousel whenever the carousel has scrolled out of view -- that was the root cause of
  // the scroll-hijack bug (this timer yanking the page back to this section every 5s while
  // the user scrolled toward #bookform). Scrolling `track` directly via scrollTo() confines
  // the effect to the carousel's own horizontal scroll container and never touches the
  // document's scroll position.
  function autoAdvanceTrack(i: number) {
    const track = trackRef.current;
    const el = slideRefs.current[(i + slides.length) % slides.length];
    if (!track || !el) return;
    const target = el.offsetLeft - (track.clientWidth - el.offsetWidth) / 2;
    track.scrollTo({ left: target, behavior: reduced ? 'auto' : 'smooth' });
  }

  // Chromium (and others) redirect a mostly-vertical wheel gesture into this track's own
  // horizontal scroll-snap when the pointer happens to be over it, which reads as the page
  // scroll "getting stuck" -- confirmed live (page advanced ~300px per wheel step elsewhere,
  // ~17px while hovering the carousel). We take over EVERY wheel event over the track and
  // route it ourselves (never falling back to the browser default for either axis) -- a
  // conditional version that only intervened for clearly-vertical deltas still let mixed/
  // diagonal ticks (common on trackpads) fall through to the browser's own redirect, which
  // was the source of an erratic "scroll jumps back up" report on real hardware this
  // environment's automated scroll testing couldn't reproduce (it doesn't dispatch real
  // `wheel` events, confirmed by instrumenting the listener). Needs a native (non-passive)
  // listener: React's onWheel is passive by default, so preventDefault() inside it is
  // silently ignored.
  //
  // `behavior: 'instant'` is required, not 'auto': globals.css sets `scroll-behavior: smooth`
  // on <html>, and per spec 'auto' means "use the element's computed scroll-behavior" -- so a
  // scrollBy with 'auto' here would animate. Rapid wheel ticks (many per physical gesture) each
  // retarget/interrupt the previous still-running animation, which was why this still felt stuck
  // (and occasionally erratic) even after adding this handler. 'instant' bypasses that entirely.
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    function onWheel(e: WheelEvent) {
      e.preventDefault();
      if (Math.abs(e.deltaY) >= Math.abs(e.deltaX)) {
        window.scrollBy({ top: e.deltaY, left: 0, behavior: 'instant' });
      } else {
        track!.scrollBy({ left: e.deltaX, top: 0, behavior: 'instant' });
      }
    }
    track.addEventListener('wheel', onWheel, { passive: false });
    return () => track.removeEventListener('wheel', onWheel);
  }, []);

  useEffect(() => {
    if (reduced || paused) return;
    // RULE: timers never scroll the page or move focus -- see autoAdvanceTrack's comment.
    const timer = window.setInterval(() => autoAdvanceTrack(active + 1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, paused, reduced]);

  function handlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    const track = trackRef.current;
    if (!track) return;
    dragState.current = { startX: e.clientX, startScrollLeft: track.scrollLeft };
    track.setPointerCapture(e.pointerId);
  }
  function handlePointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    const track = trackRef.current;
    if (!track || !dragState.current) return;
    track.scrollLeft = dragState.current.startScrollLeft - (e.clientX - dragState.current.startX);
  }
  function handlePointerUp() {
    dragState.current = null;
  }

  function handleKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      scrollToIndex(active + (isRtl ? -1 : 1));
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      scrollToIndex(active + (isRtl ? 1 : -1));
    }
  }

  return (
    <div
      className="flex flex-col gap-6"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="relative">
        <div
          ref={trackRef}
          role="region"
          aria-label="Product screenshots"
          aria-roledescription="carousel"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          className="carousel-track relative flex cursor-grab snap-x snap-mandatory gap-5 overflow-x-auto scroll-smooth px-[19%] pb-2 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand active:cursor-grabbing"
          style={{ scrollbarWidth: 'none' }}
        >
          {slides.map((slide, i) => {
            const isActive = i === active;
            return (
              <div
                key={slide.src}
                ref={(el) => {
                  slideRefs.current[i] = el;
                }}
                className="w-[62%] flex-none snap-center transition-all duration-300"
                style={{
                  opacity: isActive ? 1 : 0.6,
                  transform: isActive ? 'scale(1)' : 'scale(.92)',
                }}
                onClick={() => !isActive && scrollToIndex(i)}
              >
                <BrowserFrame src={slide.src} alt={slide.caption} />
              </div>
            );
          })}
        </div>

        <button
          type="button"
          aria-label="Previous screenshot"
          onClick={() => scrollToIndex(active - 1)}
          className="absolute start-0 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white text-text shadow-hero transition-colors hover:bg-tint-bg"
        >
          <span style={{ display: 'inline-flex', transform: isRtl ? 'scaleX(-1)' : undefined }}>
            <ChevronIcon dir="prev" />
          </span>
        </button>
        <button
          type="button"
          aria-label="Next screenshot"
          onClick={() => scrollToIndex(active + 1)}
          className="absolute end-0 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white text-text shadow-hero transition-colors hover:bg-tint-bg"
        >
          <span style={{ display: 'inline-flex', transform: isRtl ? 'scaleX(-1)' : undefined }}>
            <ChevronIcon dir="next" />
          </span>
        </button>
      </div>

      <p className="m-0 text-center text-[14.5px] font-semibold text-text">{slides[active]?.caption}</p>

      <div className="flex justify-center">
        {slides.map((slide, i) => (
          // The visible dot stays 8px (22px active) to match the design, but a
          // Lighthouse a11y pass flagged the *hit target* at that same 8x8px --
          // below the 24x24px minimum. The button itself is now a 24x24px
          // touch target with the small dot centered inside as a child span.
          <button
            key={slide.src}
            type="button"
            aria-label={`Go to screenshot ${i + 1}`}
            aria-current={i === active}
            onClick={() => scrollToIndex(i)}
            className="flex h-6 w-6 flex-none items-center justify-center"
          >
            <span
              className="block rounded-full transition-all"
              style={{
                width: i === active ? 22 : 8,
                height: 8,
                background: i === active ? '#6C74F0' : '#E7E8EF',
              }}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
