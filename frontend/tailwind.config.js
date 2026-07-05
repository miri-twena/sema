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
        primary: { DEFAULT: "#7C8CFF", dark: "#5B5F9F" },
        mint: "#7EE6C3",
        coral: "#FFB4A2",
        sun: "#FFE59A",
        sky: "#9ED8FF",
        ink: "#1E293B",
        muted: "#64748B",
        faint: "#94A3B8",
        line: "#E8EDF3",
        lineSoft: "#EEF2F7",
        critical: { bg: "#FEE2E2", fg: "#DC2626" },
        warning: { bg: "#FEF9C3", fg: "#CA8A04" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      boxShadow: {
        card: "0 6px 24px rgba(30,41,59,0.05)",
        pop: "0 10px 34px rgba(30,41,59,0.16)",
        bubble: "0 4px 14px rgba(124,140,255,0.25)",
      },
      borderRadius: { xl2: "18px" },
    },
  },
  plugins: [],
};
