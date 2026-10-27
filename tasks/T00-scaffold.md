# T00 — Repo scaffold and shared foundations

| Field | Value |
|---|---|
| Owner lane | Lead |
| Model | Sonnet 5.5 |
| Wave | 0 |
| Depends on | — |
| Unblocks | T01–T16 |
| Branch | `t00-scaffold` |

## Goal
Create the monorepo skeleton so every lane can start in parallel.

## Scope
- `backend/`: FastAPI app with `app/main.py`, routers stubbed per docs/API_CONTRACTS.md Part A returning fixtures, `app/core/config.py` (pydantic-settings reading `.env`), `app/core/db.py` (SQLite engine), `app/core/events.py` (in-memory async pub/sub per scan_id for SSE), `requirements.txt`, `pytest.ini`, one health test.
- `frontend/`: Vite + React 18 + TS + Tailwind + `motion` + `lucide-react` + `recharts` + `react-router-dom` + `shiki`; empty pages for routes in docs/UI_SPEC.md; `src/lib/api.ts` with typed functions for every Part A endpoint; `src/lib/types.ts` mirroring the contracts; `src/lib/mock/` fixtures copied from contracts; `VITE_USE_MOCK` switch.
- Root: `.env.example` (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_MODE, BOOMI_MODE, BOOMI_BASE_URL, BOOMI_USER, BOOMI_TOKEN, GITHUB_MODE, GITHUB_TOKEN, PATCHPILOT_API_KEY, BACKEND_URL, FRONTEND_URL), `.gitignore`, `Makefile` (dev, test, lint), `backend/Dockerfile` placeholder.
- Empty service modules with function signatures and docstrings for: cloner, scanner, symbols, reachability, risk, fixer, github_pr, boomi_client, llm, pipeline. Each raises NotImplementedError.

## Acceptance criteria
- `make dev` starts both apps; `GET /api/health` returns the contract shape.
- Frontend builds and shows the sidebar layout with all routes.
- `pytest -q` passes.
- Service signatures exactly match the module table in docs/ARCHITECTURE.md.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T00: Repo scaffold and shared foundations`, push, and print the NEXT block.
