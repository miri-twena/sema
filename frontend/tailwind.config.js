import { fileURLToPath } from "url";
import { dirname } from "path";

// Resolve content globs relative to THIS file (not process cwd) so Tailwind
// finds the source whether vite runs from frontend/ or from the repo root
// with root=frontend (the preview launcher). Forward slashes only: Tailwind's
// glob engine (fast-glob) does not accept Windows backslashes.
const here = dirname(fileURLToPath(import.meta.url)).replace(/\\/g, "/");

/** @type {import('tailwindcss').Config} */
export default {
  content: [`${here}/index.html`, `${here}/src/**/*.{ts,tsx}`],
  theme: {
    extend: {
      colors: {
        // SEMA pastel-tech palette (mirrors app/components/theme.py)
        bg: "#F8FAFC",
        surface: "#FFFFFF",
        surfaceAlt: "#F1F5F9",
        // Login redesign (2026): primary raised toward the brand mark's
        // violet and darkened slightly off the old #7C8CFF, which failed AA
        // for small text on white -- ripples app-wide by design (buttons,
        // links, focus rings everywhere use this same token).
        primary: { DEFAULT: "#6C74F0", dark: "#5B5F9F" },
        // 3px focus ring (email/code inputs) -- primary at 14% opacity as a
        // named token rather than an inline `primary/[0.14]` utility, so the
        // exact value only lives in one place.
        primaryRing: "rgba(108,116,240,.14)",
        mint: "#7EE6C3",
        coral: "#FFB4A2",
        sun: "#FFE59A",
        sky: "#9ED8FF",
        ink: "#1E293B",
        muted: "#5F6878",
        faint: "#7B8494",
        line: "#E8EDF3",
        lineSoft: "#EEF2F7",
        critical: {
          bg: "#FEF3F2",
          fg: "#B32318",
          // Wrong-code/expired-code input background -- lighter than the
          // alert-block `bg`, used nowhere else.
          bgSoft: "#FEF9F8",
        },
        warning: { bg: "#FEF9C3", fg: "#B45309" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        // Logo wordmark ONLY (Logo.tsx) -- never headings, buttons, or body
        // copy. Logo.tsx currently sets this inline rather than via this
        // class (no build-time SVGR/JSX-className wiring needed for it), but
        // the token is declared here too so any future Tailwind usage stays
        // on the same family name instead of a second hardcoded string.
        display: ["Montserrat", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 6px 24px rgba(30,41,59,0.05)",
        pop: "0 10px 34px rgba(30,41,59,0.16)",
        bubble: "0 4px 14px rgba(124,140,255,0.25)",
        // Login card + its primary CTA (login redesign).
        loginCard: "0 1px 2px rgba(24,33,47,.04), 0 12px 32px -14px rgba(24,33,47,.14)",
        loginCta: "0 6px 16px -8px rgba(108,116,240,.7)",
        // KPI cards' white-card treatment (dashboard palette pass).
        kpiCard: "0 1px 2px rgba(24,33,47,.05)",
      },
      borderRadius: { xl2: "18px", control: "10px", loginCard: "16px" },
    },
  },
  plugins: [],
};
