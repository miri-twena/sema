import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Docker Desktop on Windows does not propagate filesystem events from the host
// into a Linux container, so a bind-mounted source tree needs a POLLING watcher
// or hot reload silently never fires. Gated on an env var set only by
// docker-compose.yml: running Vite natively on Windows keeps native events,
// since polling costs CPU and adds up to `interval` ms of latency.
const usePolling = process.env.VITE_USE_POLLING === "true";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: usePolling ? { watch: { usePolling: true, interval: 300 } } : {},
})
