# Task: Persist drill-down conversations as widget-anchored threads

Make drill-down chats first-class, persistent threads anchored to the widget they were opened from — like Slack threads. Closing the panel no longer loses anything; reopening a widget resumes its thread. Read `AGENTS.md` first and follow its conventions (backend: `sema_core/` + `api/`, frontend: `frontend/`).

**Supersedes:** Part 2 of `chat_ux_fixes_prompt.md` (the discard-confirmation flow). If that was already implemented, remove the confirm bar — this model makes it unnecessary.

## Current state

- `frontend/src/components/DrillChat.tsx` opens a panel with its own `useChat({ persistKey: null })` — the thread lives only in memory and dies on close.
- The drill context is already structured: `DrillContext { kind: "kpi" | "chart" | "table" | "action", title, detail, initialInput?, dir? }`.
- Main conversations are persisted server-side (see `useConversations.ts`, `frontend/src/lib/api.ts`, and the conversation endpoints in `api/main.py`).

## Data model

A thread belongs to a main conversation and is keyed by its anchor:

- `conversation_id` — the parent conversation.
- `turn_index` — which turn's answer the widget appeared in (home-screen widgets, which have no turn, use a `null` turn_index with the client's overview as parent context — see "Home-screen widgets" below).
- `widget_kind` + `widget_title` — from `DrillContext`.
- Thread turns: same shape as main-chat turns (question, response, timestamps).

Rules:

- One thread per anchor: reopening the same widget resumes its thread.
- Threads are owned by the parent conversation: deleting/archiving the conversation deletes its threads. No independent lifecycle, and threads NEVER appear in the sidebar conversation list.
- Storage: follow whatever storage the existing conversations use (same DB/tables layer in `sema_core/` — inspect how conversations are persisted and mirror it).

## Backend

1. Schema/migration for threads + thread turns, mirroring the existing conversation storage patterns.
2. Endpoints (match existing API conventions in `api/main.py` + `api/models.py` + `api/serialize.py`):
   - `GET /api/conversations/{id}/threads` — list thread summaries (anchor + turn count) so the client can badge widgets.
   - `GET /api/conversations/{id}/threads/{thread_id}` — full thread transcript.
   - The existing chat endpoint already accepts `drillContext`; extend it to also accept the anchor (`conversation_id`, `turn_index`) and persist the turn into the right thread (creating it on first turn). Keep the server-side prompt-framing exactly as is — the client still never assembles context text (prompt-injection surface, see the comment in `DrillChat.tsx`).
3. Cascade delete with the parent conversation.

## Frontend

1. `DrillContext` gains the anchor fields; `KpiCards`, `ChartRenderer`, `DataTable`, `RecommendedActions`, and `TurnView`/`AssistantResponseCard` pass `turn_index` down (App already knows the index per `TurnView`).
2. `DrillChat` loads the existing thread for its anchor on open (show a small skeleton while loading) and continues it; turns persist via the extended chat endpoint. Remove any discard-confirmation UI.
3. **Thread badge:** widgets whose anchor has a thread show a small indicator in their corner — lucide `MessageCircle` icon + turn count, `bg-primary/10 text-primary-dark rounded-full text-[0.68rem] px-1.5`, positioned with logical properties, `aria-label="N follow-ups"`. Fetch thread summaries once per opened conversation (extend `useConversations` or a small new hook) and refresh after a drill turn completes. Reuse the hover-reveal pattern only if the badge crowds the widget — default is always visible.
4. **Home-screen widgets** (KPI cards on `HomeDashboard`): these have no parent conversation. Keep them ephemeral as today (no persistence, no badge) — do NOT invent a synthetic conversation for them. A `TODO` comment is enough.
5. Reopening a stored conversation restores its badges (thread summaries come from the list endpoint).

## Constraints

- No new frontend dependencies.
- RTL: logical properties only; thread badge and any new UI must respect `dir`.
- Accessibility: badge is announced via the widget's existing `aria-label` (append "N follow-ups"); skeleton has `aria-busy`.
- Tests: backend tests for thread create/resume/cascade-delete following the existing `tests/` patterns; run `pytest`, `npm run lint`, `npm run build`.

## Acceptance checklist

- [ ] Opening a drill on a widget, asking questions, closing, and reopening the same widget resumes the full thread.
- [ ] Widgets with threads show a count badge inside stored conversations, including after app reload.
- [ ] Threads never appear in the sidebar; deleting the parent conversation removes its threads (verified by test).
- [ ] Home-screen widgets remain ephemeral without errors.
- [ ] No discard-confirmation UI remains; closing a drill panel is always instant and safe.
- [ ] `pytest`, `npm run lint`, `npm run build` all pass.
