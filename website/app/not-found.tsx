import Link from 'next/link';

// Static export note: this one file (`out/404.html`) is served for ANY unmatched
// path under ANY locale prefix -- there's no per-request routing on a static host
// to pick a Hebrew variant, so it's deliberately locale-neutral English (the
// least-bad single fallback). A real localized /he/* 404 would need a routing
// change (a catch-all route inside the (he) group); flagged in
// docs/website_qa_report.md rather than guessed at here.
//
// Inline styles only, deliberately: this route isn't inside either locale's
// route-group layout (there's no root app/layout.tsx by design -- see those
// layouts' comments), so Next's static export doesn't link the app's compiled
// Tailwind stylesheet on this one page. Tailwind classes here would silently
// no-op, rendering unstyled serif text with the elements running together, so
// everything below is a self-contained inline style rather than a className.
export default function NotFound() {
  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 18,
        padding: '24px',
        textAlign: 'center',
        fontFamily:
          'Manrope, Heebo, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        background: 'linear-gradient(180deg,#F7F8FF 0%,#FFFFFF 60%)',
        color: '#15161C',
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/sema-mark-brand.svg" alt="SEMA" style={{ height: 32, width: 'auto' }} />
      <span
        style={{
          borderRadius: 999,
          background: '#EEEFFE',
          padding: '8px 14px',
          fontSize: 13,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '.14em',
          color: '#4E56D6',
        }}
      >
        404
      </span>
      <h1 style={{ margin: 0, fontSize: 36, fontWeight: 800, lineHeight: 1.15, letterSpacing: '-.02em' }}>
        Page not found
      </h1>
      <p style={{ margin: 0, maxWidth: 420, fontSize: 16, lineHeight: 1.65, color: '#5C6070' }}>
        The page you&rsquo;re looking for doesn&rsquo;t exist or may have moved.
      </p>
      <Link
        href="/"
        style={{
          borderRadius: 12,
          background: '#6C74F0',
          padding: '16px 28px',
          fontSize: 16,
          fontWeight: 700,
          color: '#FFFFFF',
          textDecoration: 'none',
        }}
      >
        Back to home
      </Link>
    </div>
  );
}
