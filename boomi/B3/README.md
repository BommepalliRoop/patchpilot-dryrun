# B3 — Scan summary → Slack

PatchPilot calls B3 once at the end of each scan. Boomi validates the summary, posts a Slack Block Kit message
(header `PatchPilot daily scan — <client_name>`; fields Total alerts, Real risks = reachable + unsure, P1, P2, Fixed,
PRs opened; `<dashboard_url|Open dashboard>` link when present) and replies. Always HTTP 200 with an `ok` flag.

## Endpoint
`POST https://c01-sg.integrate.boomi.com/ws/simple/createPatchpilotscansummary` (Basic auth, `Content-Type: application/json`)

## Request / response
Request: `contracts/boomi/B3_scan_summary_request.json` (required: `scan_id`, `client_name`, `stats`).

| Case | Response (HTTP 200) |
|---|---|
| Slack accepted (body `ok`) | `{"ok":true,"slack_sent":true}` |
| Slack failed | `{"ok":true,"slack_sent":false}` |
| Missing fields / bad JSON | `{"ok":false,"error":"invalid_request","message":"missing client_name, stats"}` |

## Components (folder `DRYRUN - PatchPilot`, `Rjo4OTMyNDgz`)
| Component | ID |
|---|---|
| Process `PatchPilot B3 - Scan Summary` | `621351f0-77e8-41fe-8a82-e6cb82053bd7` |
| WSS listener op `PatchPilot_B3_ScanSummary_Listener_Operation` (CREATE, `patchpilotscansummary`) | `cf751cf6-b552-4153-8db1-bb708c7bb74c` |
| Slack connection `PatchPilot_Slack_Connection` (shared with B2) | `75b76870-ae10-4efc-a056-97fc74035c0c` |
| Slack operation `PatchPilot_Slack_PostMessage_Operation` (shared with B2) | `4d12ab17-eabd-4e58-8c58-1636362f60af` |

Flow: listener → Groovy validate + build message → Decision `DDP_VALID` → Slack POST → Groovy reply → Return Documents
(invalid → Return Documents). Source in the Boomi workspace: `scripts/gen_b3.py`, `scripts/b3_build_slack.groovy`,
`scripts/b3_build_reply.groovy`, `active-development/process/PatchPilot_B3_Scan_Summary.xml`.

## Test results (2026-10-28, deployed package version 1)
- `{"scan_id":"scn_x"}` → HTTP 200 `{"ok":false,"error":"invalid_request","message":"missing client_name, stats"}`
- sample request → HTTP 200 `{"ok":true,"slack_sent":false}` (expected: the Slack connection's Base URL is still the
  placeholder; paste the webhook URL in the Boomi GUI and redeploy, then this returns `slack_sent: true`).
