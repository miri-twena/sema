import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Integration between lib/api.ts and lib/pilotAccess.ts: every fetch helper
// must send X-API-Key when a pilot key is stored, and a 401 response must
// clear it + tell the gate to reappear (docs/deployment.md's Render
// section). No jsdom/RTL here -- see pilotAccess.test.ts's own note; a fake
// `window` (sessionStorage + dispatchEvent) is enough, and Node's built-in
// `fetch`/`Response`/`Event` globals cover the rest.
function installFakeWindow() {
  const store = new Map<string, string>();
  const dispatchEvent = vi.fn();
  (globalThis as unknown as { window: unknown }).window = {
    sessionStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    },
    dispatchEvent,
  };
  return { store, dispatchEvent };
}

function jsonResponse(body: unknown, init?: { status?: number }) {
  return new Response(JSON.stringify(body), {
    status: init?.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api.ts <-> pilotAccess integration", () => {
  let fake: ReturnType<typeof installFakeWindow>;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    fake = installFakeWindow();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends no X-API-Key header when no key is stored (local dev parity)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "ok", db_connected: true, agent_configured: true, active_client: "ecommerce" }));
    const { api } = await import("./api");
    await api.health();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).not.toHaveProperty("X-API-Key");
  });

  it("sends X-API-Key when a key is stored", async () => {
    const { setAccessKey } = await import("./pilotAccess");
    setAccessKey("my-pilot-key");
    fetchMock.mockResolvedValue(jsonResponse({ status: "ok", db_connected: true, agent_configured: true, active_client: "ecommerce" }));
    const { api } = await import("./api");
    await api.health();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toMatchObject({ "X-API-Key": "my-pilot-key" });
  });

  it("a 401 response clears the stored key and fires the revoked event", async () => {
    const { setAccessKey, ACCESS_REVOKED_EVENT, getAccessKey } = await import("./pilotAccess");
    setAccessKey("now-invalid");
    fetchMock.mockResolvedValue(jsonResponse({ detail: "invalid or missing API key" }, { status: 401 }));
    const { api } = await import("./api");
    await expect(api.health()).rejects.toThrow();
    expect(getAccessKey()).toBeNull();
    expect(fake.dispatchEvent).toHaveBeenCalledTimes(1);
    expect(fake.dispatchEvent.mock.calls[0][0].type).toBe(ACCESS_REVOKED_EVENT);
  });

  it("a non-401 error does not touch the stored key", async () => {
    const { setAccessKey, getAccessKey } = await import("./pilotAccess");
    setAccessKey("still-valid");
    fetchMock.mockResolvedValue(jsonResponse({ detail: "boom" }, { status: 500 }));
    const { api } = await import("./api");
    await expect(api.health()).rejects.toThrow();
    expect(getAccessKey()).toBe("still-valid");
    expect(fake.dispatchEvent).not.toHaveBeenCalled();
  });

  it("postJSON (used by chat) also sends X-API-Key", async () => {
    const { setAccessKey } = await import("./pilotAccess");
    setAccessKey("chat-key");
    fetchMock.mockResolvedValue(
      jsonResponse({
        answer: "",
        kpis: [],
        chart: null,
        table: null,
        actions: [],
        follow_up_questions: [],
        sql_used: null,
        confidence: null,
        evidence: null,
        status: "ok",
        error: null,
      }),
    );
    const { api } = await import("./api");
    await api.chat("hi", [], "ecommerce");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toMatchObject({ "X-API-Key": "chat-key", "Content-Type": "application/json" });
  });
});
