# T13 — Finding detail page

| Field | Value |
|---|---|
| Owner lane | Dev D |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 2 |
| Depends on | T11 |
| Unblocks | T17 |
| Branch | `t13-ui-finding` |

## Goal
Show the proof and the fix.

## Scope
- Header with CVE, package, score ring (animated), priority badge.
- Evidence CodeViewer with highlighted line and in-route tag; AI explanation card.
- Fix card: DiffViewer, tests passed, attempts, Open PR button; Integration card: Jira link, Teams sent, compliance id; vertical Timeline.
- Re-run fix button (POST /api/findings/{id}/fix).

## Acceptance criteria
- Renders the contract example perfectly; handles needs_human and not_reachable states.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T13: Finding detail page`, push, and print the NEXT block.
