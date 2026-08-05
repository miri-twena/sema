import { beforeEach, describe, expect, it, vi } from "vitest";

// This project's vitest setup runs in Node (no jsdom/happy-dom installed --
// see useLoginFlow.test.ts, which only exercises the pure reducer for the
// same reason). lib/pilotAccess.ts only touches `window` INSIDE function
// bodies, never at module-load time, so a minimal in-memory stand-in
// assigned before each test is enough to exercise it for real without
// adding a DOM dependency.
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

describe("pilotAccess", () => {
  let fake: ReturnType<typeof installFakeWindow>;

  beforeEach(() => {
    vi.resetModules();
    fake = installFakeWindow();
  });

  it("returns null when nothing is stored yet", async () => {
    const { getAccessKey } = await import("./pilotAccess");
    expect(getAccessKey()).toBeNull();
  });

  it("round-trips a key through set/get/clear", async () => {
    const { getAccessKey, setAccessKey, clearAccessKey } = await import("./pilotAccess");
    setAccessKey("pilot-secret-123");
    expect(getAccessKey()).toBe("pilot-secret-123");
    clearAccessKey();
    expect(getAccessKey()).toBeNull();
  });

  it("stores the key via sessionStorage, never localStorage", async () => {
    const { setAccessKey } = await import("./pilotAccess");
    setAccessKey("only-in-session");
    expect(fake.store.get("sema_pilot_access_key")).toBe("only-in-session");
  });

  it("withAccessKeyHeader adds X-API-Key only when a key is stored", async () => {
    const { withAccessKeyHeader, setAccessKey } = await import("./pilotAccess");
    expect(withAccessKeyHeader()).toEqual({});
    setAccessKey("abc123");
    expect(withAccessKeyHeader()).toEqual({ "X-API-Key": "abc123" });
  });

  it("withAccessKeyHeader merges over extra headers without dropping them", async () => {
    const { withAccessKeyHeader, setAccessKey } = await import("./pilotAccess");
    setAccessKey("abc123");
    expect(withAccessKeyHeader({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
      "X-API-Key": "abc123",
    });
  });

  it("withAccessKeyHeader with no key preserves extra headers as-is", async () => {
    const { withAccessKeyHeader } = await import("./pilotAccess");
    expect(withAccessKeyHeader({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
    });
  });

  it("revokeAccess clears the stored key and fires ACCESS_REVOKED_EVENT", async () => {
    const { ACCESS_REVOKED_EVENT, getAccessKey, revokeAccess, setAccessKey } = await import("./pilotAccess");
    setAccessKey("about-to-be-revoked");
    revokeAccess();
    expect(getAccessKey()).toBeNull();
    expect(fake.dispatchEvent).toHaveBeenCalledTimes(1);
    expect(fake.dispatchEvent.mock.calls[0][0].type).toBe(ACCESS_REVOKED_EVENT);
  });
});
