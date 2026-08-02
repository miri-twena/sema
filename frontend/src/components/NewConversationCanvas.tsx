import { type ForwardedRef } from "react";
import { MessageSquareText, TrendingUp } from "lucide-react";
import type { PopularQuestion } from "../lib/api";
import { ChatInput } from "./ChatInput";
import { QuestionChip } from "./QuestionChip";
import { limitPool, useCyclingPlaceholder } from "../hooks/useCyclingPlaceholder";
import { useT } from "../locales";
import { useUiLang } from "../lib/useUiLang";
import { dirOf } from "../lib/rtl";

const MAX_CARDS = 4;

/**
 * "New conversation"'s clean ask canvas (new_conversation_canvas_prompt.md,
 * approved mode A) -- a SEPARATE screen from the home dashboard, not a
 * variant of it: no brief, no KPIs, no attention line. The user's intent
 * here is "I want to ask", so the screen answers only that. Supersedes
 * home_hebrew_polish_prompt.md item 5's "move the intro block up" fix --
 * that intro block now lives on ITS OWN screen entirely, reached via
 * "New conversation", while the home dashboard keeps its own top ask bar
 * (home_ask_bar_top_prompt.md) unchanged as a second, separate entry point.
 */
export function NewConversationCanvas({
  suggested,
  popularQuestions,
  onAsk,
  onStopAsk,
  asking,
  askInputRef,
}: {
  suggested: string[];
  popularQuestions: PopularQuestion[];
  onAsk: (q: string) => void;
  onStopAsk?: () => void;
  asking?: boolean;
  askInputRef?: ForwardedRef<HTMLTextAreaElement>;
}) {
  const t = useT();
  const dir = useUiLang() === "he" ? "rtl" : "ltr";
  const cycling = useCyclingPlaceholder(suggested);
  const cards = limitPool(suggested, MAX_CARDS);

  return (
    <div className="py-12 md:py-20 max-w-xl mx-auto">
      <div dir={dir} className="text-center">
        <h2 className="text-2xl font-semibold tracking-tight text-ink">{t.newConversation.headline}</h2>
        <p className="text-sm text-muted mt-1.5">{t.newConversation.subtitle}</p>
      </div>

      {/* Visually primary: a soft accent ring around the (otherwise
          unmodified) hero input, so it reads as THE action on this screen. */}
      <div className="mt-6 rounded-2xl ring-2 ring-primary/15">
        <ChatInput
          ref={askInputRef}
          onSend={onAsk}
          onStop={onStopAsk}
          loading={asking}
          variant="hero"
          autoFocus
          placeholder={cycling.text}
          placeholderDir={cycling.text ? dirOf(cycling.text) : undefined}
          onFocus={cycling.stop}
        />
      </div>

      {cards.length > 0 && (
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {cards.map((q) => (
            <button
              key={q}
              onClick={() => onAsk(q)}
              className="group text-start flex items-start gap-3 rounded-xl border border-line bg-surface shadow-card px-4 py-3.5 hover:border-primary hover:-translate-y-px transition-all"
            >
              <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                <MessageSquareText size={13} />
              </span>
              <span className="text-sm text-ink leading-snug" dir="auto">
                {q}
              </span>
            </button>
          ))}
        </div>
      )}

      {popularQuestions.length > 0 && (
        <div className="mt-8">
          <div dir={dir} className="flex items-center gap-1.5 mb-2 justify-center">
            <TrendingUp size={13} className="text-primary" aria-hidden />
            <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
              {t.home.trendingInCompany}
            </span>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {popularQuestions.map((p) => (
              <QuestionChip key={p.question} question={p.question} count={p.times_asked} onPick={onAsk} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
