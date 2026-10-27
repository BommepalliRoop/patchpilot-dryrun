# T07 — Risk scorer

| Field | Value |
|---|---|
| Owner lane | Dev B |
| Model | Haiku 5.5 |
| Effort | low |
| Wave | 2 |
| Depends on | T00 |
| Unblocks | T03 |
| Branch | `t07-risk` |

## Goal
Pure function scoring.

## Scope
- `risk.score(cvss, reachability, evidence, kev, epss_percentile) -> (score, priority)` exactly per docs/ARCHITECTURE.md (includes `threat_w`).

## Acceptance criteria
- Table-driven tests for every priority boundary, plus KEV boost, EPSS ≥ 0.9 boost, `epss_percentile=None`, and not_reachable + KEV stays P4.

## Hardening (docs/RISKS.md)
Implement and test these rows: — (pure function; still reject cvss outside 0–10 with ValueError).

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T07: Risk scorer`, push, and print the NEXT block.
