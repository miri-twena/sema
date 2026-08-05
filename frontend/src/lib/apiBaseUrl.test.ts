import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The API base URL bug: BASE (lib/api.ts) used to fall back to
// "http://localhost:8000" whenever VITE_API_URL was unset, with NO
// distinction between a dev server and a production build. That's exactly
// wrong for api/Dockerfile.prod's frontend-builder stage, which leaves
// VITE_API_URL unset ON PURPOSE (its own comment says so) expecting
// same-origin relative paths -- the built bundle would instead try to call
// an unreachable localhost:8000 from every deployed browser.
//
// BASE is a module-level const computed once at import time from
// `import.meta.env`, so each case needs vi.resetModules() + a fresh dynamic
// import AFTER stubbing the env -- same pattern as pilotAccess.test.ts.
// Exercised through resolveApiUrl (already exported) rather than exporting
// BASE itself just for testing.
describe("API base URL resolution (production same-origin fix)", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("production build, VITE_API_URL unset -> empty base (same-origin relative paths)", async () => {
    vi.stubEnv("PROD", true);
    const { resolveApiUrl } = await import("./api");
    // BASE = "" -> resolveApiUrl just returns the path unchanged, never
    // prefixed with a bogus "http://localhost:8000".
    expect(resolveApiUrl("/api/admin/org-settings/logo/ecommerce")).toBe(
      "/api/admin/org-settings/logo/ecommerce",
    );
  });

  it("dev server, VITE_API_URL unset -> localhost:8000", async () => {
    vi.stubEnv("PROD", false);
    const { resolveApiUrl } = await import("./api");
    expect(resolveApiUrl("/api/health")).toBe("http://localhost:8000/api/health");
  });

  it("explicit VITE_API_URL wins in production regardless of PROD", async () => {
    vi.stubEnv("PROD", true);
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const { resolveApiUrl } = await import("./api");
    expect(resolveApiUrl("/api/health")).toBe("https://api.example.com/api/health");
  });

  it("explicit VITE_API_URL wins in dev too", async () => {
    vi.stubEnv("PROD", false);
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const { resolveApiUrl } = await import("./api");
    expect(resolveApiUrl("/api/health")).toBe("https://api.example.com/api/health");
  });

  it("explicit empty-string VITE_API_URL is honored the same as unset-in-production", async () => {
    vi.stubEnv("PROD", true);
    vi.stubEnv("VITE_API_URL", "");
    const { resolveApiUrl } = await import("./api");
    expect(resolveApiUrl("/api/health")).toBe("/api/health");
  });

  it("no production bundle configuration can silently fall back to localhost", async () => {
    // The regression this whole file guards against, stated directly: for
    // EVERY VITE_API_URL a production build could plausibly ship with
    // (unset, or an explicit real URL), the resolved base must never be
    // "http://localhost:8000".
    for (const viteApiUrl of [undefined, "https://sema-pilot.onrender.com", ""]) {
      vi.resetModules();
      vi.unstubAllEnvs();
      vi.stubEnv("PROD", true);
      if (viteApiUrl !== undefined) vi.stubEnv("VITE_API_URL", viteApiUrl);
      const { resolveApiUrl } = await import("./api");
      expect(resolveApiUrl("/api/health")).not.toContain("localhost");
    }
  });
});
