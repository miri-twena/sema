// Minimal static file server for the Next.js static export (`out/`), used by the Playwright
// regression suite so it exercises the actual exported HTML/JS the site ships, not the dev
// server. Deliberately dependency-free (no `serve`/`http-server` package) -- this repo only
// has the `playwright` devDependency (not `@playwright/test`), and this is a small enough
// job to just do with Node's built-in `http`/`fs`.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, '..', 'out');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
};

function resolveFile(root, urlPath) {
  let p = decodeURIComponent(urlPath.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  let full = path.join(root, p);
  if (!full.startsWith(root)) return null; // guard against path traversal
  if (fs.existsSync(full) && fs.statSync(full).isDirectory()) {
    full = path.join(full, 'index.html');
  }
  if (!fs.existsSync(full)) {
    // trailingSlash:true export -- try appending /index.html for extensionless routes
    const withIndex = path.join(root, p, 'index.html');
    if (fs.existsSync(withIndex)) return withIndex;
    return null;
  }
  return full;
}

/** Creates (but does not start) an http.Server serving `root` (defaults to the `out/` export). */
export function createStaticServer(root = OUT_DIR) {
  return http.createServer((req, res) => {
    const file = resolveFile(root, req.url ?? '/');
    if (!file) {
      const notFound = path.join(root, '404.html');
      if (fs.existsSync(notFound)) {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        fs.createReadStream(notFound).pipe(res);
        return;
      }
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    const ext = path.extname(file);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
}

// Only auto-start (as a standalone server) when run directly, e.g. `node scripts/serve-static.mjs`.
// When imported (e.g. by the Playwright regression test), the caller controls listen()/close().
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const port = Number(process.env.PORT || 4173);
  const server = createStaticServer();
  server.listen(port, () => {
    console.log(`Static export served at http://localhost:${port}`);
  });
}
