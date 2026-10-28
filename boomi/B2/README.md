# B2: Finding notification → Supabase compliance log + Jira + Slack

Boomi process **PatchPilot B2 - Finding Notification** (`4d2e7436-862c-4605-8dc1-9b4d0c29b47b`). PatchPilot calls it once for every real finding, and it is idempotent on `finding_id`.

## Endpoint
`POST https://c01-sg.integrate.boomi.com/ws/simple/createPatchpilotfinding` (Basic auth, shared web server user). The body follows `contracts/boomi/B2_finding_request.json`.
Backend `.env`: `BOOMI_BASE_URL=https://c01-sg.integrate.boomi.com` and `BOOMI_B2_PATH=/ws/simple/createPatchpilotfinding`. This Atom tier serves only `/ws/simple/...` paths, not `/patchpilot/findings`.

It always answers HTTP 200 with JSON. The backend accepts `ok:false`.

| Case | Body |
|---|---|
| OK | `{"ok":true,"jira_key":"KAN-10","jira_url":"…/browse/KAN-10","slack_sent":true,"compliance_log_id":"log_fnd_07","processed_at":"…Z"}` |
| Missing field | `{"ok":false,"error":"invalid_request","message":"missing cve_id, …"}` |
| Jira failed | `{"ok":false,"error":"jira_create_failed","message":"Jira error: …"}`. The row stays with `jira_key` NULL, and a retry resumes. |
| DB failed | `{"ok":false,"error":"log_write_failed","message":"compliance log step failed: …"}` |

## Flow (docs/BOOMI_FLOW.md section 3)
Listener → validate → Try/Catch → Branch: (1) **Q1 lookup** by `finding_id`, (2) decide:
- **New** → Q2 insert row → Jira create → Q3 save key → Slack → Q4 save `slack_sent` → reply
- **Resume** (row exists, no Jira key) → Jira → Q3 → Slack → Q4 → reply
- **Status change** → Q5 update status, `fixed_at`, `pr_url` → Slack "updated" → Q4 → reply
- **Slack-only retry** (`slack_sent` false) → Slack → Q4 → reply
- **Pure retry** → reply with the stored values (no new Jira issue, no new Slack post)

Jira: project **KAN**, issue type **Task**, no priority field (team-managed project). The priority is in the summary and the labels. Labels: `patchpilot`, `security`, the client slug, `p1`…`p4`, `pp-<finding_id>`, and `actively-exploited` when the CVE is in CISA KEV.
Slack: Block Kit message to `#security-alerts` (title by fix status, client/CVE/package/where/exploit/Jira fields, PR and Jira links).

## Components (folder `DRYRUN - PatchPilot`)
| Component | ID |
|---|---|
| WSS op `PatchPilot_B2_Finding_Listener_Operation` | `666b421e-a582-474d-8d31-b42c16161267` |
| `PatchPilot_Jira_Connection` (REST, Basic, password set in GUI) | `e7e8ad95-b8f8-462d-b686-a26aedcbba4e` |
| `PatchPilot_Jira_CreateIssue_Operation` | `152f6077-6453-4e6c-bbee-6d46e6e1224d` |
| `PatchPilot_Slack_Connection` (webhook URL set in GUI) | `75b76870-ae10-4efc-a056-97fc74035c0c` |
| `PatchPilot_Slack_PostMessage_Operation` | `4d12ab17-eabd-4e58-8c58-1636362f60af` |
| `PatchPilot_Supabase_Connection` + Q1–Q5 operations | see `boomi/B4/README.md` |

The source is in the Boomi workspace: `scripts/gen_b2v3.py` and `scripts/b2v3_*.groovy`. Never push the Jira, Slack or Supabase connections from the workspace: a push wipes the secrets that were typed into the GUI.

## Known gaps
- No Jira **comment** on a status change (spec 3.4). Only the Slack "updated" alert and the Q5 row update happen.
- Q3–Q5 run their UPDATE SQL through a DB V2 **Standard Insert** operation, because Standard Update failed with `operation type is not supported:null`.
- The insert race (`Q2` affects 0 rows) is not handled. A second parallel call would also create a Jira issue.

## Test results (Oct 28, live)
`fnd_e2e_03`, in order:
1. New (`needs_human`) → `ok`, `KAN-10`, `slack_sent:true`, row inserted
2. Same call again → same `KAN-10`, no new issue
3. `fix_status: fixed` → `ok`, `KAN-10`, Slack "updated", row `status=fixed` and `fixed_at` set (checked via B4)
4. Bad request → `invalid_request`

`time_to_fix_minutes` showed -237 because the sample `detected_at` (05:10Z) is later than the test time.
