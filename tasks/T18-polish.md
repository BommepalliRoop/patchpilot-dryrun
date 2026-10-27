# T18 — Polish and rehearsal

| Field | Value |
|---|---|
| Owner lane | Everyone |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 4 |
| Depends on | T17 |
| Unblocks | — |
| Branch | `t18-polish` |

## Goal
Last 15 minutes before code freeze.

## Scope
- Fix visual glitches, loading states, copy text; check dark contrast; final README screenshots.
- Freeze at 12:20. No new features after 12:10.

## Acceptance criteria
- Two clean rehearsals of docs/DEMO_SCRIPT.md.

## Hardening (docs/RISKS.md)
Implement and test these rows: O4 (pitch answer on safety).

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T18: Polish and rehearsal`, push, and print the NEXT block.
