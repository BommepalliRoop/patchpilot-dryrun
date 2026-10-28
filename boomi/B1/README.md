# B1 — Daily scan trigger (Boomi → PatchPilot)

Every morning Boomi asks the PatchPilot backend to scan each client repo: one `POST {BACKEND_URL}/api/scans` per
client, then logs the `scan_id` (202) or the error. One failing client never stops the run. Spec: `docs/BOOMI_FLOW.md`
section 2, `docs/BOOMI_HANDOFF.md` section 7, `docs/API_CONTRACTS.md` (`POST /api/scans`).

## Process shapes
`Start (No Data)` → `Message: Client list` (JSON array) → `Data Process: Split, one document per client` (short Groovy,
also sets `DDP_CLIENT_NAME`) → `Notify: Log request body` → `Try/Catch` →
- Try: `REST: POST /api/scans` → `Data Process: Read scan response` → `Decision: Scan queued (202)?`
  - True → `Notify [OK] client, scan_id, status` → Stop (continue)
  - False (400/401/429/5xx, returned as documents) → `Notify [FAIL] client, http_status, error.code: message` → Stop (continue)
- Catch (host unreachable, timeout, DNS) → `Notify [FAIL] client, status=unreachable, error` → Stop (continue)

Client list (edit it in the Message shape): `Acme Retail`, `https://github.com/BommepalliRoop/demo-target`, `main`,
`auto_fix: true`, `owner_email: owner@easystepin.com`.

## Components (folder `DRYRUN - PatchPilot`, `Rjo4OTMyNDgz`)
| Component | Type | ID |
|---|---|---|
| PatchPilot B1 - Daily Scan Trigger | Process | `5b616403-0e0a-4502-8ac4-bd0c10c8616d` |
| PatchPilot_Backend_Connection | REST connection, auth NONE | `0f6c6c00-d554-4109-ac5b-8405bbcf342a` |
| PatchPilot_Backend_CreateScan_Operation | REST operation, POST `/api/scans`, returnApplicationErrors=true | `4d986295-9ab4-453f-8d30-99ebbcf686b0` |

Source (Boomi workspace, not in this repo): `scripts/gen_b1.py`, `scripts/b1_split_clients.groovy`,
`scripts/b1_read_response.groovy`, `active-development/{process,connector-settings,connector-action}/…B1…/PatchPilot_Backend_*`.

## Switch to the real backend (GUI)
1. Open `PatchPilot_Backend_Connection` → **URL**: replace `https://patchpilot-backend.invalid` with the real
   `BACKEND_URL` (no trailing slash, no `/api`). Save.
2. Open `PatchPilot_Backend_CreateScan_Operation` → **Request Headers** → `X-API-Key`: paste the PatchPilot API key. Save.
   (The key is stored in the Boomi component only; never commit it.)
3. Open the process → **Create Packaged Component** → **Deploy** to the environment
   `f23944f3-15ac-440e-80b4-6bb6b5e5625c`. Push alone does not change what runs.
4. **Run Process** once and check Process Reporting: expect `B1: [OK] client=Acme Retail scan_id=scn_… status=queued`.

## Daily 09:00 IST schedule (GUI only)
The Boomi Companion CLI has no schedule tool, so set it in the GUI. **Turn it on only after the real URL and key are in.**
1. Check the runtime's time zone: Manage → Runtime Management → the Atom → Properties → Basic → Time Zone.
2. Manage → Runtime Management → the Atom → **Deployed Processes** → `PatchPilot B1 - Daily Scan Trigger` →
   **Edit Schedules** (or Process Schedules).
3. Add a schedule, type **Days**, every 1 day, at **09:00** if the time zone is Asia/Kolkata. If it is UTC, use
   **03:30** (or Advanced: minutes `30`, hours `3`, every day).
4. Make sure the schedule is enabled, save, and check the next run time it shows.

## Not done (on purpose)
- The 30 s retry for timeouts/5xx from the spec is skipped: a failed client is logged and the run continues. Add it
  later with a Try/Catch `retryCount` or a Decision + Wait if needed.
- The client list is static in the Message shape (spec: a later version fetches it from the backend).

## Test results (Oct 28, against the placeholder host)
Deployed package `6bc79bd4-4c38-47bc-a0b9-457836215c80` (version 1). Execution
`execution-76045426-7949-436a-a96f-41a48e3f391c-2026.10.28`: status **COMPLETE**. Process log:
```
Split: one document per client  Data Process Execution (SCRIPTING) produced 1 documents.
Log request body  B1: [REQ] client=Acme Retail body={"auto_fix":true,"branch":"main","client_name":"Acme Retail","owner_email":"owner@easystepin.com","repo_url":"https://github.com/BommepalliRoop/demo-target"}
PatchPilot: POST /api/scans  Shape executed with errors in 415 ms.
Try/Catch  Try/Catch Shape sending 1 document(s) down error path
SEVERE Log unreachable backend  B1: [FAIL] client=Acme Retail status=unreachable error=access denied ("java.net.SocketPermission" "patchpilot-backend.invalid" "resolve")
Stop  continuing process
Process execution completed normally.
```
So the split, request body and the unreachable-backend path work. The 202 and 4xx paths are not tested yet; they need
the real backend.

## Deployment status (Oct 28)
B1 is **undeployed**, to free a Standard connector licence slot for Supabase (the training account allows 3: Jira, Slack, Supabase). Once the backend is live, set the real BACKEND_URL and `X-API-Key` in the GUI, free a slot or get a 4th licence, then redeploy B1 and set the schedule.
