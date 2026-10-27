# T12 — Overview and live scan pages

| Field | Value |
|---|---|
| Owner lane | Dev D |
| Model | Sonnet 5.5 |
| Wave | 2 |
| Depends on | T11 |
| Unblocks | T17 |
| Branch | `t12-ui-overview-scan` |

## Goal
The pages judges will stare at.

## Scope
- Overview per UI_SPEC: hero stats, Noise funnel animation driven by stats, recent scans table, Run scan modal (POST /api/scans).
- Scan live view: subscribe to SSE (`EventSource`), animate PipelineStepper, terminal-style log stream, findings table with filters and staggered rows.
- Mock mode replays a scripted SSE sequence from fixtures so it works without the backend.

## Acceptance criteria
- Full scan flow is watchable end-to-end in mock mode in ~25 s with smooth animation.
- Switching `VITE_USE_MOCK=false` works against the real backend.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T12: Overview and live scan pages`, push, and print the NEXT block.
