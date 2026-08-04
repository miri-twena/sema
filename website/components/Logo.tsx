interface LogoProps {
  variant?: 'brand' | 'inverse';
  markHeight?: number;
  wordmarkSize?: number;
  className?: string;
}

export default function Logo({ variant = 'brand', markHeight = 26, wordmarkSize = 16, className }: LogoProps) {
  const src = variant === 'brand' ? '/brand/sema-mark-brand.svg' : '/brand/sema-mark-inverse.svg';
  const wordmarkColor = variant === 'brand' ? '#6C74F0' : '#FFFFFF';
  return (
    <span dir="ltr" className={`inline-flex items-center gap-2 ${className ?? ''}`} style={{ unicodeBidi: 'isolate' }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="SEMA" style={{ height: markHeight, width: 'auto', display: 'block', flex: 'none' }} />
      <span
        className="font-wordmark font-extrabold"
        style={{ fontSize: wordmarkSize, letterSpacing: '.12em', color: wordmarkColor }}
      >
        SEMA
      </span>
    </span>
  );
}
