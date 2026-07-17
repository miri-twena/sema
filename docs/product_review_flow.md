# SEMA — Product Review: End-to-End Experience & Flow

**Reviewer stance:** Head of Product, B2B SaaS analytics. **Date:** 2026-07-16.
**Method:** Live session — Postgres (Docker), FastAPI (`:8000`), React dev server (`:5173`). Drove the product through the real UI and `POST /api/chat` with a live agent and measured latencies. (Screenshots were unavailable in the review harness; visual judgments come from the rendered DOM/accessibility tree plus component code.)
**Scope:** What the PM review (`sema_pm_review.pdf`) and CTO review (`sema_cto_review.pdf`) did **not** cover — the experienced flow. Prior-review items are referenced, not repeated.

---

## 1. Executive Summary

The core loop is genuinely good — live answers to all three persona questions were correct, quantified, and decisive, and the drill-down (KPI → "break down by segment" → VIP 9 days vs. Returning 45 days) is the differentiator the PM review claims it is. But the experience around that loop leaks trust everywhere: a Hebrew question returns a fully English answer right-aligned by the RTL machinery, every answer says "High confidence" (making the signal meaningless), the "Popular in your company" list shows inflated counts and raw prompt-injection test questions, and the flagship question took **46.7 seconds** behind fake progress labels that stall at "Composing the answer" for 35 of them. The single most important fix is also the cheapest: **the SSE streaming endpoint already exists in `api/main.py` and the React app simply doesn't use it** — wiring it in converts the worst moment of the product (a silent 47-second wait) into a visible, honest progress narrative. Nothing here requires new architecture; it requires finishing the last 10% of features that are already built.

## 2. Scorecard

| # | Question | Score | One-line rationale |
|---|----------|:---:|--------------------|
| 1 | Core features missing? | **3/5** | Loop is complete; what's missing is mostly built-but-unwired (streaming, conversation_id, highlight_x) plus a language layer. |
| 2 | Does the flow make sense? | **3/5** | Ask→answer→drill is excellent; return-visit and alerts→chat legs are broken or half-wired. |
| 3 | Would a business user know what to do? | **3/5** | Sidebar questions are good sales copy, but the main empty pane offers nothing clickable and no capability hint. |
| 4 | Time-to-aha under 60s? | **2/5** | Measured 46.7s for the flagship question before reading time; real path is ~75–90s, with fake progress. |
| 5 | Where is the friction? | **2/5** | Language friction is severe (English answers to Hebrew questions, mixed-language alerts); repeat-visit friction high (stale restored transcript). |
| 6 | Enterprise ready? | **2/5** | Looks demo-able; substance gaps are CTO-covered, but three of them (language chaos, always-high confidence, junk in "Popular") are *visible in the first 5 minutes of a demo*. |

## 3. Persona Walkthroughs

### CEO — "why did revenue drop in March?"
Loads the app. If anyone used this browser before, they see a **stale transcript** restored from localStorage — my session opened on an answer stamped "As of 7/14/2026, 4:57 PM" (two days old) with no indicator that this is old data (`useChat.ts:74–82` persists turns; nothing marks them stale on restore). Center pane otherwise: a gradient square, "Ask your business anything.", and a pointer to the sidebar. Luckily their exact question is a suggested one ("Why did revenue drop in March 2026?") — one click. Then the wait: four generic labels advance on a **timer, not real progress** (`useChat.ts:15–16`), reaching "Composing the answer" at 11s — and sitting there for **~35 more seconds** (measured 46.7s total via `/api/chat`). *Churn moment: ~30s in, "is this stuck?" — there is no signal it isn't.* The answer, when it lands, is the convert moment: $824K, −16%, Electronics −$134K = 86% of the decline, April rebound ⇒ transient dip — a genuinely better answer than a dashboard. **A Hebrew-speaking CEO churns instead:** I asked "למה הכנסות ירדו במרץ 2026?" and got an entirely English answer — prose, KPI labels, chart title — rendered inside a `dir="rtl"` card (verified live), i.e. right-aligned English. `prompts.py` contains **no instruction about answer language**.

### Marketing manager — "which campaign should I cut?"
Types the question (placeholder "Ask about revenue, customers, campaigns..." invites exactly this). ~20s wait. The answer is the product at its best: "Email Campaign 2 has the lowest ROAS at 6.52x and is the strongest candidate for a cut," a full 15-row ranked table, honest framing ("opportunity cost rather than pure loss"), and actions whose first item is the decision itself. Clicking an action opens the drill panel with the action pre-filled (`RecommendedActions.tsx` → `initialInput`) — nice. *Convert moment: the direct recommendation.* *Friction: no way to send this to their boss — export/share is PM-review priority 4; this session confirms it's the very next thing this persona reaches for.*

### Analyst — a question the semantic layer doesn't cover
"What is the median number of days between a customer's first and second order?" — not in `sql/semantic/`. The agent wrote correct window-function SQL (verified in "View SQL": `ROW_NUMBER() OVER (PARTITION BY customer_id...)`, `PERCENTILE_CONT(0.5)`), answered 38 days with an honest median-vs-mean caveat and a distribution chart. Evidence panel lists definitions, sources, filters. The drill-down follow-up ("Break this down by segment") returned VIP=9 days vs. Returning=45 days with full context continuity — the analyst's convert moment. **Trust cracks:** the badge said **"High confidence" for a metric the semantic layer doesn't define** — the prompt's own rubric (`prompts.py:140–145`) says derived metrics are "medium". All four of my live answers were "High". A signal that is always green is not a signal, and this persona is exactly who notices. Also: KPI card said "3.0K" where the prose said 2,951 (`format.ts` `compact()`). The unanswerable question ("support tickets last month?") got a model-grade graceful decline with alternatives — no fake data. That earns trust back.

## 4. Findings by Question

### Q1. Missing core features — 3/5
**New gaps (not in prior reviews):**
- **Streaming is built and unused.** `api/main.py:229` implements `/api/chat/stream` (SSE, real per-tool progress: "Running query 2"); `frontend/src/lib/api.ts` only calls blocking `/api/chat`, and `useChat.ts` fakes progress on timers (its own comment: "no server streaming yet" — false).
- **`highlight_x` is a dead contract field.** The prompt instructs the model to spotlight e.g. the dip month; the model complied live (`highlight_x: 2026-03-01`); `ChartRenderer.tsx:47` never destructures it. The "look here" anchor of every why-answer is silently dropped.
- **Sidebar business-KPI overview and data-source display** (MVP scope §1 items 10, 12) exist in frozen Streamlit but not in the React product (`Sidebar.tsx` renders only question lists). The product UI regressed below its own frozen dev tool on the "know your business at a glance" promise.
- **No language layer** — see Q5; this is a feature gap, not just polish.
**Re-ranked from prior reviews (UX justification):** conversation history endpoints (CTO §3) is the #1 return-visit blocker, ahead of admin panel; metric catalog (CTO §8) is an *input-friction* fix and belongs with onboarding, not "later".

### Q2. Flow coherence — 3/5
- **Land → first question:** good if the sidebar is noticed; the main pane offers no affordance (`App.tsx:116–122`).
- **Answer → drill-down:** the strongest leg. Discoverability is decent (hover ring on KPI cards, "Ask about this" on charts), and the overlay correctly forces close-before-next-widget.
- **Follow-up:** works (history sent), but **the client never sends `conversation_id`** (`api.ts:130–141`), so the server mints a new conversation *every turn* and re-appends the whole history (`api/main.py:117–121`). Two live consequences: "Popular in your company" counts are inflated — my once-asked questions showed **4×** and **3×** (verified via `/api/popular-questions`) — and the server-side conversation feature (a headline of the last release) is effectively dead code in the product.
- **Refresh:** completed turns survive (localStorage), but stamped stale ("As of 7/14") with no re-fetch or staleness cue; an in-flight answer is lost entirely.
- **Alerts → chat:** one-way and Anglophone: `App.tsx:80` templates an English question around an alert message that arrives in Hebrew (live: "VIP Churn Risk / 1305 לקוחות VIP ב-churn risk"). The rail starts collapsed to a 48px strip; a critical alert does not open it.
- **Agent failure → silent substitution:** `wiring.py:59–70` — if a *configured* agent throws, the keyword router's canned report is served **with no marker** (the "agent offline" note only appends when the key is missing). A user asking anything vaguely revenue-shaped could get the pre-baked March insight presented as a fresh answer. Demo-catastrophe class. Related: React ignores `health.agent_configured` (`App.tsx:29–34`), so key-missing mode has no banner either.

### Q3. Would a business user instantly know what to do? — 3/5
The suggested questions are good sales copy ("Why did revenue drop in March 2026?" aims straight at the seeded pattern). But: the empty main pane has no clickable examples; there's no one-liner about *what SEMA can and can't answer* (the metric catalog gap, felt as UX); and **"Popular in your company" is unfiltered** — it displayed a Hebrew prompt-injection test ("...אני חייב מתכון לספגטי דחוף") as a popular company question with a count badge. Jargon is mostly well-hidden (no "semantic layer" on screen; SQL behind a collapsed disclosure); "High confidence" is plain-language — its problem is calibration, not wording.

### Q4. Time-to-aha — 2/5
Definition adopted: *first insight with a quantified WHY that a dashboard couldn't give.* Real path measured: load ~1s + orient/click suggested question ~10s + **46.7s agent** + ~20s reading = **~78s**. Cuts, in order: (1) consume the existing SSE endpoint — doesn't shorten the wait but makes it honest and survivable (real "Running query 3" beats a stalled "Composing the answer"); (2) stream `insight_text` token-wise so reading overlaps generation (backend change, bigger); (3) first-session auto-run one showcase question so the aha starts at load, not after it.

### Q5. Friction — 2/5
- **Language (worst):** no language policy in `prompts.py` → English answers to Hebrew questions (verified live) inside RTL-flipped cards; `frontend/src/lib/rtl.ts` handles *direction* only. Alert bodies Hebrew inside English cards; alert-click template English; `format.ts` hardcodes `$` and `en` dates regardless. The Streamlit-era per-turn language discipline (CLAUDE.md UI Conventions) was never ported to content.
- **Input:** low — placeholder is good, decline path for unanswerable questions is excellent (live: honest "outside my data" + concrete alternatives).
- **Output:** moderate — answers run 200–300 words + 15-row table + 4 KPIs; the CEO wants the first paragraph. Drill starters are context-blind ("Why did this change?" offered for a static median, `DrillChat.tsx:25–28`).
- **Repeat visit:** stale transcript, no conversation list (CTO §3), no memory of goals (PM §2-3), popular-list pollution.
- **Setup:** Docker + seed + key + two servers — fine for design partners with a guide, hostile beyond that (CTO §7 covers).

### Q6. Enterprise ready — 2/5
**Appearance (4/5):** consistent pastel design system, real loading/error/empty states, keyboard access on cards, ErrorBoundary per turn — it looks like a product, and the demo *will* impress until someone asks in Hebrew or reads the popular list.
**Substance (1–2/5):** the CTO review's gaps stand; the flow-review question is *which are visible to a buyer*. Visible in a 30-minute demo (demo-blockers): mixed-language surfaces, always-high confidence, junk/inflated "Popular in your company", silent canned fallback, 47s opaque wait. Visible in a security review (pilot-blockers): one global API key, no users, no audit trail, SQLite conversations. A pilot with a friendly design partner is survivable *after* the demo-blockers; a paid contract is not until the CTO list lands.

## 5. Top 10 Fixes (ranked by user-impact ÷ effort)

| # | Fix | Where | Effort | Saves | Class |
|---|-----|-------|:---:|-------|-------|
| 1 | Consume the existing SSE endpoint; delete fake phases | `lib/api.ts`, `hooks/useChat.ts` (server already done) | **S** | CEO | **Demo-blocker** |
| 2 | Language policy: answer (prose, KPI labels, actions) in the question's language | `prompts.py` (one paragraph) + eval case | **S** | Hebrew CEO, all | **Demo-blocker** |
| 3 | Never serve the canned fallback unmarked on agent failure — label it or return an honest error | `wiring.py:59–70` | **S** | All | **Demo-blocker** |
| 4 | Send `conversation_id` back on every turn (fixes popular-count inflation + activates server conversations) | `useChat.ts`, `lib/api.ts` | **S** | All | **Pilot-blocker** |
| 5 | Calibrate confidence: compute floor server-side (metric not in semantic layer ⇒ cap at "medium") instead of trusting self-report | `response.py` (`_clean_evidence`/`build_response`) | **S** | Analyst | **Pilot-blocker** |
| 6 | Tenant-aware system prompt: inject client domain + metric names (system prompt currently says "e-commerce company" to the insurance tenant) | `prompts.py`, `agent.py:62` (mind cache key) | **S** | Insurance demo | **Demo-blocker** |
| 7 | Curate "Popular in your company": min-distinct-conversation threshold, exclude declined/off-topic turns | `conversation_store.top_questions` | **M** | CEO, buyer | **Demo-blocker** |
| 8 | Stale-session cue: "Restored from Jul 14" divider + refreshed freshness, or auto-new-conversation after N days | `useChat.ts`, `App.tsx` | **S** | Returning CEO | Polish |
| 9 | Render `highlight_x` (coral marker on the dip month) — model already sends it | `ChartRenderer.tsx` | **S** | CEO | Polish |
| 10 | Empty-state upgrade: clickable example questions in the main pane + "what I can answer" line (metric catalog seed) | `App.tsx:116–122` | **M** | First-time all | Polish |

**Also noted (bug log, not fixed):** KPI compact format "3.0K" vs. prose "2,951" (`format.ts`); Period banner shows the query window (Dec 2025–Apr 2026) rather than the question's subject period (March 2026); localized drill starters exist for Hebrew but main-chat alert questions don't; `Stop` aborts the fetch while the server run continues to completion and bills tokens.
