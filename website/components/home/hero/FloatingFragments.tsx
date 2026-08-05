/** Two low-opacity subsets of the brand mark's polygon geometry, floating slowly behind the hero. Purely decorative. */
export default function FloatingFragments() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <svg
        viewBox="0 0 219 185"
        width="150"
        height="127"
        className="absolute -left-6 top-8 opacity-[.08]"
        style={{ animation: 'float-slow-a 8s ease-in-out infinite' }}
      >
        <polygon points="67.0,4.0 104.0,7.0 72.0,35.0" fill="#6C74F0" />
        <polygon points="120.0,4.0 157.0,7.0 143.0,37.0 119.0,7.0" fill="#F2C94C" />
        <polygon points="80.0,37.0 112.0,6.0 137.0,42.0 80.0,41.0" fill="#F2887C" />
        <polygon points="64.0,12.0 66.0,43.0 14.0,57.0" fill="#6C74F0" />
      </svg>
      <svg
        viewBox="0 0 219 185"
        width="120"
        height="101"
        className="absolute -right-8 bottom-4 opacity-[.07]"
        style={{ animation: 'float-slow-b 9s ease-in-out infinite' }}
      >
        <polygon points="26.0,106.0 69.0,49.0 75.0,54.0 98.0,110.0 26.0,110.0" fill="#4E56D6" />
        <polygon points="145.0,49.0 184.0,110.0 109.0,109.0" fill="#F2887C" />
        <polygon points="153.0,49.0 215.0,67.0 192.0,107.0 187.0,105.0 152.0,52.0" fill="#F2C94C" />
      </svg>
    </div>
  );
}
