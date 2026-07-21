# SEMA React UI (Vite) -- development container.
#
# Runs the Vite dev server with HMR. docker-compose.yml bind-mounts the source
# and keeps /app/node_modules as a container-owned volume, so the Linux-built
# dependencies here are never shadowed by the Windows-built ones on the host
# (esbuild and rollup ship platform-specific binaries that would crash).

FROM node:24-alpine

WORKDIR /app

# Separate layer: dependencies are only reinstalled when the lockfile changes,
# not on every source edit. npm ci installs exactly what package-lock.json
# pins, unlike npm install which may resolve newer versions.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host 0.0.0.0 makes Vite reachable from the Windows host. Without it Vite
# binds to localhost inside the container and the published port serves nothing.
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
