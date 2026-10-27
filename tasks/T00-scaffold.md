# T00 — Repo scaffold and shared foundations

| Field | Value |
|---|---|
| Owner lane | Lead |
| Model | Sonnet 5.5 |
| Effort | high |
| Wave | 0 |
| Depends on | — |
| Unblocks | T01–T16 |
| Branch | `t00-scaffold` |

## Goal
Create the monorepo skeleton so every lane can start in parallel.

## Scope
- `backend/`: FastAPI app with `app/main.py`, routers stubbed per docs/API_CONTRACTS.md Part A returning fixtures, `app/core/config.py` (pydantic-settings reading `.env`), `app/core/db.py` (SQLite engine), `app/core/events.py` (in-memory async pub/sub per scan_id for SSE), `requirements.txt`, `pytest.ini`, one health test.
- `frontend/`: Vite + React 18 + TS + Tailwind + `motion` + `lucide-react` + `recharts` + `react-router-dom` + `shiki`; empty pages for routes in docs/UI_SPEC.md; `src/lib/api.ts` with typed functions for every Part A endpoint; `src/lib/types.ts` mirroring the contracts; `src/lib/mock/` fixtures copied from contracts; `VITE_USE_MOCK` switch.
- Root: `.env.example` (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL (optional), LLM_MODE, BOOMI_MODE, BOOMI_BASE_URL, BOOMI_USER, BOOMI_TOKEN, BOOMI_B2_PATH, BOOMI_B3_PATH, BOOMI_B4_PATH (defaults = contract paths), GITHUB_MODE, GITHUB_TOKEN, GITLAB_TOKEN (optional), DEMO_REPO_URL, ALLOWED_REPO_PREFIXES, WORK_DIR, THREAT_INTEL, DEMO_MODE, SCAN_TIMEOUT_S, MAX_SCANS_PER_HOUR, PATCHPILOT_API_KEY, BACKEND_URL, FRONTEND_URL; plus `frontend/.env.example` with VITE_API_BASE_URL, VITE_USE_MOCK — full list and sources in docs/CONFIG.md), `.gitignore`, `Makefile` (dev, test, lint) **and** `scripts/dev.ps1` (Windows has no `make`: starts backend + frontend in two windows), `backend/Dockerfile` placeholder.
- Empty service modules with function signatures and docstrings for: cloner, ecosystems, scanner, threat_intel, symbols, reachability, risk, fixer, github_pr, boomi_client, llm, pipeline. Each raises NotImplementedError.

## Acceptance criteria
- `make dev` (or `scripts/dev.ps1` on Windows) starts both apps; `GET /api/health` returns the contract shape.
- Frontend builds and shows the sidebar layout with all routes.
- `pytest -q` passes.
- Service signatures exactly match the module table in docs/ARCHITECTURE.md.

## Hardening (docs/RISKS.md)
Implement and test these rows: S4 (`redact()` helper), S12, S13, E1, E2, E8, O2.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T00: Repo scaffold and shared foundations`, push, and print the NEXT block.
