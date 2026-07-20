// Clipboard primitives shared by every per-block copy action. One home for the
// async Clipboard API + its fallbacks, so individual blocks only describe WHAT
// to copy, never HOW.

/** Last-resort plain-text copy for browsers without the async Clipboard API
 * (or on an insecure origin, where navigator.clipboard is undefined). */
function execCommandCopy(text: string): boolean {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  // Off-screen but still focusable -- display:none would break select().
  ta.style.cssText = "position:fixed;top:-9999px;opacity:0";
  document.body.appendChild(ta);

  // Preserve whatever the user had selected on the page.
  const sel = document.getSelection();
  const previous = sel && sel.rangeCount > 0 ? sel.getRangeAt(0) : null;

  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  if (previous && sel) {
    sel.removeAllRanges();
    sel.addRange(previous);
  }
  return ok;
}

/** Plain text, with the execCommand fallback. Throws if both routes fail. */
export async function copyText(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Permission denied or not focused -- try the legacy path before failing.
  }
  if (!execCommandCopy(text)) throw new Error("Clipboard unavailable");
}

/** Dual-format write: `plain` for text targets (Excel reads the TSV), `html`
 * for rich targets (Docs/Word get a real table). Degrades to plain-only. */
export async function copyRich(plain: string, html: string): Promise<void> {
  try {
    if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/plain": new Blob([plain], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        }),
      ]);
      return;
    }
  } catch {
    // Fall through: a plain-text copy is far better than nothing.
  }
  await copyText(plain);
}

/** PNG to the clipboard. Pass the Blob as a PROMISE: ClipboardItem accepts one,
 * which keeps the rasterize step inside the click gesture -- browsers reject a
 * clipboard write that resolves after an await outside the user activation. */
export async function copyPng(blob: Promise<Blob> | Blob): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
    throw new Error("Image copy is not supported in this browser");
  }
  await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
}

/**
 * Rasterize a rendered chart SVG to a PNG blob. Recharts output is plain SVG
 * (no foreignObject), so serialize -> draw on a canvas -> export. Drawn at 2x
 * on a white background so the copied image is crisp and not transparent.
 */
export async function svgToPngBlob(svg: SVGSVGElement): Promise<Blob> {
  const rect = svg.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));

  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  // Recharts renders with inline `style="width:100%;height:100%"`, which BEATS
  // the width/height attributes above. Standalone (as a data: URL image) those
  // percentages have no containing block to resolve against, so the image
  // rasterizes blank. Pin the inline style to concrete pixels instead.
  clone.style.width = `${width}px`;
  clone.style.height = `${height}px`;
  const svgText = new XMLSerializer().serializeToString(clone);
  const svgUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgText);

  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("chart image failed to load"));
    img.src = svgUrl;
  });

  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("no 2d context");
  ctx.scale(scale, scale);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(img, 0, 0, width, height);

  return await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/png"),
  );
}

/** Copy an <img> as a PNG blob by drawing it to a canvas (handles non-PNG
 * sources, which the clipboard won't take directly). */
export async function imgToPngBlob(img: HTMLImageElement): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth || img.width;
  canvas.height = img.naturalHeight || img.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("no 2d context");
  ctx.drawImage(img, 0, 0);
  return await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/png"),
  );
}

// --- tabular serialization ---------------------------------------------------

type Row = Record<string, unknown>;

/** RAW values, not display-formatted ones: "10,856.1" would land in Excel as
 * text, and a thousands-separated id would be corrupted outright. Tabs and
 * newlines inside a cell are collapsed, since TSV has no escape syntax. */
function tsvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[\t\r\n]+/g, " ");
}

export function toTSV(columns: string[], rows: Row[]): string {
  const lines = [columns.map(tsvCell).join("\t")];
  for (const r of rows) lines.push(columns.map((c) => tsvCell(r[c])).join("\t"));
  return lines.join("\n");
}

function escapeHtml(v: unknown): string {
  return String(v ?? "").replace(/[&<>]/g, (c) => (c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"));
}

/** Matching HTML table so rich-paste targets (Docs, Word, Notion) get a real
 * table rather than tab-separated text. */
export function toHTMLTable(columns: string[], rows: Row[]): string {
  const head = `<thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const body = rows
    .map((r) => `<tr>${columns.map((c) => `<td>${escapeHtml(r[c])}</td>`).join("")}</tr>`)
    .join("");
  return `<table border="1" cellspacing="0" cellpadding="4">${head}<tbody>${body}</tbody></table>`;
}
