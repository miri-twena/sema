import Image from 'next/image';

export default function BrowserFrame({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="overflow-hidden rounded-card-lg border border-border bg-white shadow-hero">
      <div dir="ltr" className="flex items-center gap-3 border-b border-border-faint bg-tint-bg px-4 py-2.5">
        <span className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#F2887C]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#F2C94C]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#7DD4A8]" />
        </span>
        <span className="flex-1 truncate rounded-full bg-white px-3 py-1 text-center text-xs text-text-faint">
          app.sema.example
        </span>
      </div>
      <div className="relative aspect-[8/5] w-full bg-tint-bg">
        <Image src={src} alt={alt} fill sizes="(max-width: 768px) 90vw, 640px" style={{ objectFit: 'cover', objectPosition: 'top' }} loading="lazy" />
      </div>
    </div>
  );
}
