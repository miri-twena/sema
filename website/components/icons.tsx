export function DiamondBulletIcon({ tone = 'default' }: { tone?: 'default' | 'dark' }) {
  const [top, bottom] = tone === 'dark' ? ['#C7CDFF', '#949CFF'] : ['#949CFF', '#6C74F0'];
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-none" aria-hidden="true">
      <polygon points="6,0 12,6 6,12" fill={top} />
      <polygon points="6,0 6,12 0,6" fill={bottom} />
    </svg>
  );
}
