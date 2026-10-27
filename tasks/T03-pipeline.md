# T03 — Scan orchestrator, SSE and scan API

| Field | Value |
|---|---|
| Owner lane | Dev A |
| Model | Opus 5.5 |
| Effort | high |
| Wave | 2 |
| Depends on | T01, T02 (others via stubs) |
| Unblocks | T17 |
| Branch | `t03-pipeline` |

## Goal
Run all stages in a background task and stream progress.

## Scope
- `pipeline.run_scan(scan_id)` runs stages clone → scan → symbols → reachability → risk → fix → pr → notify in order, per docs/ARCHITECTURE.md; parallelise per-finding work with `asyncio.gather` (limit 4).
- Emits events on the bus for every stage start/finish and per-finding progress; persists stats.
- Stages not yet implemented by other tasks are called through their module interface; if they raise NotImplementedError use a clearly-logged stub result so the pipeline still completes.
- `POST /api/scans` (accepts `X-API-Key` for machine callers), `GET /api/scans/{id}/events` as SSE (`sse-starlette`), `POST /api/findings/{id}/fix`.
- Only reachable or unsure(≥0.5) findings go to fix/pr/notify. Fix + PR run once **per package** (ARCHITECTURE "Group by package"); notify runs per finding. `auto_fix=false` → skip fix/pr, still notify with `event: finding.open`.
- `POST /api/scans`: validate `repo_url` against `ALLOWED_REPO_PREFIXES` (400 `repo_not_allowed`); store optional `owner_email`.

- When `POST /api/scans` is called with a valid `X-API-Key` (Boomi B1), record an integration event `process: B1`, `direction: inbound`, with the response status, so the Integrations page can show B1 health.

## Acceptance criteria
- POST a scan → SSE stream shows every stage → ends with `done`; scan stats saved.
- Pipeline survives a failing stage for one finding (marks that finding, continues others).
- Test with all external modes = mock.

## Hardening (docs/RISKS.md)
Implement and test these rows: S1, S3, S9, S10, N6, N7, N8, N9, E3, E4, E5, E6, E7, L7.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T03: Scan orchestrator, SSE and scan API`, push, and print the NEXT block.
