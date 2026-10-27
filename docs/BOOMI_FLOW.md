# Boomi end-to-end flow — B0 to B4, step by step (low level)

Companion to `docs/BOOMI_HANDOFF.md`. The handoff says **what** to build; this file says **exactly what happens,
in which order, with which call, payload, response and database statement**. Example values follow one demo run:
client `Acme Retail`, scan `scn_01`, finding `fnd_07` (PyYAML, CVE-2020-14343, P1).

Systems involved:

| System | Who owns it | Used by | How Boomi reaches it |
|---|---|---|---|
| PatchPilot backend (FastAPI) | Dev team | B1 calls it; it calls B2, B3, B4 | HTTPS, header `X-API-Key` |
| Jira Cloud | Lead / Boomi team | B2 | REST API v2, Basic auth (email + API token) |
| Slack | Lead / Boomi team | B2, B3 | HTTPS POST to the channel webhook URL |
| Supabase PostgreSQL (`public.compliance_log`) | Lead created it | B2 (write), B4 (read) | Boomi Database connector, JDBC, Session pooler |
| PatchPilot app database (SQLite) | Dev team | Backend only | **Never** touched by Boomi |

---

## 0. Database map — where the compliance table is created, written and read

| # | When | Process / step | Statement | Effect on `compliance_log` |
|---|---|---|---|---|
| D1 | Once, before the event | Lead, Supabase SQL Editor | `CREATE TABLE` + `CREATE INDEX` + `ENABLE ROW LEVEL SECURITY` | Table exists, empty (**done Oct 27**) |
| D2 | Once, before the event | Lead, Supabase SQL Editor | `ALTER TABLE … ADD COLUMN ecosystem, updated_at` | Two extra columns (M1 in section 6) (**done Oct 27**, Q1–Q6 tested; `teams_sent` renamed `slack_sent`) |
| D3 | B0 step 0.6 | Boomi connection test | `SELECT count(*)` | Read only — proves the connection |
| D4 | B2 step 2.3 | Every finding call | **Q1 SELECT** by `finding_id` | Read only — "have we seen this finding?" |
| D5 | B2 step 2.5 | New finding | **Q2 INSERT** (reserve the row, no Jira yet) | New row, `jira_key` NULL, `slack_sent` false |
| D6 | B2 step 2.7 | After Jira created | **Q3 UPDATE** `jira_key`, `jira_url` | Row now linked to the Jira issue |
| D7 | B2 step 2.9 | After Slack post | **Q4 UPDATE** `slack_sent` | Row records whether Slack got it |
| D8 | B2 step 2.4c | Same finding, new status (e.g. fixed later) | **Q5 UPDATE** `status`, `fixed_at`, `pr_url` | Row moves to the new status |
| D9 | B4 step 4.3 | Compliance page / audit | **Q6 SELECT** report | Read only |

B1 and B3 never touch the database. The backend never touches Supabase.

Status mapping used everywhere (B2 `fix_status` → table `status`):

| B2 `fix_status` | `compliance_log.status` | `fixed_at` |
|---|---|---|
| `fixed` | `fixed` | time Boomi processed it |
| `fixed_untested` | `needs_human` | NULL |
| `needs_human` | `needs_human` | NULL |
| `not_attempted` | `open` | NULL |

---

## 1. B0 — Setup (once, at the start of the sprint)

| Step | What to do | Detail | Done when |
|---|---|---|---|
| 0.1 | Pick the runtime | Boomi **Atom Cloud** (public HTTPS). A laptop Atom is not reachable by our backend | Atom shows "online" |
| 0.2 | Shared Web Server | API type **REST**, authentication **Basic**; User Management → add user `patchpilot` → copy the generated token | You have user + token |
| 0.3 | Note the base URL | Usually `https://<atom-cloud-host>/ws/rest` → `BOOMI_BASE_URL` | URL known |
| 0.4 | Connection: Jira | Jira connector, or HTTP Client with base `https://<site>.atlassian.net`, Basic auth = Jira email + **API token** (id.atlassian.com → Security → API tokens) | Test call `GET /rest/api/2/myself` → 200 |
| 0.5 | Connection: Slack | HTTP Client, URL = Slack **incoming webhook** (api.slack.com/apps → Create New App → From scratch → Incoming Webhooks → On → Add New Webhook → pick the channel, e.g. `#security-alerts`) | `POST {"text":"PatchPilot test"}` → `200 ok`, message appears in the channel |
| 0.6 | Connection: Supabase | Database connector, driver **PostgreSQL**, JDBC URL `jdbc:postgresql://aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require`, user `postgres.eyaujwqdizcselugymkn`, password from the Lead (private) | `SELECT count(*) FROM public.compliance_log` → `0` (**D3**) |
| 0.7 | Connection: PatchPilot | HTTP Client, base `BACKEND_URL` (from the Lead after deploy), header `X-API-Key: <PATCHPILOT_API_KEY>` | Set later; use webhook.site until then |
| 0.8 | Hand over | Send the Lead: base URL + exact paths (team chat), user (team chat), token (**private**) | Lead switches `BOOMI_MODE=live` |

If 0.6 fails (driver not available on the Atom): tell the Lead immediately → fallback Google Sheet with the same columns.

---

## 2. B1 — Daily start (Boomi → PatchPilot)

**Purpose:** every morning, ask PatchPilot to scan every client repo. Boomi only **starts** the scan; PatchPilot does the work.

| Step | Boomi shape | What happens | Data |
|---|---|---|---|
| 1.1 | **Start shape: Schedule** | Runs daily **09:00 IST** (check the Atom time zone). Demo: run manually with "Execute" | — |
| 1.2 | Message shape | Loads the client list (JSON array). Later version: fetch it from the backend instead | see 1.2 payload |
| 1.3 | Data Process → Split Documents | One document per client | one JSON object each |
| 1.4 | Connector: HTTP Client (PatchPilot), operation POST | `POST {BACKEND_URL}/api/scans` | request below |
| 1.5 | Decision on HTTP status | 202 → 1.6 · 400/401/429 → 1.7 · timeout/5xx → retry once after 30 s, then 1.7 | — |
| 1.6 | Notify / process log | Log `scan_id` and client name | `scn_01` |
| 1.7 | Notify / process log (error) | Log status + `error.code` + client; continue with the next client (never stop the whole run) | — |

1.2 client list:
```json
[ { "client_name": "Acme Retail", "repo_url": "https://github.com/BommepalliRoop/demo-target",
    "branch": "main", "auto_fix": true, "owner_email": "owner@easystepin.com" } ]
```

1.4 request:
```http
POST https://<BACKEND_URL>/api/scans
X-API-Key: <PATCHPILOT_API_KEY>
Content-Type: application/json

{ "client_name": "Acme Retail", "repo_url": "https://github.com/BommepalliRoop/demo-target",
  "branch": "main", "auto_fix": true, "owner_email": "owner@easystepin.com" }
```

1.5 responses:
```json
202 { "scan_id": "scn_01", "status": "queued" }
400 { "error": { "code": "repo_not_allowed", "message": "repo_url is not on the allowed list" } }
401 { "error": { "code": "unauthorized", "message": "missing or wrong X-API-Key" } }
429 { "error": { "code": "rate_limited", "message": "too many scans this hour" } }
```
Database: **none**. Other systems: **none**.

### Between B1 and B2 — what PatchPilot does (dev team, for context only)
After the 202, the backend runs: clone → detect languages → OSV scan → exploit data (CISA KEV, EPSS) → AI symbols →
reachability → risk score → fix + tests → GitHub PR. This takes about 1–2 minutes. Then, for **each real finding**
(reachable, or unsure with confidence ≥ 0.5) it calls **B2**, and at the very end it calls **B3** once.
The backend stores everything in its own SQLite database; nothing here touches Supabase.

---

## 3. B2 — New finding → Jira + Slack + audit log (the main one)

**Trigger:** PatchPilot calls B2 once per real finding. It may call again for the same finding (a retry after a timeout,
or a later status change such as `needs_human` → `fixed` after a manual re-fix).

### 3.1 Request (PatchPilot → Boomi)
```http
POST https://<BOOMI_BASE_URL>/patchpilot/findings
Authorization: Basic base64(BOOMI_USER:BOOMI_TOKEN)
Idempotency-Key: fnd_07
Content-Type: application/json
```
```json
{
  "event": "finding.fixed", "scan_id": "scn_01", "finding_id": "fnd_07",
  "client_name": "Acme Retail", "repo_url": "https://github.com/BommepalliRoop/demo-target",
  "cve_id": "CVE-2020-14343", "package": "pyyaml", "ecosystem": "PyPI",
  "installed_version": "5.3.1", "fixed_version": "6.0.1", "cvss": 9.8, "priority": "P1", "score": 10.0,
  "kev": false, "epss": 0.0598, "epss_percentile": 0.9326,
  "reachability": "reachable", "confidence": 0.93,
  "summary": "Arbitrary code execution via full_load / FullLoader",
  "ai_explanation": "User-supplied YAML from POST /import reaches yaml.load without SafeLoader.",
  "evidence": [ { "file": "app/routes.py", "line": 42, "in_route": true } ],
  "fix_status": "fixed", "tests_passed": true,
  "pr_url": "https://github.com/BommepalliRoop/demo-target/pull/3",
  "owner_email": "owner@easystepin.com", "detected_at": "2026-10-28T05:10:05Z"
}
```

### 3.2 Steps

| Step | Boomi shape | What happens | DB | Next |
|---|---|---|---|---|
| 2.1 | **Start: Web Services Server listener**, POST `/patchpilot/findings`, profile = JSON above | Receives the call. Store header `Idempotency-Key` and `finding_id` in process properties | — | 2.2 |
| 2.2 | Decision (validate) | Required: `finding_id`, `cve_id`, `package`, `priority`, `client_name`, `fix_status`, `detected_at`. Missing → **reply 400** and stop | — | 2.3 |
| 2.3 | Database connector, Get | **Q1** lookup by `finding_id` | **SELECT (D4)** | 2.4 |
| 2.4 | Decision on Q1 result | a) no row → **2.5** (new finding) · b) row with `jira_key` NULL → **2.6** (earlier call failed half-way, resume) · c) row with `jira_key` set and a different status → **2.4c** · d) row with `jira_key` set and same status → **2.4d** (pure retry) | — | — |
| 2.4c | Database connector, Update | **Q5** set new status / `fixed_at` / `pr_url`; then Jira **add comment** (3.4) "Status changed: needs_human → fixed. PR: …"; then **2.8** (Slack message "updated") | **UPDATE (D8)** | 2.8 |
| 2.4d | — | Nothing new to create. If `slack_sent` is false, go to **2.8** to retry Slack; otherwise go to **2.10** with the stored values | — | 2.8 / 2.10 |
| 2.5 | Database connector, Insert | **Q2** reserve the row (status mapped, `jira_key` NULL). If it returns no row, another call inserted it first → back to **2.3** | **INSERT (D5)** | 2.6 |
| 2.6 | Decision on `priority` | P1/P2 → Jira priority Highest/High, Slack message style "attention"; P3/P4 → Medium/Low, style "default" | — | 2.7 |
| 2.7 | HTTP Client / Jira connector | **Create Jira issue** (3.3). Success → **Q3** save key + URL. Failure → **reply 502** `jira_create_failed` and stop (row stays with `jira_key` NULL; our retry resumes at 2.6) | **UPDATE (D6)** | 2.8 |
| 2.8 | HTTP Client (Slack) | **Post the Slack message** (3.5). Any 2xx = sent. Failure = not sent (do **not** stop) | — | 2.9 |
| 2.9 | Database connector, Update | **Q4** save `slack_sent` true/false | **UPDATE (D7)** | 2.10 |
| 2.10 | Map → Return Documents | **Reply 200** (3.6) with `jira_key`, `jira_url`, `slack_sent`, `compliance_log_id`, `processed_at` | — | end |

Must answer within **15 seconds** (our timeout). Typical: Q1 50 ms + Q2 50 ms + Jira 1–2 s + Q3 50 ms + Slack 0.5–1 s + Q4 50 ms ≈ 3 s.

### 3.3 Jira — create issue (step 2.7)
```http
POST https://<site>.atlassian.net/rest/api/2/issue
Authorization: Basic base64(<jira-email>:<jira-api-token>)
Content-Type: application/json
```
```json
{ "fields": {
    "project":   { "key": "SEC" },
    "issuetype": { "name": "Bug" },
    "summary":   "[P1] CVE-2020-14343 in pyyaml (PyPI) — Acme Retail",
    "priority":  { "name": "Highest" },
    "labels":    [ "patchpilot", "security", "acme-retail" ],
    "description": "Arbitrary code execution via full_load / FullLoader\n\nWhy it matters: User-supplied YAML from POST /import reaches yaml.load without SafeLoader.\nEvidence: app/routes.py:42 (in web route)\nUpgrade: pyyaml 5.3.1 -> 6.0.1\nFix status: fixed, tests passed\nPull request: https://github.com/BommepalliRoop/demo-target/pull/3\nExploit data: CISA KEV = no · EPSS 6% (top 7%)\nRisk score: 10.0 (CVSS 9.8)\nPatchPilot finding: fnd_07 · scan scn_01"
} }
```
Response `201 { "id": "10042", "key": "SEC-101", "self": "https://<site>.atlassian.net/rest/api/2/issue/10042" }`
→ `jira_url = https://<site>.atlassian.net/browse/SEC-101`.
Add label `actively-exploited` when `kev` is true. If Jira answers 400 "Field 'priority' cannot be set" (some
team-managed projects hide it), resend without `priority`.

### 3.4 Jira — add comment (step 2.4c, status change only)
```http
POST https://<site>.atlassian.net/rest/api/2/issue/SEC-101/comment
{ "body": "PatchPilot update: status needs_human -> fixed. Pull request: https://github.com/.../pull/3" }
```
Response `201`.

### 3.5 Slack — post message (step 2.8)
```http
POST <SLACK_WEBHOOK_URL>          (https://hooks.slack.com/services/T…/B…/…  — secret)
Content-Type: application/json
```
```json
{ "text": "P1 vulnerability fixed automatically: CVE-2020-14343 in pyyaml (Acme Retail)",
  "blocks": [
    { "type": "header", "text": { "type": "plain_text", "text": "P1 vulnerability fixed automatically" } },
    { "type": "section", "fields": [
      { "type": "mrkdwn", "text": "*Client*\nAcme Retail" },
      { "type": "mrkdwn", "text": "*CVE*\nCVE-2020-14343" },
      { "type": "mrkdwn", "text": "*Package*\npyyaml (PyPI) 5.3.1 → 6.0.1" },
      { "type": "mrkdwn", "text": "*Where*\napp/routes.py:42 (web route)" },
      { "type": "mrkdwn", "text": "*Exploit data*\nEPSS 6% · top 7%" },
      { "type": "mrkdwn", "text": "*Jira*\nSEC-101" } ] },
    { "type": "section", "text": { "type": "mrkdwn", "text": "User-supplied YAML from POST /import reaches yaml.load without SafeLoader." } },
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "<https://github.com/BommepalliRoop/demo-target/pull/3|Open pull request>  ·  <https://<site>.atlassian.net/browse/SEC-101|Open Jira>" } } ] }
```
Response: `200` with body `ok` → `slack_sent = true`. Errors (`slack_sent = false`, flow continues): `400 invalid_payload` /
`no_text` (bad JSON), `403 action_prohibited`, `404 channel_not_found` / `no_service` (webhook removed),
`410 channel_is_archived`. Links are plain `<url|text>` links (no interactive buttons, so no Slack app backend is needed).
Title by case: `fixed` "… fixed automatically" · `fixed_untested` "… upgrade PR ready — please run tests" ·
`needs_human` "… needs review" · `not_attempted` "… found (auto-fix off)" · status change "… updated". Leave out the
pull-request link when `pr_url` is empty. Add "🔥 Actively exploited (CISA KEV)" to Exploit data when `kev` is true.

### 3.6 Reply to PatchPilot (step 2.10)
```json
200 { "ok": true, "jira_key": "SEC-101", "jira_url": "https://<site>.atlassian.net/browse/SEC-101",
      "slack_sent": true, "compliance_log_id": "log_fnd_07", "processed_at": "2026-10-28T05:11:40Z" }
400 { "ok": false, "error": "invalid_request", "message": "missing cve_id" }
401 { "ok": false, "error": "unauthorized", "message": "bad credentials" }
502 { "ok": false, "error": "jira_create_failed", "message": "Jira returned 400: ..." }
500 { "ok": false, "error": "log_write_failed", "message": "compliance log insert failed" }
```

---

## 4. B3 — Scan summary → Slack message

**Trigger:** PatchPilot calls B3 once at the end of every scan.

| Step | Boomi shape | What happens | DB |
|---|---|---|---|
| 3.1 | **Start: Web Services Server listener**, POST `/patchpilot/scan-summary` | Receives the summary (`Idempotency-Key: scn_01`) | — |
| 3.2 | Decision (validate) | Required: `scan_id`, `client_name`, `stats`. Missing → reply 400 | — |
| 3.3 | Map | Build the summary message (Block Kit) | — |
| 3.4 | HTTP Client (Slack) | Post the message; `200 ok` = sent | — |
| 3.5 | Return Documents | Reply 200 | — |

Request:
```json
POST /patchpilot/scan-summary   (Basic auth, Idempotency-Key: scn_01)
{ "event": "scan.completed", "scan_id": "scn_01", "client_name": "Acme Retail",
  "repo_url": "https://github.com/BommepalliRoop/demo-target", "finished_at": "2026-10-28T05:11:42Z",
  "stats": { "total_alerts": 35, "reachable": 3, "unsure": 1, "not_reachable": 31, "p1": 1, "p2": 1, "fixed": 2, "prs_opened": 2 },
  "dashboard_url": "https://patchpilot.vercel.app/scans/scn_01" }
```
Slack message: header "PatchPilot daily scan — Acme Retail"; fields Total alerts 35 · Real risks 3 · P1 1 · P2 1 · Fixed 2 ·
PRs opened 2; link `<dashboard_url|Open dashboard>`. Same webhook and response rules as 3.5.
Responses: `200 { "ok": true, "slack_sent": true }` · Slack failed → `200 { "ok": true, "slack_sent": false }` · `400` · `401`.
Database: **none**. A duplicate summary message on a retry is harmless.

---

## 5. B4 — Compliance report (audit)

**Trigger:** someone opens the Compliance page in the React app → React calls our backend `GET /api/compliance` →
the backend calls B4 → B4 reads Supabase.

| Step | Boomi shape | What happens | DB |
|---|---|---|---|
| 4.1 | **Start: Web Services Server listener**, GET `/patchpilot/compliance` | Reads query parameters `client_name`, `from` | — |
| 4.2 | Decision (validate) | `client_name` present, `from` is `YYYY-MM-DD` → else reply 400 | — |
| 4.3 | Database connector, Get | **Q6** report query | **SELECT (D9)** |
| 4.4 | Map → Return Documents | Build `{ client_name, from, items: [...] }` (empty list if no rows) | — |

Request: `GET /patchpilot/compliance?client_name=Acme%20Retail&from=2026-10-01` (Basic auth, no body).
Response:
```json
200 { "client_name": "Acme Retail", "from": "2026-10-01",
      "items": [ { "compliance_log_id": "log_fnd_07", "cve_id": "CVE-2020-14343", "package": "pyyaml", "priority": "P1",
                   "detected_at": "2026-10-28T05:10:05Z", "fixed_at": "2026-10-28T05:11:40Z", "time_to_fix_minutes": 2,
                   "jira_key": "SEC-101", "pr_url": "https://github.com/BommepalliRoop/demo-target/pull/3", "status": "fixed" } ] }
400 { "ok": false, "error": "invalid_request", "message": "from must be YYYY-MM-DD" }
```

---

## 6. All SQL in one place (Supabase, `public.compliance_log`)

**M1 — migration, run once by the Lead (D2)**
```sql
ALTER TABLE public.compliance_log
  ADD COLUMN IF NOT EXISTS ecosystem  TEXT,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
```

**Q1 — B2 lookup (D4)** · params: finding_id
```sql
SELECT compliance_log_id, status, jira_key, jira_url, slack_sent
FROM public.compliance_log WHERE finding_id = ?;
```

**Q2 — B2 reserve new row (D5)** · params: compliance_log_id ('log_' + finding_id), finding_id, scan_id, client_name,
repo_url, cve_id, package, ecosystem, priority, kev, detected_at, fixed_at (or NULL), pr_url (or NULL), status (mapped)
```sql
INSERT INTO public.compliance_log
  (compliance_log_id, finding_id, scan_id, client_name, repo_url, cve_id, package, ecosystem,
   priority, kev, detected_at, fixed_at, pr_url, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz, ?, ?)
ON CONFLICT (finding_id) DO NOTHING
RETURNING compliance_log_id;
```

**Q3 — B2 save Jira (D6)** · params: jira_key, jira_url, finding_id
```sql
UPDATE public.compliance_log SET jira_key = ?, jira_url = ?, updated_at = now() WHERE finding_id = ?;
```

**Q4 — B2 save Slack result (D7)** · params: slack_sent, finding_id
```sql
UPDATE public.compliance_log SET slack_sent = ?, updated_at = now() WHERE finding_id = ?;
```

**Q5 — B2 status change (D8)** · params: new status, fixed_at (or NULL), pr_url (or empty), finding_id, new status
```sql
UPDATE public.compliance_log
SET status = ?, fixed_at = COALESCE(fixed_at, ?::timestamptz), pr_url = COALESCE(NULLIF(?, ''), pr_url), updated_at = now()
WHERE finding_id = ? AND status <> ?
RETURNING compliance_log_id;
```

**Q6 — B4 report (D9)** · params: client_name, from
```sql
SELECT compliance_log_id, cve_id, package, priority, detected_at, fixed_at,
       CASE WHEN fixed_at IS NULL THEN NULL
            ELSE FLOOR(EXTRACT(EPOCH FROM (fixed_at - detected_at)) / 60)::int END AS time_to_fix_minutes,
       jira_key, pr_url, status
FROM public.compliance_log
WHERE client_name = ? AND detected_at >= ?::date
ORDER BY detected_at DESC;
```

In Boomi: Q1 and Q6 = Database connector **Get** operations with parameters; Q2–Q5 = **Send** operations
(standard update / prepared statement with parameters). Bind every value as a parameter — never build SQL by
joining strings (SQL injection).

---

## 7. One full run — how the row changes

| Time | Event | Row `log_fnd_07` after the step |
|---|---|---|
| 09:00:00 | B1 Schedule → `POST /api/scans` → 202 `scn_01` | (no row) |
| 09:00–09:01:40 | PatchPilot scans, fixes, opens PR #3 | (no row) |
| 09:01:40.0 | B2 called (`fnd_07`, `fix_status: fixed`) → Q1 finds nothing | (no row) |
| 09:01:40.1 | Q2 insert | status `fixed`, fixed_at 09:01:40, jira_key NULL, slack_sent false |
| 09:01:41.5 | Jira 201 `SEC-101` → Q3 | jira_key `SEC-101`, jira_url set |
| 09:01:42.2 | Slack 202 → Q4 | slack_sent true |
| 09:01:42.3 | Reply 200 to PatchPilot | (unchanged) |
| 09:01:43 | B3 summary message posted in Slack | (unchanged) |
| any time | Compliance page → B4 → Q6 | read: time_to_fix_minutes 2 |

Failure examples:
- Jira down at 09:01:41 → row stays with `jira_key` NULL, reply 502 → PatchPilot retries once → Q1 finds the row with
  `jira_key` NULL → resumes at Jira → one issue only.
- Reply lost (network) after success → PatchPilot retries with the same `Idempotency-Key` → Q1 finds the row with
  `jira_key` set and same status → reply the stored values → no duplicate Jira or Slack post.
- Next day the same finding is still open and the backend sends `needs_human` → Q1 finds a different status → Q5 updates
  the row, Jira gets a comment, Slack gets an "updated" message → still one Jira issue.

---

## 8. Error and retry rules (summary)

| Where | Problem | What Boomi does | What PatchPilot sees |
|---|---|---|---|
| B1 → backend | 401 / 400 / 429 | Log, continue with next client | — |
| B1 → backend | timeout / 5xx | Retry once after 30 s, then log | — |
| B2 validation | missing field | Reply 400 | Logged as failed integration event |
| B2 Jira | 4xx/5xx | Reply 502, row keeps `jira_key` NULL | Retries once → B2 resumes |
| B2 Slack | any failure | Continue, `slack_sent` false, reply 200 | Shows "Slack not sent" |
| B2 database | Q2/Q3/Q4 error | Reply 500 `log_write_failed` | Retries once |
| B3 Slack | failure | Reply 200 `slack_sent:false` | Shows in activity feed |
| B4 database | error | Reply 500 | Compliance page shows an error with Retry |
| Any listener | wrong user/token | 401 | Lead checks `BOOMI_USER` / `BOOMI_TOKEN` |
