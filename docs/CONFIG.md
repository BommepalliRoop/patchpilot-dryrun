# Configuration and keys checklist

Every value PatchPilot needs, who provides it, where to get it, and when. Fill the "Value / status" column
as you collect things. **Never write a secret in this file, in git, or in a chat.** Secrets go only into
`.env` (gitignored, created by T00 from `.env.example`) and into the host's env settings (Render/Railway, Vercel).

Legend: 🔒 = secret (only in `.env` / host settings) · 📄 = safe to write here and share

## 1. Our backend `.env` (repo root)
| Variable | 🔒/📄 | Example / format | Who provides | Where to get it | Needed by | Value / status |
|---|---|---|---|---|---|---|
| `LLM_PROVIDER` | 📄 | `anthropic` or `openai` | Organisers | Kickoff 9:00 | T04 | |
| `LLM_API_KEY` | 🔒 | `sk-...` | Organisers | Kickoff 9:00 | T04 (live) | |
| `LLM_MODEL` | 📄 | e.g. `claude-sonnet-5-5` | Organisers / us | Kickoff; pick the strongest allowed model | T04 | |
| `LLM_BASE_URL` | 📄 | blank, or a gateway / Azure URL | Organisers | Only if keys come via a proxy or Azure | T04 | |
| `LLM_MODE` | 📄 | `mock` → `live` | Us | Switch to `live` once T04 passes with the real key | all AI tasks | `mock` |
| `GITHUB_TOKEN` | 🔒 | `github_pat_...` | Lead | GitHub → Settings → Developer settings → Fine-grained token. Repository access: **demo-target only**. Permissions: Contents RW, Pull requests RW, Metadata R. Expiry 7 days | T09 | |
| `GITLAB_TOKEN` | 🔒 | `glpat-...` | Lead | GitLab → Preferences → Access tokens, scope `api`, only if a client repo is on GitLab (stretch) | T09 | |
| `GITHUB_MODE` | 📄 | `mock` → `live` | Us | Switch after T09 | T09 | `mock` |
| `DEMO_REPO_URL` | 📄 | `https://github.com/BommepalliRoop/demo-target` | Lead / Dev E | Create empty repo tonight; T15 fills it | T02, T15, T17 | |
| `ALLOWED_REPO_PREFIXES` | 📄 | `https://github.com/BommepalliRoop/` (comma-separated) | Us | Only these repos may be scanned (the engine runs their tests) | T03 | |
| `WORK_DIR` | 📄 | blank = `<system temp>/patchpilot` | Us | Override only if temp space is small | T02, T08 | |
| `THREAT_INTEL` | 📄 | `live` / `mock` / `off` (default `live`) | Us | CISA KEV + FIRST EPSS enrichment; no key needed (public feeds) | T02 | `live` |
| `DEMO_MODE` | 📄 | `true` on demo day, else `false` | Us | Enables `/api/demo/reset` (still needs the API key) | T01, T17 | |
| `SCAN_TIMEOUT_S` | 📄 | `600` | Us | Whole-scan timeout | T03 | |
| `MAX_SCANS_PER_HOUR` | 📄 | `20` | Us | Abuse / credit protection | T03 | |
| `FIX_PYTHON` | 📄 | blank = backend Python; e.g. path to `python3.11` | Us | Interpreter for the fix venvs. The demo target needs Python 3.11 (requests 2.25.1 breaks on 3.12+); Docker image is 3.11 already | T08 | |
| `PATCHPILOT_API_KEY` | 🔒 | 32+ random chars | Us | `python -c "import secrets;print(secrets.token_urlsafe(32))"` — share privately with Boomi team for B1 | T03 (B1 auth) | |
| `BOOMI_MODE` | 📄 | `mock` → `live` | Us | Switch after B2 test call works | T10 | `mock` |
| `BOOMI_BASE_URL` | 📄 | `https://<atom-cloud-host>/ws/rest` | Boomi team | Their deployed Web Services Server base URL | T10 | `https://c01-sg.integrate.boomi.com/ws/rest` (host confirmed Oct 28; confirm the `/ws/rest` path on the Shared Web Server page) |
| `BOOMI_USER` | 📄 | Shared Web Server user name | Boomi team | Boomi Atom Management → Shared Web Server → User Management | T10 | created Oct 28 (value in `.env` only) |
| `BOOMI_TOKEN` | 🔒 | token | Boomi team | Same place as `BOOMI_USER` | T10 | created Oct 28 (in `.env` only; reset after the practice run) |
| `BOOMI_B2_PATH` | 📄 | default `/patchpilot/findings` | Boomi team | Only if Boomi cannot use the contract path | T10 | |
| `BOOMI_B3_PATH` | 📄 | default `/patchpilot/scan-summary` | Boomi team | same | T10 | |
| `BOOMI_B4_PATH` | 📄 | default `/patchpilot/compliance` | Boomi team | same | T10 | |
| `BACKEND_URL` | 📄 | `https://patchpilot-api.onrender.com` | Dev C | After T16 deploy | T16, Boomi B1 | |
| `FRONTEND_URL` | 📄 | `https://patchpilot.vercel.app` | Dev C | After T16 deploy (used for CORS + dashboard links in B3) | T16 | |

## 2. Frontend env (Vercel project settings, or `frontend/.env.local`)
| Variable | 🔒/📄 | Value | Notes |
|---|---|---|---|
| `VITE_API_BASE_URL` | 📄 | `BACKEND_URL` | local: `http://localhost:8000` |
| `VITE_USE_MOCK` | 📄 | `true` → `false` | `true` until T03 is merged |

Anything starting with `VITE_` is shipped to the browser — never put a key there.

## 3. Accounts and tools to have ready (tonight)
| Item | Owner | How to check | Status |
|---|---|---|---|
| Python **3.11** (CLAUDE.md requires it; 3.13 alone is not enough) | everyone | `py -3.11 --version` | |
| Node 20+ | everyone | `node --version` | |
| Git + GitHub CLI logged in | everyone | `gh auth status` | |
| Claude Code logged in | everyone | `claude` starts | |
| OSV-Scanner | backend devs | `osv-scanner --version` | |
| Docker (optional) | Dev C | `docker --version` | |
| Collaborator access to `BommepalliRoop/patchpilot` | Lead | invite each dev + Boomi team | |
| Empty `demo-target` repo | Lead | `gh repo create BommepalliRoop/demo-target --public` | |
| Render or Railway account | Dev C | log in | |
| Vercel account linked to GitHub | Dev C | log in | |
| `cloudflared` (fallback tunnel) | Dev C | `cloudflared --version` | |

## 4. Databases — which one is which
| Database | Used by | Engine | Config needed |
|---|---|---|---|
| App database (scans, findings, fixes, integration events) | Our backend only | **SQLite** file `backend/patchpilot.db` (via SQLModel) | None — created automatically on start. Boomi never touches it |
| Compliance log (audit trail, B2 writes, B4 reads) | Boomi only | **PostgreSQL on Supabase** (free plan) | Lead creates it and gives the Boomi team the connection details privately |

## 5. Boomi-side resources — the Lead prepares and sends privately
These values never go into our `.env` or git. They go into Boomi connections. Send them by private message.

| # | Resource | How to create | Values to send to the Boomi team | Status |
|---|---|---|---|---|
| R1 | Compliance PostgreSQL (Supabase) | supabase.com → New project `patchpilot` (pick a region, set and save a strong database password) → SQL Editor → run the `CREATE TABLE` + `CREATE INDEX` from BOOMI_HANDOFF section 4a → Connect → **Session pooler** | host `aws-0-<region>.pooler.supabase.com`, port 5432, database `postgres`, user `postgres.<project-ref>`, password, `sslmode=require`, JDBC URL | ✅ done Oct 27 — Supabase `patchpilot` (ap-northeast-1), host `aws-0-ap-northeast-1.pooler.supabase.com`, user `postgres.eyaujwqdizcselugymkn`; table created, RLS on, M1 columns added, Q1–Q6 tested, `teams_sent` renamed to `slack_sent` |
| R2 | Jira | Jira Cloud site → project `SEC` (Scrum/Kanban, any) → id.atlassian.com → Security → API tokens → create token | site URL, project key, user email, API token | |
| R3 | Slack incoming webhook | api.slack.com/apps → Create New App → From scratch → Incoming Webhooks → On → Add New Webhook → pick `#security-alerts` → copy URL | webhook URL (secret), channel name | |
| R4 | B1 client list | — | `[{"client_name":"Acme Retail","repo_url":"<DEMO_REPO_URL>","branch":"main","auto_fix":true,"owner_email":"<email>"}]` | |
| R5 | PatchPilot access for B1 | after T16 deploy | `BACKEND_URL`, `PATCHPILOT_API_KEY` | |

If the Boomi team already has its own Jira / Slack / database they prefer, they may use those — they just tell you which.
Test R1 before sending: in the Supabase SQL Editor run `SELECT count(*) FROM compliance_log;` → `0`.

## 6. Exchange sheet — what moves between teams
| From → To | Item | When |
|---|---|---|
| Boomi → Dev | `BOOMI_BASE_URL`, `BOOMI_USER`, `BOOMI_TOKEN` (token sent privately) | by 10:30 |
| Boomi → Dev | Final paths for B2/B3/B4 if they differ from the contract | by 10:30 |
| Boomi → Dev | Jira site URL + project key, Slack channel name (for the demo script) | by 10:30 |
| Dev → Boomi | `BACKEND_URL`, `PATCHPILOT_API_KEY` (sent privately) | after T16, ~11:40 |
| Dev → Boomi | `FRONTEND_URL` (dashboard links in Slack messages) | after T16 |
| Dev → Boomi | Client list for B1: `client_name`, `repo_url` (= `DEMO_REPO_URL`), `branch`, `auto_fix`, `owner_email` | before they start |
| Lead → Boomi | R1 compliance PostgreSQL, R2 Jira, R3 Slack webhook (section 5, private) | before they start |

## 7. Switching from mock to live (on the day)
1. All `*_MODE=mock` (and `THREAT_INTEL=mock` if offline) → everything works end to end with fixtures.
2. `LLM_MODE=live` after T04 passes with the kickoff key.
3. `GITHUB_MODE=live` after T09 opens a real PR on demo-target.
4. `BOOMI_MODE=live` after `python -m app.services.boomi_client ping` returns `ok: true` (T10).
5. Check `GET /api/health` shows the modes you expect; the sidebar badges show the same.
