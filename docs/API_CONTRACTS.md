# API contracts (source of truth)

All JSON uses snake_case. Timestamps ISO-8601 UTC. Example files live in `contracts/`.

Enums
- scan.status: `queued | running | completed | failed`
- stage: `clone | scan | symbols | reachability | risk | fix | pr | notify | done`
- reachability: `reachable | not_reachable | unsure`
- priority: `P1 | P2 | P3 | P4`
- finding.status: `open | fixing | fixed | needs_human | ignored`
- B2 event: `finding.fixed | finding.needs_human | finding.open` (open = reachable but `auto_fix` was false)
- B2 fix_status: `fixed | fixed_untested | needs_human | not_attempted` (`fixed_untested` = upgrade PR opened, tests not run because the toolchain is missing)
- ecosystem (OSV names): `PyPI | npm | Maven | Go | crates.io | Packagist | NuGet | RubyGems` (others passed through as OSV names them)
- analysis: `deep` (Python AST + AI) | `generic` (text search + AI, all other languages)

---------------------------------------------------------------
## Part A — PatchPilot backend REST API (frontend ↔ backend, and Boomi B1 → backend)
Base URL: `${BACKEND_URL}` (local `http://localhost:8000`). Auth for machine callers: header `X-API-Key: ${PATCHPILOT_API_KEY}`.
Hardening rules for every endpoint: `docs/RISKS.md`.

### POST /api/scans  — start a scan
Request
```json
{ "client_name": "Acme Retail", "repo_url": "https://github.com/<org>/demo-target", "branch": "main", "auto_fix": true,
  "owner_email": "owner@easystepin.com" }
```
`owner_email` is optional (default empty); it is passed through to B2. `repo_url` must start with one of
`ALLOWED_REPO_PREFIXES`, else 400 `repo_not_allowed` (the engine installs and tests the repo's code).
Response 202
```json
{ "scan_id": "scn_01", "status": "queued" }
```
If a scan for the same `repo_url` + `branch` is already `queued`/`running`, the response is 202 with that scan's id and
status (no second scan). More than `MAX_SCANS_PER_HOUR` → 429 `rate_limited`. Invalid `branch` / non-https `repo_url` → 400 `invalid_request`.

### GET /api/scans  — list scans (newest first)
Response 200: `[Scan]`

### GET /api/scans/{scan_id}
Response 200 — Scan
```json
{
  "scan_id": "scn_01", "client_name": "Acme Retail", "repo_url": "...", "branch": "main",
  "status": "completed", "current_stage": "done",
  "started_at": "2026-10-28T05:10:00Z", "finished_at": "2026-10-28T05:11:42Z",
  "languages": [ { "ecosystem": "PyPI", "manifests": ["requirements.txt"], "analysis": "deep" },
                 { "ecosystem": "npm", "manifests": ["tools/package-lock.json"], "analysis": "generic" } ],
  "stats": { "total_alerts": 12, "reachable": 2, "unsure": 1, "not_reachable": 9, "p1": 1, "p2": 1, "fixed": 2, "prs_opened": 2 }
}
```

### GET /api/scans/{scan_id}/events  — Server-Sent Events
Each event `data:` is
```json
{ "scan_id": "scn_01", "stage": "reachability", "status": "running", "message": "Checking yaml.load in app/routes.py", "progress": 0.55, "data": {} }
```
Final event has `stage: "done"`.

### GET /api/findings?scan_id=scn_01&priority=P1&reachability=reachable
Response 200: `[FindingSummary]`
```json
[{ "finding_id": "fnd_07", "cve_id": "CVE-2020-14343", "package": "pyyaml", "installed_version": "5.3.1",
   "fixed_version": "5.4", "cvss": 9.8, "reachability": "reachable", "confidence": 0.93,
   "score": 10.0, "priority": "P1", "status": "fixed",
   "kev": false, "epss": 0.0598, "epss_percentile": 0.9326, "ecosystem": "PyPI", "analysis": "deep" }]
```

Threat fields: `kev` = CVE is on the CISA Known Exploited Vulnerabilities list (actively exploited);
`epss` = FIRST EPSS probability of exploitation in the next 30 days (0–1); `epss_percentile` (0–1).
`epss`/`epss_percentile` are `null` and `kev` is `false` when the feeds are unavailable or have no data.

`ecosystem` and `analysis` tell the UI which language a finding belongs to and how deep the reachability proof is.

### GET /api/findings/{finding_id}
Response 200 — FindingDetail = FindingSummary +
```json
{
  "summary": "Arbitrary code execution via full_load / FullLoader",
  "kev_date_added": null,
  "vulnerable_symbols": ["yaml.load", "yaml.full_load"],
  "evidence": [{ "file": "app/routes.py", "line": 42, "in_route": true,
                 "code_snippet": "...", "start_line": 27 }],
  "ai_explanation": "User-supplied YAML from POST /import reaches yaml.load without SafeLoader.",
  "fix": { "new_version": "5.4.1", "attempts": 1, "tests_passed": true,
           "patch_diff": "--- a/requirements.txt ...", "pr_url": "https://github.com/.../pull/3", "status": "fixed" },
  "integration": { "jira_key": "SEC-101", "jira_url": "https://...", "slack_sent": true, "compliance_log_id": "log_fnd_07" },
  "timeline": [{ "stage": "scan", "at": "2026-10-28T05:10:05Z", "message": "Detected via OSV" }]
}
```

### POST /api/findings/{finding_id}/fix  — run/re-run fix manually
Response 202 `{ "finding_id": "fnd_07", "status": "fixing" }`

### GET /api/integrations/activity?limit=50
Response 200: `[IntegrationEvent]`
```json
[{ "id": 1, "finding_id": "fnd_07", "process": "B2", "endpoint": "/patchpilot/findings",
   "status_code": 200, "ok": true, "summary": "Jira SEC-101 created, Slack sent", "created_at": "..." }]
```

### GET /api/compliance?client_name=Acme%20Retail&from=2026-10-01
Backend proxy of Boomi B4 (via `boomi_client.get_compliance`) for the Compliance page.
Response 200: same shape as `contracts/boomi/B4_compliance_response.json`. Mock mode returns that file.

### GET /api/health  → `{ "status": "ok", "llm_mode": "mock", "boomi_mode": "mock", "github_mode": "mock" }`
### POST /api/demo/reset  → clears DB and workdirs. Response `{ "ok": true }`
Requires `X-API-Key`; returns 404 unless `DEMO_MODE=true`.

Errors: `{ "error": { "code": "not_found", "message": "..." } }` with 400/401/404/409/429/500.
Codes: `invalid_request` (400), `repo_not_allowed` (400), `unauthorized` (401), `not_found` (404), `conflict` (409),
`rate_limited` (429), `internal_error` (500). Messages never contain stack traces or secrets.

---------------------------------------------------------------
## Part B — Boomi processes (built by the Boomi team with Boomi Companion)
Base URL for Boomi-hosted endpoints: `${BOOMI_BASE_URL}` (the Boomi team shares it).
Auth to Boomi: HTTP Basic (`BOOMI_USER` / `BOOMI_TOKEN`) unless the Boomi team agrees otherwise.
Timeout on our side: 15 s. Our client retries once on 5xx or timeout.
Every B2/B3 call carries header `Idempotency-Key: <finding_id>` (B3: `<scan_id>`). Boomi must treat a repeated key as the
same request: return the earlier result (same `jira_key`) instead of creating a second Jira issue / Slack post.
The same key with a **different** `fix_status` (e.g. after `POST /api/findings/{id}/fix`) is a status update: Boomi updates
the compliance row and comments on the existing Jira issue. Step-by-step Boomi flow: `docs/BOOMI_FLOW.md`.

### B1 — Scheduled scan trigger (Boomi → PatchPilot)
Boomi schedule (daily 9:00 AM; on demo day also a manual "Run now"). For each client repo in its config list
it calls `POST ${BACKEND_URL}/api/scans` with header `X-API-Key` and body as in Part A.
Expected response 202 `{ "scan_id": "...", "status": "queued" }`. Boomi logs the scan_id.

### B2 — Finding notification (PatchPilot → Boomi) — the main one
`POST ${BOOMI_BASE_URL}/patchpilot/findings`
Request: `contracts/boomi/B2_finding_request.json`
Boomi does: Decision on priority (P1/P2 urgent path) → Jira create issue → Slack message → compliance log write.
Response 200: `contracts/boomi/B2_finding_response.json`
```json
{ "ok": true, "jira_key": "SEC-101", "jira_url": "https://<site>.atlassian.net/browse/SEC-101",
  "slack_sent": true, "compliance_log_id": "log_fnd_07", "processed_at": "2026-10-28T05:11:40Z" }
```
Error response (4xx/5xx): `{ "ok": false, "error": "jira_create_failed", "message": "..." }`

### B3 — Scan summary (PatchPilot → Boomi)
`POST ${BOOMI_BASE_URL}/patchpilot/scan-summary`
Request: `contracts/boomi/B3_scan_summary_request.json`. Boomi posts one Slack summary message to the security channel.
Response 200: `{ "ok": true, "slack_sent": true }`

### B4 — Compliance report (PatchPilot → Boomi)
`GET ${BOOMI_BASE_URL}/patchpilot/compliance?client_name=Acme%20Retail&from=2026-10-01`
Response 200: `contracts/boomi/B4_compliance_response.json`
