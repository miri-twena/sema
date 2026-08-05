import { useEffect, useState } from "react";
import { revokeAccess, withAccessKeyHeader } from "../lib/pilotAccess";

/**
 * `<img src>` can't carry a custom X-API-Key header, but the org logo is
 * served from a protected /api/* route (api/main.py's
 * GET /api/admin/org-settings/logo/{client_id}) once the internal-pilot gate
 * is active. Fetches the image WITH the header and returns a blob object URL
 * instead -- the same "fetch it ourselves" workaround exportTableCsv already
 * uses for downloads. Returns null while loading, on no url, or on failure
 * (the caller's existing "no logo" rendering already handles null).
 */
export function useProtectedImageSrc(url: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!url) {
      setSrc(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;

    fetch(url, { headers: withAccessKeyHeader() })
      .then((res) => {
        if (!res.ok) {
          if (res.status === 401) revokeAccess();
          throw new Error(`${res.status}`);
        }
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setSrc(null);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  return src;
}
