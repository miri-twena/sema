# Task: Thumbs up/down feedback on answers

Add per-answer feedback. Follow `AGENTS.md`. Frontend: `frontend/src/components/MessageActions.tsx` (existing action row on every answer), `TurnView.tsx`/`AssistantResponseCard.tsx`, `useChat.ts`, `lib/api.ts`. Backend: `api/` + storage layer in `sema_core/` (mirror how conversations are persisted).

## Backend

1. Store feedback per answer: `conversation_id`, `turn_index`, `rating` (`up`/`down`), optional `comment` (≤500 chars), `client_id`, user identifier if available, timestamp. One rating per turn — resubmitting updates it.
2. `POST /api/feedback` (create/update) + include current rating in the conversation-transcript response so reopened conversations show prior feedback state.
3. Follow existing endpoint conventions (`api/models.py`, `api/serialize.py`); migration mirrors existing table patterns.

## Frontend

1. In `MessageActions.tsx` add `ThumbsUp` / `ThumbsDown` (lucide) buttons beside copy/retry — same size and muted style. Only on completed answers (all modes), not on errors.
2. Selected state: filled/colored icon (`text-primary-dark` for up, keep down neutral-critical-free — use same primary tint; do NOT use red). Clicking the other icon switches; clicking the same one clears (send `rating: null` → delete).
3. On thumbs-down only: a small inline popover (reuse the `useDismiss` pattern) with an optional one-line text input "What was wrong?" + Send/Skip. Feedback posts immediately on click; the comment is a follow-up update. Never block the UI on the request; on failure revert silently and show nothing.
4. Optimistic UI; feedback state lives on the turn in `useChat` and hydrates from the transcript on conversation open.
5. Works in the drill panel too (it renders `TurnView`) — drill turns without a stored anchor may skip persistence (no-op) with a `TODO`.

## Constraints

- RTL-safe (logical properties, `dir`-aware popover placement); `aria-pressed` on the two buttons, `aria-label`s ("Good answer" / "Bad answer").
- No new deps. Tests: backend create/update/clear + one-per-turn uniqueness; run `pytest`, `npm run lint`, `npm run build`.

## Accept

- [ ] Rate, switch, and clear work with optimistic UI; state survives reopening the conversation.
- [ ] Thumbs-down offers an optional comment without forcing it.
- [ ] No feedback UI on error responses; drill panel doesn't crash.
- [ ] `pytest`, lint, build pass.
