# T14 — Integrations and compliance pages

| Field | Value |
|---|---|
| Owner lane | Dev D |
| Model | Haiku 5.5 |
| Effort | low |
| Wave | 3 |
| Depends on | T11 |
| Unblocks | T17 |
| Branch | `t14-ui-integrations` |

## Goal
Make Boomi visible.

## Scope
- Integrations: B1–B4 cards with health dot (last call ok/failed), activity feed from `/api/integrations/activity` with animated new items (poll 3 s).
- Compliance: table from backend proxy of B4 (add `GET /api/compliance` in backend calling boomi_client.get_compliance), CSV export.

## Acceptance criteria
- Works in mock mode; shows the live Jira keys once Boomi is live.

## Hardening (docs/RISKS.md)
Implement and test these rows: E14.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T14: Integrations and compliance pages`, push, and print the NEXT block.
