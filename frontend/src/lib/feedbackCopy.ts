// Bilingual copy for per-answer thumbs up/down feedback
// (answer_feedback_prompt.md) -- supersedes the "preview" ANSWER_FEEDBACK
// entry that used to live in placeholderCopy.ts. Same Record<Lang,{...}>
// shape as lib/loginCopy.ts / lib/placeholderCopy.ts.

export const FEEDBACK_COPY = {
  en: {
    up: "Good answer",
    down: "Bad answer",
    commentPrompt: "What was wrong?",
    commentPlaceholder: "Optional...",
    send: "Send",
    skip: "Skip",
  },
  he: {
    up: "תשובה טובה",
    down: "תשובה לא טובה",
    commentPrompt: "מה היה לא בסדר?",
    commentPlaceholder: "לא חובה...",
    send: "שליחה",
    skip: "דלג/י",
  },
} as const;
