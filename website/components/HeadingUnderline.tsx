'use client';

import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

/** A short brand-color stroke that draws itself under a heading once it scrolls into view. */
export default function HeadingUnderline({ color = '#6C74F0' }: { color?: string }) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const show = reduced || inView;

  return (
    <div
      ref={ref}
      style={{
        height: 3,
        width: show ? 56 : 0,
        background: color,
        borderRadius: 999,
        transition: reduced ? 'none' : 'width 500ms ease 200ms',
      }}
    />
  );
}
