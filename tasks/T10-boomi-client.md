# T10 — Boomi client (mock + live)

| Field | Value |
|---|---|
| Owner lane | Dev C |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 1 |
| Depends on | T00 (T01 for event logging) |
| Unblocks | T03, T17 |
| Branch | `t10-boomi-client` |

## Goal
Call Boomi processes B2/B3/B4 exactly per contract.

## Scope
- `boomi_client.notify_finding(payload) -> B2Response`, `send_scan_summary(payload)`, `get_compliance(client, from)`.
- Builds payloads from DB objects to match `contracts/boomi/*.json` exactly (B2 includes `kev`, `epss`, `epss_percentile`); Basic auth; paths from BOOMI_B2_PATH / BOOMI_B3_PATH / BOOMI_B4_PATH (default to the contract paths); 15 s timeout; retry once on 5xx; logs every call to integration_events.
- `BOOMI_MODE=mock`: returns contract example responses with generated jira keys (`SEC-1xx`).
- Tiny CLI: `python -m app.services.boomi_client ping` sends the sample B2 request to the live URL (for the Boomi team to test).

- B2 payload also carries `ecosystem`; `fix_status` may be `fixed_untested`.

- After a manual re-fix (`POST /api/findings/{id}/fix`) send B2 again with the **same** `Idempotency-Key` (= `finding_id`) and the new `fix_status`; Boomi treats it as a status update (docs/BOOMI_FLOW.md section 3).

## Acceptance criteria
- Pydantic validation test: generated payload == contract keys.
- Mock and live paths both covered (live behind an env flag).

## Hardening (docs/RISKS.md)
Implement and test these rows: N5 (`Idempotency-Key` header), N6, S4.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T10: Boomi client (mock + live)`, push, and print the NEXT block.
