'use client';

import type { ReactNode } from 'react';
import { useInView } from '@/lib/hooks/useInView';
import { useReducedMotion } from '@/lib/hooks/useReducedMotion';

interface RevealProps {
  children: ReactNode;
  /** Stagger index; multiplied internally into a millisecond delay. */
  index?: number;
  className?: string;
}

export default function Reveal({ children, index = 0, className }: RevealProps) {
  const { ref, inView } = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();
  const show = reduced || inView;

  return (
    <div
      ref={ref}
      className={`h-full ${className ?? ''}`}
      style={{
        opacity: show ? 1 : 0,
        transform: show ? 'translateY(0)' : 'translateY(18px)',
        transition: reduced ? 'none' : `opacity 550ms ease ${index * 110}ms, transform 550ms ease ${index * 110}ms`,
      }}
    >
      {children}
    </div>
  );
}
