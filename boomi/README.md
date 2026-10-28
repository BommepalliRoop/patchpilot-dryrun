# Boomi artefacts

Owned by the Boomi team. Boomi processes live in the Boomi platform; this folder holds their documentation
so the repo shows the whole solution. How to contribute: `docs/BOOMI_HANDOFF.md` section 11.

## Current status (Oct 28)
| Item | State |
|---|---|
| Boomi account | `Training-Roop Sagar Reddy-Bommepalli`, account ID `trainingroopsagarreddybom-QG5NJ8` |
| Runtime | Atom Cloud, Singapore: `https://c01-sg.integrate.boomi.com` |
| Atom ID | `6ba41b11-d781-4cc4-9a87-4a30615bf0ac` |
| Environment ID | `f23944f3-15ac-440e-80b4-6bb6b5e5625c` |
| Shared Web Server user for PatchPilot | created (username and token are in each developer's `.env` only, never in git) |
| Compliance database | Supabase `public.compliance_log` created, RLS on, queries tested (see `docs/BOOMI_HANDOFF.md` 4a/4b) |
| Boomi Companion plugin (`bc-integration`) | installed; workspace `~/Projects/patchpilot-boomi-workspace` on the Mac (outside this repo, `.env` gitignored) |
| Still to do | Deploy the backend, then put BACKEND_URL + API key into B1, free a 4th licence slot (or undeploy something) and redeploy B1 + set its 09:00 schedule; switch backend to `BOOMI_MODE=live`; rotate the Jira token and Slack webhook (both were pasted in chat) |

**Where the secrets live:** `BOOMI_USER` / `BOOMI_TOKEN` in the PatchPilot `.env`; `SERVER_USERNAME` / `SERVER_TOKEN`
and the AtomSphere API token in `D:\hackathon\boomi-workspace\.env`. Both `.env` files are gitignored. The Shared Web Server
token was shared in chat during setup, so reset it (Atom Management → Shared Web Server → User Management) after the practice run.

| Folder | Process | Status |
|---|---|---|
| `B0/` | Setup: runtime, listener, auth, connections | done: Jira (KAN), Slack (`#security-alerts`), Supabase (+ PostgreSQL JDBC custom library) |
| `B1/` | Daily scan trigger (Boomi → PatchPilot) | built, **undeployed** (licence slot) until the backend URL exists |
| `B2/` | Finding notification → Jira + Slack + compliance log | **live**, idempotent, tested end to end |
| `B3/` | Scan summary → Slack message | **live**, tested (`slack_sent:true`) |
| `B4/` | Compliance report | **live**, tested against Supabase |

Endpoints (Basic auth): `POST /ws/simple/createPatchpilotfinding` (B2), `POST /ws/simple/createPatchpilotscansummary` (B3),
`GET /ws/simple/getPatchpilotcompliance?client_name=&from=` (B4), all under `https://c01-sg.integrate.boomi.com`.
Licence: the training account allows 3 Standard connections (Jira, Slack, Supabase). B1 needs a 4th, for the backend.

Each folder: `README.md` (what it does, shapes, connections — no secrets), `screenshot.png` (process canvas),
`sample-response.json` (real response from a test call), and an XML export if your account allows it.

Never commit tokens, passwords, API keys or webhook URLs.
