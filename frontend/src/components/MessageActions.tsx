import { useState } from "react";
import { Copy, Check, RotateCw, ThumbsDown, ThumbsUp } from "lucide-react";
import { copyText } from "../lib/clipboard";
import { useUiLang } from "../lib/useUiLang";
import { useDismiss } from "../hooks/useDismiss";
import { FEEDBACK_COPY } from "../lib/feedbackCopy";
import { api, type TurnFeedback } from "../lib/api";

/**
 * Action row shown under a completed answer. This is the "copy the WHOLE
 * answer" escape hatch -- per-block copy (CopyButton/CopyableBlock, floated
 * into each block) is the primary interaction, so there is no chart-image
 * button here any more; the chart owns that action itself.
 *
 * Feedback (answer_feedback_prompt.md): optimistic and best-effort. A rating
 * click applies to the UI immediately and posts in the background; a failed
 * request reverts silently (no error shown -- this is a nice-to-have signal,
 * never worth interrupting the reading experience over). Persistence only
 * happens when conversationId/turnIndex/clientId are ALL present -- absent
 * inside the drill panel (drill turns are out of scope, see TurnView) and for
 * a turn with no server conversation yet, where the click still updates the
 * button state locally but nothing is sent.
 */
export function MessageActions({
  text,
  onRetry,
  conversationId,
  turnIndex,
  clientId,
  feedback,
  onFeedbackChange,
}: {
  text: string;
  onRetry?: () => void;
  conversationId?: string;
  turnIndex?: number;
  clientId?: string;
  feedback?: TurnFeedback | null;
  onFeedbackChange?: (feedback: TurnFeedback | null) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const [vote, setVote] = useState<"up" | "down" | null>(feedback?.rating ?? null);
  const [comment, setComment] = useState<string | null>(feedback?.comment ?? null);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const lang = useUiLang();
  const ft = FEEDBACK_COPY[lang];
  const popoverRef = useDismiss<HTMLDivElement>(commentOpen, () => setCommentOpen(false));

  const canPersist = conversationId !== undefined && turnIndex !== undefined && clientId !== undefined;

  const copyAll = async () => {
    try {
      await copyText(text);
      setFailed(false);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setFailed(true);
    }
  };

  /** Posts the new rating/comment; on failure, reverts to whatever was there
   * right before THIS optimistic update (passed in explicitly, rather than
   * read back off state, so a revert is correct even if another change
   * happened while the request was in flight). */
  const post = async (
    rating: "up" | "down" | null,
    commentValue: string | null,
    revertTo: { rating: "up" | "down" | null; comment: string | null },
  ) => {
    if (!canPersist) return;
    try {
      await api.sendFeedback({
        conversation_id: conversationId,
        turn_index: turnIndex,
        client_id: clientId,
        rating,
        comment: commentValue ?? undefined,
      });
    } catch {
      // Silent revert -- never block the UI on this request, never surface
      // an error for a feature this incidental to reading the answer.
      setVote(revertTo.rating);
      setComment(revertTo.comment);
      onFeedbackChange?.(revertTo.rating ? { rating: revertTo.rating, comment: revertTo.comment } : null);
    }
  };

  const castVote = (next: "up" | "down") => {
    const previous = { rating: vote, comment };
    const nextVote = vote === next ? null : next;
    const nextComment = nextVote === "down" ? comment : null;
    setVote(nextVote);
    setComment(nextComment);
    onFeedbackChange?.(nextVote ? { rating: nextVote, comment: nextComment } : null);
    if (nextVote === "down") {
      setCommentDraft("");
      setCommentOpen(true);
    } else {
      setCommentOpen(false);
    }
    void post(nextVote, nextComment, previous);
  };

  const sendComment = () => {
    const trimmed = commentDraft.trim();
    const previous = { rating: vote, comment };
    setCommentOpen(false);
    if (!trimmed || vote !== "down") return;
    setComment(trimmed);
    onFeedbackChange?.({ rating: "down", comment: trimmed });
    void post("down", trimmed, previous);
  };

  const btn =
    "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted hover:bg-surfaceAlt hover:text-ink transition";

  return (
    <div dir="ltr" className="relative mt-3 pt-2.5 border-t border-line flex items-center gap-1">
      <button onClick={copyAll} className={btn} title="Copy the entire answer" aria-label="Copy entire answer">
        {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
        {copied ? "Copied" : "Copy answer"}
      </button>

      {onRetry && (
        <button onClick={onRetry} className={btn} title="Ask this question again" aria-label="Retry question">
          <RotateCw size={14} /> Retry
        </button>
      )}

      <span className="w-px h-4 bg-line mx-0.5" aria-hidden />

      <button
        onClick={() => castVote("up")}
        className={btn}
        title={ft.up}
        aria-label={ft.up}
        aria-pressed={vote === "up"}
      >
        <ThumbsUp size={14} className={vote === "up" ? "text-primary" : undefined} fill={vote === "up" ? "currentColor" : "none"} />
      </button>
      <button
        onClick={() => castVote("down")}
        className={btn}
        title={ft.down}
        aria-label={ft.down}
        aria-pressed={vote === "down"}
      >
        <ThumbsDown size={14} className={vote === "down" ? "text-primary" : undefined} fill={vote === "down" ? "currentColor" : "none"} />
      </button>

      {failed && <span className="text-xs text-muted ms-1">Copy failed</span>}

      {commentOpen && (
        <div
          ref={popoverRef}
          role="dialog"
          dir={lang === "he" ? "rtl" : "ltr"}
          className="absolute top-[calc(100%+4px)] start-0 z-30 w-72 rounded-xl2 border border-line bg-surface shadow-pop p-3"
        >
          <p className="text-[0.78rem] font-medium text-ink mb-1.5">{ft.commentPrompt}</p>
          <input
            autoFocus
            value={commentDraft}
            onChange={(e) => setCommentDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendComment()}
            maxLength={500}
            placeholder={ft.commentPlaceholder}
            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
          <div className="flex items-center justify-end gap-2 mt-2">
            <button
              type="button"
              onClick={() => setCommentOpen(false)}
              className="text-[0.75rem] text-muted hover:text-ink px-2 py-1"
            >
              {ft.skip}
            </button>
            <button
              type="button"
              onClick={sendComment}
              className="rounded-lg bg-primary px-3 py-1 text-[0.75rem] font-medium text-white hover:bg-primary/90 transition"
            >
              {ft.send}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
