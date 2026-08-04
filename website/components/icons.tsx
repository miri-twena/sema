export function ChatFacetIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="3,5.5 12,3 12,10.5" fill="#949CFF" />
      <polygon points="12,3 21,5.5 12,10.5" fill="#6C74F0" />
      <polygon points="3,5.5 12,10.5 4.5,15.5" fill="#6C74F0" />
      <polygon points="12,10.5 21,5.5 19.5,15.5" fill="#4E56D6" />
      <polygon points="4.5,15.5 12,10.5 19.5,15.5" fill="#949CFF" />
      <polygon points="6.2,16.6 10.8,16.6 6.8,21.5" fill="#4E56D6" />
    </svg>
  );
}

export function BarChartFacetIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="4,13 8,11 8,20" fill="#7DD4A8" />
      <polygon points="4,13 8,20 4,20" fill="#2F8F63" />
      <polygon points="10,5 14,7 14,20" fill="#949CFF" />
      <polygon points="10,5 14,20 10,20" fill="#6C74F0" />
      <polygon points="16,10 20,8 20,20" fill="#7DD4A8" />
      <polygon points="16,10 20,20 16,20" fill="#2F8F63" />
    </svg>
  );
}

export function SparkFacetIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="12,2 14.2,9.8 12,12" fill="#F2C94C" />
      <polygon points="12,2 12,12 9.8,9.8" fill="#F2887C" />
      <polygon points="22,12 14.2,14.2 12,12" fill="#F2887C" />
      <polygon points="22,12 12,12 14.2,9.8" fill="#F2C94C" />
      <polygon points="12,22 9.8,14.2 12,12" fill="#F2C94C" />
      <polygon points="12,22 12,12 14.2,14.2" fill="#F2887C" />
      <polygon points="2,12 9.8,9.8 12,12" fill="#F2887C" />
      <polygon points="2,12 12,12 9.8,14.2" fill="#F2C94C" />
    </svg>
  );
}

export function DiamondBulletIcon({ tone = 'default' }: { tone?: 'default' | 'dark' }) {
  const [top, bottom] = tone === 'dark' ? ['#C7CDFF', '#949CFF'] : ['#949CFF', '#6C74F0'];
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-none" aria-hidden="true">
      <polygon points="6,0 12,6 6,12" fill={top} />
      <polygon points="6,0 6,12 0,6" fill={bottom} />
    </svg>
  );
}
