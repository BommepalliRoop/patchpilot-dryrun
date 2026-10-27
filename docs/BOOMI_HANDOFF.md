# Boomi team handoff

You own all Boomi work. Build with Boomi Companion. The dev team never edits your processes;
we only agree on the contracts in `docs/API_CONTRACTS.md` Part B and the JSON files in `contracts/boomi/`.

## What you build
| ID | Process | Direction | Trigger | Steps |
|---|---|---|---|---|
| B1 | Scheduled scan trigger | Boomi → PatchPilot | Schedule daily 9:00 + manual run | Read client repo list (static JSON or DB) → for each, HTTP POST `${BACKEND_URL}/api/scans` with `X-API-Key` → log scan_id |
| B2 | Finding notification | PatchPilot → Boomi | Web Services listener `POST /patchpilot/findings` | Validate → Decision on `priority` (P1/P2 urgent) → Jira: create issue → Teams: post message (incoming webhook) → write compliance log row → return response JSON |
| B3 | Scan summary | PatchPilot → Boomi | Listener `POST /patchpilot/scan-summary` | Map stats → Teams summary card → return `{ok, teams_sent}` |
| B4 | Compliance report | PatchPilot → Boomi | Listener `GET /patchpilot/compliance` | Query compliance log by client/date → return items JSON |

Priority order if time is short: B2 → B1 → B3 → B4.

## Jira mapping (B2)
| Jira field | From payload |
|---|---|
| Project | `SEC` (or your project key) |
| Issue type | Bug (or Task) |
| Summary | `[{priority}] {cve_id} in {package} — {client_name}` |
| Priority | P1→Highest, P2→High, P3→Medium, P4→Low |
| Description | summary, ai_explanation, evidence file:line, fix_status, tests_passed, pr_url |
| Labels | `patchpilot`, `security`, client name slug |

## Teams message (B2)
Title: `{priority} vulnerability fixed automatically` (or `needs review` if `fix_status` = `needs_human`).
Body: client, repo, CVE, package `installed → fixed`, why reachable (ai_explanation), buttons/links to PR and Jira.

## Compliance log row
compliance_log_id, client_name, repo_url, cve_id, package, priority, detected_at, fixed_at, jira_key, pr_url, status.
Use a Boomi-connected database, SharePoint list, or a Google/Excel sheet — whichever is fastest for you.

## Response rules
- Always return JSON with `ok`. Success 200 with fields from `contracts/boomi/B2_finding_response.json`.
- Failure: 4xx/5xx with `{ "ok": false, "error": "<code>", "message": "..." }`.
- Respond within 15 seconds.

## What we need from you, and when
| Item | When |
|---|---|
| `BOOMI_BASE_URL`, auth user/token | by 10:30 on the day |
| B2 working against the sample request (Postman/curl) | by 11:15 |
| B1 schedule pointing at our `BACKEND_URL` | by 11:40 (we give you the URL after T16) |

Until then the dev team runs with `BOOMI_MODE=mock`, so nobody is blocked.

## Test call
```bash
curl -u "$BOOMI_USER:$BOOMI_TOKEN" -H "Content-Type: application/json" \
  -d @contracts/boomi/B2_finding_request.json "$BOOMI_BASE_URL/patchpilot/findings"
```

## Prompt idea for Boomi Companion (B2)
"Create a process with a Web Services Server listener for POST /patchpilot/findings that accepts this JSON
[paste B2_finding_request.json]. Add a Decision on priority: P1 or P2 go to an urgent branch. Create a Jira issue
using this mapping [paste table]. Post a message to a Microsoft Teams incoming webhook with the CVE, package,
explanation and links to pr_url and the new Jira issue. Insert a row into the compliance log. Return this JSON
[paste B2_finding_response.json]."
