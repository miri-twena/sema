/** Micro-UI vignettes for the Features cards -- tiny pieces of real product UI, not icons. */

export function AskVignette() {
  return (
    <svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true">
      <rect x="1" y="12" width="68" height="24" rx="12" fill="#FFFFFF" stroke="#E0E2EE" strokeWidth="1.5" />
      <rect x="12" y="21.5" width="26" height="5" rx="2.5" fill="#C7CDFF" />
      <rect x="40" y="22" width="2" height="10" fill="#6C74F0">
        <animate attributeName="opacity" values="1;0;1" dur="1.2s" repeatCount="indefinite" />
      </rect>
      <circle cx="56" cy="24" r="8" fill="#6C74F0" />
      <path d="M53 24h6m-2.5-2.5L59 24l-2.5 2.5" stroke="#FFFFFF" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function DashboardVignette() {
  return (
    <svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="30" height="40" rx="6" fill="#FFFFFF" stroke="#E0E2EE" strokeWidth="1.5" />
      <rect x="3" y="4" width="30" height="3" rx="1.5" fill="#6C74F0" />
      <rect x="9" y="14" width="12" height="4" rx="2" fill="#DADCEA" />
      <rect x="9" y="22" width="18" height="6" rx="2" fill="#3B3F4E" />
      <rect x="9" y="33" width="4" height="7" rx="1.5" fill="#C7CDFF" />
      <rect x="15" y="30" width="4" height="10" rx="1.5" fill="#949CFF" />
      <rect x="21" y="26" width="4" height="14" rx="1.5" fill="#6C74F0" />
      <rect x="37" y="4" width="30" height="40" rx="6" fill="#FFFFFF" stroke="#E0E2EE" strokeWidth="1.5" />
      <rect x="37" y="4" width="30" height="3" rx="1.5" fill="#F2C94C" />
      <rect x="43" y="14" width="12" height="4" rx="2" fill="#DADCEA" />
      <rect x="43" y="22" width="14" height="6" rx="2" fill="#3B3F4E" />
      <path d="M43 38l6-5 4 2.5 8-7.5" stroke="#F2887C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function InsightVignette() {
  return (
    <svg width="70" height="48" viewBox="0 0 70 48" fill="none" aria-hidden="true">
      <rect x="1" y="4" width="62" height="18" rx="9" fill="#FFFFFF" stroke="#E0E2EE" strokeWidth="1.5" />
      <circle cx="12" cy="13" r="4" fill="#F2887C" />
      <circle cx="12" cy="13" r="4" fill="none" stroke="#F2887C" strokeWidth="1.2" opacity=".5">
        <animate attributeName="r" values="4;8" dur="1.6s" repeatCount="indefinite" />
        <animate attributeName="opacity" values=".5;0" dur="1.6s" repeatCount="indefinite" />
      </circle>
      <rect x="21" y="9" width="30" height="3.5" rx="1.75" fill="#3B3F4E" />
      <rect x="21" y="15" width="20" height="3" rx="1.5" fill="#DADCEA" />
      <rect x="7" y="28" width="62" height="18" rx="9" fill="#FFFFFF" stroke="#E0E2EE" strokeWidth="1.5" opacity=".65" />
      <circle cx="18" cy="37" r="4" fill="#F2C94C" opacity=".8" />
      <rect x="27" y="33" width="26" height="3.5" rx="1.75" fill="#B9BCCB" />
      <rect x="27" y="39" width="16" height="3" rx="1.5" fill="#E3E5EF" />
    </svg>
  );
}
