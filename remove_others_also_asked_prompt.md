# Task: Remove "Others also asked" from answers

Remove the "Others also asked" chips section that renders under chat answers (added per Part 4 of `sidebar_redesign_prompt.md`).

1. In `frontend/src/components/AssistantResponseCard.tsx`: delete the section and its render logic entirely.
2. Delete any component/helper created solely for it (e.g. a chips component, session-tracking of shown questions, related props threaded from `App.tsx`/`TurnView.tsx`). `popularQuestions` usage elsewhere (home-screen "Trending in your company") stays untouched.
3. Remove now-unused imports/props/types; nothing else about the answer card changes.
4. Run `npm run lint` && `npm run build` — both must pass with no unused-var warnings.
