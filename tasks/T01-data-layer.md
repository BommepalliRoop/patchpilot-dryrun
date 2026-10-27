# T01 — Data models and persistence

| Field | Value |
|---|---|
| Owner lane | Dev A |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 1 |
| Depends on | T00 |
| Unblocks | T03, T10, T17 |
| Branch | `t01-data-layer` |

## Goal
SQLModel tables and Pydantic API schemas.

## Scope
- Tables per docs/ARCHITECTURE.md Data model (including integration fields, timeline and the per-package `fixes` row); ID helpers (`scn_`, `fnd_`, `fix_` prefixes).
- Pydantic schemas: Scan, ScanStats, FindingSummary, FindingDetail, Evidence, FixInfo, IntegrationInfo, TimelineItem, IntegrationEvent — field names identical to docs/API_CONTRACTS.md.
- Repository functions: create_scan, update_scan_stage, add_finding, update_finding, add_fix, add_integration_event, get_* and list_* with filters.
- Replace fixture responses in routers `GET /api/scans*`, `GET /api/findings*`, `GET /api/integrations/activity`, `POST /api/demo/reset` with real DB reads.

## Acceptance criteria
- Unit tests for create/read/filter.
- API responses validate against the example JSON in contracts/ (write a test that loads them).

## Hardening (docs/RISKS.md)
Implement and test these rows: S8 (reset needs `X-API-Key` + `DEMO_MODE=true`), E8, L10.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T01: Data models and persistence`, push, and print the NEXT block.
