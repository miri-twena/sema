import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { HelpCircle, Info, Sparkles } from "lucide-react";
import type { ChatResponse } from "../lib/api";
import { CodeBlock, InlineCode } from "./CodeBlock";

/** Tappable suggestion pill. Sends the text as the next question, continuing
 * the SAME conversation -- the caller passes useChat.send, which keeps the
 * conversation_id, so a clarification choice never starts a new chat. */
function Choice({ text, dir, onAsk }: { text: string; dir: "rtl" | "ltr"; onAsk: (q: string) => void }) {
  return (
    <button
      onClick={() => onAsk(text)}
      dir={dir}
      className="text-start text-[0.84rem] rounded-lg border border-lineSoft bg-primary/[0.06] text-primary-dark px-3 py-2 hover:bg-surface hover:border-primary transition"
    >
      {text}
    </button>
  );
}

const MD = { pre: CodeBlock, code: InlineCode };

/**
 * Renders the non-`answer` response modes. Each is a calm, first-class state --
 * deliberately NOT an error: the whole point of the uncertainty flow is that
 * "I need one more detail" and "I can't ground this" are normal outcomes, so
 * neither gets warning styling, a confidence badge, or analytical furniture
 * (the server already strips KPIs/charts/evidence for these modes).
 */
export function ModeCard({
  response,
  dir,
  onAsk,
}: {
  response: ChatResponse;
  dir: "rtl" | "ltr";
  onAsk?: (q: string) => void;
}) {
  const mode = response.mode;

  if (mode === "off_topic") {
    // Just a normal assistant bubble -- light, human, no chrome at all.
    return (
      <div className="sema-prose text-ink text-[0.94rem]">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
          {response.answer}
        </ReactMarkdown>
      </div>
    );
  }

  if (mode === "clarification") {
    const options = response.clarification_options ?? [];
    return (
      <div className="rounded-xl border border-lineSoft bg-primary/[0.04] p-3.5">
        <div className="flex items-center gap-1.5 mb-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-primary-dark">
          <HelpCircle size={13} /> Quick question
        </div>
        <div className="sema-prose text-ink text-[0.92rem]">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
            {response.answer}
          </ReactMarkdown>
        </div>
        {options.length > 0 && onAsk && (
          <div className="mt-2.5 flex flex-col gap-1.5">
            {options.map((o) => (
              <Choice key={o} text={o} dir={dir} onAsk={onAsk} />
            ))}
          </div>
        )}
        <div className="mt-2 text-[0.75rem] text-muted">
          Or just type your own answer below.
        </div>
      </div>
    );
  }

  // cannot_answer -- transparent and specific, never a technical error.
  const alternatives = response.follow_up_questions ?? [];
  return (
    <div className="rounded-xl border border-line bg-surfaceAlt p-3.5">
      <div className="flex items-center gap-1.5 mb-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
        <Info size={13} /> Why I can't answer this
      </div>
      <div className="sema-prose text-ink text-[0.92rem]">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
          {response.answer}
        </ReactMarkdown>
      </div>

      {response.missing && (
        <div className="mt-2.5 rounded-lg border border-lineSoft bg-surface px-3 py-2 text-[0.82rem] text-muted">
          <span className="font-medium text-ink">Missing: </span>
          {response.missing}
        </div>
      )}

      {alternatives.length > 0 && onAsk && (
        <div className="mt-3">
          <div className="flex items-center gap-1.5 mb-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
            <Sparkles size={13} /> You could ask instead
          </div>
          <div className="flex flex-col gap-1.5">
            {alternatives.map((q) => (
              <Choice key={q} text={q} dir={dir} onAsk={onAsk} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
