import { useState, type RefObject } from "react";
import { Copy, Check, Image as ImageIcon, RotateCw } from "lucide-react";

type Copied = "text" | "image" | null;

/**
 * Rasterize a rendered chart SVG to a PNG blob. Recharts output is plain SVG
 * (no foreignObject), so serialize -> draw on a canvas -> export. Drawn at 2x
 * on a white background so the copied image is crisp and not transparent.
 */
async function svgToPngBlob(svg: SVGSVGElement): Promise<Blob> {
  const rect = svg.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));

  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
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

/**
 * Action row shown under a completed answer: copy the text, copy the chart as
 * an image (only when there is one), and retry the question. `containerRef`
 * points at the answer's DOM so the chart SVG can be found for image copy.
 */
export function MessageActions({
  text,
  hasImage,
  containerRef,
  onRetry,
}: {
  text: string;
  hasImage: boolean;
  containerRef: RefObject<HTMLElement | null>;
  onRetry?: () => void;
}) {
  const [copied, setCopied] = useState<Copied>(null);
  const [failed, setFailed] = useState(false);

  const flash = (which: Copied) => {
    setCopied(which);
    setFailed(false);
    window.setTimeout(() => setCopied(null), 1500);
  };

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(text);
      flash("text");
    } catch {
      setFailed(true);
    }
  };

  const copyImage = async () => {
    const svg = containerRef.current?.querySelector("svg");
    if (!svg) return;
    try {
      // Pass a Promise<Blob> to ClipboardItem so the whole rasterize step stays
      // inside the click gesture -- browsers reject a bare async clipboard write.
      const item = new ClipboardItem({ "image/png": svgToPngBlob(svg as SVGSVGElement) });
      await navigator.clipboard.write([item]);
      flash("image");
    } catch {
      setFailed(true);
    }
  };

  const btn =
    "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-surfaceAlt hover:text-ink transition";

  return (
    <div dir="ltr" className="mt-3 pt-2.5 border-t border-line flex items-center gap-1">
      <button onClick={copyText} className={btn} title="Copy answer text" aria-label="Copy answer text">
        {copied === "text" ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
        {copied === "text" ? "Copied" : "Copy"}
      </button>

      {hasImage && (
        <button onClick={copyImage} className={btn} title="Copy chart as image" aria-label="Copy chart as image">
          {copied === "image" ? <Check size={14} className="text-emerald-600" /> : <ImageIcon size={14} />}
          {copied === "image" ? "Copied" : "Copy image"}
        </button>
      )}

      {onRetry && (
        <button onClick={onRetry} className={btn} title="Ask this question again" aria-label="Retry question">
          <RotateCw size={14} /> Retry
        </button>
      )}

      {failed && <span className="text-xs text-muted ms-1">Copy failed</span>}
    </div>
  );
}
