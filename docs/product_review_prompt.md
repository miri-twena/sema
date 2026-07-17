# Prompt: Full Product Review — Head of Product

Copy everything below this line into Claude Code.

---

## Role

Act as a **Head of Product** with 15 years of experience in B2B SaaS
analytics products (think: someone who shipped at Looker, Amplitude, or
ThoughtSpot). You are doing a full product review of SEMA before a design
partner sees it. Be direct and critical — a polite review is a useless
review. Every claim must point to a concrete file, screen, or flow, not a
generality.

## Context — read first, in this order

1. `docs/project_vision.md` and `docs/mvp_scope.md` — what SEMA promises.
2. `docs/sema_pm_review.pdf` and `docs/sema_cto_review.pdf` — two prior
   reviews. **Do not repeat them.** Reference them where relevant and focus
   on what they did NOT cover: the end-to-end user experience and flow.
3. The product surface itself: `frontend/src/` (React — this IS the
   product; Streamlit `app/` is frozen, ignore it except as contrast),
   `api/main.py` (the contract), and `sema_core/agent/response.py` +
   `prompts.py` (what shapes every answer).

## Method — walk the product, don't just read it

If the environment allows (see CLAUDE.md "Running SEMA Locally"): start
Postgres, the FastAPI backend, and the React dev server, and drive the
product through the real API (`POST /api/chat`, `/api/chat/stream`,
`/api/alerts`, `/api/popular-questions`). If you cannot run it live, walk
the exact same journey through the code and say explicitly that this is a
code-walk, not a live session.

Simulate **three personas**, first session, zero onboarding:

- **CEO** — impatient, non-technical, opens the app once. Asks: "why did
  revenue drop in March?"
- **Marketing manager** — semi-technical. Asks: "which campaign should I
  cut?"
- **Analyst** — technical, skeptical of AI. Asks something the semantic
  layer does NOT cover, and checks whether she can trust/verify the answer.

For each persona, narrate the session step by step: what they see on load,
what they click, what they type, what comes back, where they hesitate,
where they get stuck, where they'd close the tab.

## The questions to answer — each gets its own section

For every section: verdict (1–5 score), evidence (files/flows/responses),
and the 2–3 highest-leverage fixes.

### 1. Are core features missing?
Given the promise "AI Business Advisor" — what does a user expect that
isn't there? Judge against the vision doc, not against a generic BI tool.
Cross-check the backlog in the two prior reviews; only add NEW gaps or
re-rank existing ones with a UX justification.

### 2. Does the flow make sense?
Map the actual flow: land → first question → answer → drill-down →
follow-up → return visit. Where does the flow break? Is the drill-down
discoverable? Does a conversation survive a refresh, and what does the user
experience when it doesn't? Is the alerts panel connected to the chat flow
or a dead end?

### 3. Would a business user instantly know what to do?
Look at the empty state: first screen, before any question. Is there a
clear "ask me this" affordance? Are the suggested questions good sales
copy for the product's strengths, or generic? Is anything on screen
(labels, panels, jargon like "semantic layer", "confidence") meaningless
to a non-analyst?

### 4. Time-to-aha: under 60 seconds?
Define SEMA's aha moment explicitly (proposal: "the user gets an insight
with a WHY that they couldn't get from their dashboard"). Then measure or
estimate the real path to it in seconds: load time, typing, agent latency
(check what streaming actually shows during the wait), reading the answer.
If it's over 60s, identify exactly which seconds to cut and how.

### 5. Where is the friction?
Hunt deliberately: setup friction (what must be configured before value?),
input friction (does the user know what they CAN ask? what happens on an
unanswerable question — graceful or dead-end?), output friction (walls of
text? charts that need interpretation? actions that aren't actionable?),
language friction (Hebrew/RTL consistency in the React app — check
`frontend/src/lib/rtl.ts` against actual components; mixed-language
answers), and repeat-visit friction (does anything remember me?).

### 6. Is it Enterprise Ready — in appearance and substance?
Appearance: does the UI look like a product a VP would demo to their board
(visual polish, empty/error/loading states, consistency)? Substance: walk
the checklist a buyer's security review would — auth, roles, audit trail,
data isolation story, SLA-ability. The CTO review covers the technical
gaps; your job is to judge how visible these gaps are to a *buyer* and
which ones block a pilot vs. a paid contract.

## Deliverable

Write `docs/product_review_flow.md`:

1. **Executive summary** — 5 sentences max: overall verdict + the single
   most important fix.
2. **Scorecard** — the six questions above, score 1–5 each, one-line
   rationale.
3. **Persona walkthroughs** — the three narrated sessions, with the exact
   moment each persona would churn (or convert).
4. **Findings by question** — the six sections.
5. **Top 10 fixes** — ranked by (user impact ÷ effort), each with: what,
   where (file/component), effort (S/M/L), and which persona it saves.
   Mark which are demo-blockers vs. pilot-blockers vs. polish.

## Rules

- Evidence over opinion: every finding cites a file, endpoint, or observed
  response.
- Do not modify any code. This is a review only.
- If you find a bug while walking the flow, log it in the findings — don't
  fix it.
- Keep the deliverable under ~4 pages equivalent. Sharp beats exhaustive.
