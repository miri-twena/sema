export function ChatMessage({ text, dir }: { text: string; dir: "rtl" | "ltr" }) {
  return (
    <div className="flex justify-end my-1.5">
      <div
        dir={dir}
        className="max-w-[72%] bg-primary text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-[0.92rem] leading-relaxed shadow-bubble"
      >
        {text}
      </div>
    </div>
  );
}
