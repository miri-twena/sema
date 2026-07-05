import tailwindcss from "tailwindcss";
import autoprefixer from "autoprefixer";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

// Load tailwind.config.js by absolute path: when the preview launcher runs
// vite from the repo root (cwd != frontend), Tailwind's default config lookup
// (relative to cwd) misses frontend/tailwind.config.js and emits base styles
// with no utilities. Passing the path explicitly fixes that.
const here = dirname(fileURLToPath(import.meta.url));

export default {
  plugins: [tailwindcss({ config: join(here, "tailwind.config.js") }), autoprefixer],
};
