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
| Boomi Companion plugin (`bc-integration`) | installed; workspace `D:\hackathon\boomi-workspace` (outside this repo, `.env` gitignored) |
| Still to do | AtomSphere API token in the workspace `.env`, `jq` installed, Jira + Slack connections, build B0–B4, B2 curl test, then `BOOMI_MODE=live` |

**Where the secrets live:** `BOOMI_USER` / `BOOMI_TOKEN` in the PatchPilot `.env`; `SERVER_USERNAME` / `SERVER_TOKEN`
and the AtomSphere API token in `D:\hackathon\boomi-workspace\.env`. Both `.env` files are gitignored. The Shared Web Server
token was shared in chat during setup, so reset it (Atom Management → Shared Web Server → User Management) after the practice run.

| Folder | Process | Status |
|---|---|---|
| `B0/` | Setup: runtime, listener, auth, connections | todo |
| `B1/` | Daily scan trigger (Boomi → PatchPilot) | todo |
| `B2/` | Finding notification → Jira + Slack + compliance log | todo |
| `B3/` | Scan summary → Slack message | todo |
| `B4/` | Compliance report | todo |

Each folder: `README.md` (what it does, shapes, connections — no secrets), `screenshot.png` (process canvas),
`sample-response.json` (real response from a test call), and an XML export if your account allows it.

Never commit tokens, passwords, API keys or webhook URLs.
