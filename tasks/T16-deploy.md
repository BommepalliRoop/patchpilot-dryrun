# T16 — Deployment

| Field | Value |
|---|---|
| Owner lane | Dev C |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 3 |
| Depends on | T03, T11 |
| Unblocks | T17 |
| Branch | `t16-deploy` |

## Goal
Public URLs so Boomi can call us and judges can open the app.

## Scope
- `backend/Dockerfile`: python:3.11-slim + git + osv-scanner binary (pinned release) + app; non-root user; healthcheck.
- Deploy backend to Render or Railway (persistent disk optional; SQLite is fine). Set env vars. Render's free tier sleeps after ~15 min idle (30–60 s cold start) and wipes the disk on redeploy: prefer Railway or a paid Render instance, call `/api/health` 5 minutes before the demo, and run the seed script after each deploy.
- Frontend: Vercel with `VITE_API_BASE_URL`; configure CORS in backend for the Vercel domain.
- Fallback: run locally + `cloudflared tunnel --url http://localhost:8000`; document both in `docs/DEPLOY.md`.
- Share BACKEND_URL with the Boomi team for B1.

- Docker image includes **Node.js 20 + npm** (for the npm fix adapter) besides Python 3.11, git and osv-scanner.

## Acceptance criteria
- Public `GET /api/health` reachable; frontend on Vercel talks to it; Boomi B1 can start a scan.

## Hardening (docs/RISKS.md)
Implement and test these rows: S2 (no `.env` in the image), S12, N10.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T16: Deployment`, push, and print the NEXT block.
