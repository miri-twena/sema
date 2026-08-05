import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { ACCESS_REVOKED_EVENT, setAccessKey } from "../lib/pilotAccess";

export type PilotGateStatus = "checking" | "granted" | "locked";

export type SubmitKeyResult = { ok: true } | { ok: false; reason: "invalid" | "network" };

/**
 * Drives the internal-pilot access gate (see lib/pilotAccess.ts). Probes
 * `GET /api/health` on mount -- the SAME request whether SEMA_API_KEY is
 * configured or not, so local dev (empty key, the server exempts every
 * request) resolves to "granted" without ever rendering the gate, and a
 * production pilot with no stored key resolves to "locked" from the same
 * codepath. Also listens for ACCESS_REVOKED_EVENT so a key that stops
 * working mid-session (rotated/expired) re-shows the gate without needing a
 * page reload.
 */
export function usePilotAccess() {
  const [status, setStatus] = useState<PilotGateStatus>("checking");

  const probe = useCallback(async () => {
    setStatus("checking");
    try {
      await api.health();
      setStatus("granted");
    } catch {
      setStatus("locked");
    }
  }, []);

  useEffect(() => {
    probe();
    const onRevoked = () => setStatus("locked");
    window.addEventListener(ACCESS_REVOKED_EVENT, onRevoked);
    return () => window.removeEventListener(ACCESS_REVOKED_EVENT, onRevoked);
  }, [probe]);

  /** Stores `key`, re-probes, and reports what actually happened -- the gate
   * screen renders its own inline error from this, rather than from `status`
   * (which ACCESS_REVOKED_EVENT also drives, so alone it can't distinguish
   * "you just typed the wrong key" from "something else revoked access"). */
  const submitKey = useCallback(async (key: string): Promise<SubmitKeyResult> => {
    setAccessKey(key);
    try {
      await api.health();
      setStatus("granted");
      return { ok: true };
    } catch (err) {
      setStatus("locked");
      const message = err instanceof Error ? err.message : "";
      return { ok: false, reason: message.startsWith("401") ? "invalid" : "network" };
    }
  }, []);

  return { status, submitKey };
}
