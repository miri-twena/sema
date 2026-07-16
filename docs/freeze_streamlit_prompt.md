# Prompt: Freeze the Streamlit UI

Copy everything below this line into Claude Code.

---

## Goal

Freeze the Streamlit UI (`app/`) completely. From now on, the **React +
FastAPI stack (`frontend/` + `api/`) is the only product UI**. Streamlit
stays in the repo as a read-only internal dev tool — no deletion, no new
investment, and no accidental changes to it going forward.

This follows the recommendation in `docs/sema_pm_review.pdf` and
`docs/sema_cto_review.pdf`: two frontends are a double maintenance tax.

## Constraints

- **Do NOT delete `app/`** — it still works and is useful as a local dev
  sanity-check tool. Freeze, don't remove.
- **Do NOT touch `sema_core/`, `api/`, or `frontend/` logic.** This task is
  docs + guardrails only, with one small UI exception (the banner below).
- No new dependencies.
- Show me the full plan (max 5 bullets) before editing, then implement with
  diffs. Do not commit — show `git diff` and wait for my approval.

## Tasks

1. **Freeze banner** — add a small, dismissible-free notice at the top of
   the Streamlit chat page (`app/main.py`) and the admin page
   (`app/pages/admin.py`): "⚠️ Internal dev tool — frozen. The product UI
   is the React app (see README)." Keep it one `st.warning(...)` line each;
   don't redesign anything.

2. **CLAUDE.md** — update so future Claude Code sessions know the policy:
   - In *Architecture Preferences*: mark Streamlit (`app/`) as **frozen —
     dev tool only, do not modify without explicit approval**; React +
     FastAPI is the product.
   - In *UI Conventions*: note the RTL/Hebrew mechanism described there is
     Streamlit-specific and frozen with it; new RTL work happens in
     `frontend/` (see `frontend/src/lib/rtl.ts`).
   - In *Running SEMA Locally*: keep the Streamlit run instructions but
     label them "(frozen dev tool)", and add the React dev flow as the
     primary one (uvicorn `api.main:app` + `npm run dev` in `frontend/`).

3. **README.md** — in *Project Structure*, mark `app/` as "frozen internal
   dev tool" and make clear `frontend/` + `api/` is the product UI. Update
   any "how to run" sections the same way as CLAUDE.md.

4. **docs/project_vision.md** — add a dated decision note (like the
   existing 2026-06-15 implementation note): Streamlit frozen as of
   2026-07, React is the product UI, and why (maintenance tax, single
   design system, RTL handled once in React).

5. **Guardrail test** — add `tests/test_streamlit_freeze.py`: a fast pytest
   (no Streamlit import, no DB) that fails if `sema_core/` or `api/` ever
   imports from `app/` (scan source files for `from app` / `import app`
   patterns via ast or simple text scan of `.py` files). This makes the
   freeze enforceable, not just documented.

6. **Verify** — run the full `pytest` suite; confirm nothing else
   references `app/` from product code. Report results.

## Out of scope (do not do)

- Removing the rule-based fallback router (separate decision, separate task).
- Migrating the admin page to React (it's on the roadmap; not now).
- Any change to `frontend/`, `sema_core/`, `sql/`, or `evals/`.
