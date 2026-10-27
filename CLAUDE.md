# CLAUDE.md — PatchPilot

> Full background from the planning chat: `CONTEXT.md` (read it once at the start).

Read this file first in every session. It is the single source of truth for how to work in this repo.

## What we are building
PatchPilot is a fully automated vulnerability-to-fix autopilot for IT service companies.
For each client repo (any language OSV supports; Python analysed deepest) it: scans dependencies (OSV) and checks exploit data (CISA KEV, EPSS) → uses AI to decide whether the vulnerable
function is actually reachable from our code → scores real risk → upgrades the library, runs tests,
lets AI patch broken code (max 2 retries) → opens a GitHub pull request → notifies Boomi, which
creates the Jira ticket, posts the Slack alert, and writes the compliance log.

Background and decisions: `docs/DECISIONS.md`. Full plan: `docs/PLAN.md`. Architecture: `docs/ARCHITECTURE.md`
(diagrams: `docs/DIAGRAMS.md`, stack: `docs/TECH_STACK.md`). API contracts: `docs/API_CONTRACTS.md`.
All env vars and who provides them: `docs/CONFIG.md`. Security, network, error-handling rules: `docs/RISKS.md` (each task lists its rows). Model, effort and the "what next" queue for every task: `tasks/BOARD.md`. Start each task in a fresh session.

## Hackathon rules that affect you
- All code is written during the event (Oct 28, 2026, build sprint 9:20 AM – 12:20 PM). Code freeze 12:20 PM.
- Boomi integration is mandatory and is built by the Boomi team with Boomi Companion. We never build
  Boomi logic in this repo; we only call the endpoints defined in `docs/API_CONTRACTS.md`.
- LLM API keys are provided at kickoff. Never hardcode keys. Read them from `.env`.

## Repo layout
```
backend/            FastAPI app (Python 3.11)
  app/main.py       app + routers
  app/api/          REST routers (scans, findings, integrations, demo)
  app/core/         config, db, logging, events (SSE bus)
  app/models/       SQLModel tables + Pydantic schemas
  app/services/     cloner, ecosystems, scanner, threat_intel, symbols, reachability, risk, fixer, github_pr, boomi_client, llm
  app/pipeline.py   orchestrator: runs the stages and emits progress events
  tests/
frontend/           React 18 + Vite + TypeScript + Tailwind + Motion (motion/react)
  src/components/ src/pages/ src/lib/api.ts src/lib/mock/
(demo-target is a SEPARATE repo: D:\hackathon\demo-target -> github.com/BommepalliRoop/demo-target, built in T15)
contracts/          Example JSON payloads (source of truth for shapes)
docs/               Plan, architecture, contracts, UI spec, demo script, Boomi handoff
tasks/              One file per task (T00..T18) + BOARD.md + STATUS.md
.claude/commands/   /run-task and /next-task slash commands
```

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
- Backend tests: `cd backend && pytest -q`
- Frontend: `cd frontend && npm run dev` (port 5173)
- Both: `make dev` (Windows without make: `powershell -File scripts/dev.ps1`)
- Lint: `make lint`

## Engineering rules
1. Implement only the task you were given. Do not touch files owned by another task unless the task file says so.
2. Match `docs/API_CONTRACTS.md` exactly: field names, types, enums, status codes. If you think a contract is wrong, stop and say so; do not change it silently.
3. Every external dependency has a mock mode so lanes never block each other:
   `LLM_MODE=mock|live`, `BOOMI_MODE=mock|live`, `GITHUB_MODE=mock|live`. Default is `mock`.
4. Python: type hints everywhere, Pydantic models for all I/O, `httpx` for HTTP, no global state except the event bus.
5. LLM calls go only through `app/services/llm.py`. Prompts live in `backend/app/prompts/*.md`. All LLM outputs are JSON and validated with Pydantic; on invalid JSON retry once, then fall back safely.
6. Never execute code from the scanned repo outside a temporary virtualenv in `WORK_DIR/<scan_id>` (default `<system temp>/patchpilot`;
   `/tmp/patchpilot` in Docker). Use `tempfile`/`pathlib`, never hardcode `/tmp` (devs are on Windows).
7. Frontend: only call the backend through `src/lib/api.ts`. While the backend is not ready, use `src/lib/mock/` fixtures that match the contracts (`VITE_USE_MOCK=true`).
8. UI must look professional: follow `docs/UI_SPEC.md` (dark-first, motion, no default Tailwind look).
9. Keep secrets out of git. `.env` is gitignored; update `.env.example` when you add a variable.

## Definition of done for any task
- Acceptance criteria in the task file all pass.
- Tests for the task pass (`pytest -q` or `npm run build` for frontend tasks).
- `tasks/STATUS.md` row updated to `done` with a one-line note.
- Commit: `git commit -m "T<id>: <short summary>"` on branch `t<id>-<slug>`, then push and open a PR to `main` (or merge directly if the team agreed).
- Final message to the human ALWAYS ends with the NEXT block (see `.claude/commands/run-task.md`): next task id + title, model, effort, and the exact `/run-task <id>` prompt, for every unblocked task. Never skip it, even after a short reply, a re-check or a "no errors" follow-up.
