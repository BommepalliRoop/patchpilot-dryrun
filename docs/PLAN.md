# PatchPilot — Project plan

## 1. Project name
PatchPilot – AI vulnerability-to-fix autopilot

## 2. Problem statement
IT service companies maintain many client codebases. Dependency scanners report hundreds of CVEs, most in
library code the application never calls. Teams cannot separate real risk from noise, so dangerous
vulnerabilities stay open for weeks, causing incidents, failed client audits (ISO 27001, SOC 2) and lost trust.
Fixing is manual: upgrade, repair what breaks, test, raise a ticket, inform the owner.

## 3. Solution
Runs daily (Boomi scheduler) or on demand:
1. Scan dependencies with OSV-Scanner.
2. AI extracts the vulnerable functions from each advisory.
3. AST + AI check whether our code actually calls them (file and line as evidence).
4. Risk score = CVSS × reachability × exposure × exploit data (CISA KEV, EPSS) → P1–P4.
5. Upgrade to the nearest safe version, run tests, AI patches broken code (max 2 retries).
6. Open a GitHub PR with a full explanation.
7. Boomi: Jira ticket, Slack alert, compliance log per client.

## 4. Why this idea
Daily use in every service company · goes beyond scanners (reasoning + tested fix) · real security and audit
impact · Boomi is the integration backbone · strong live demo.

## 5. Team split
| Team | People | Owns |
|---|---|---|
| Dev team | 3–4 | Backend, AI, fix engine, UI, deployment (Claude Code tasks T00–T18) |
| Boomi team | 3–4 | Boomi processes B1–B4 via Boomi Companion (`docs/BOOMI_HANDOFF.md`) |

## 6. Tech stack
Backend: Python 3.11, FastAPI, SQLModel/SQLite, httpx, GitPython, PyGithub, OSV-Scanner CLI, pytest.
AI: provider-agnostic LLM client (keys at kickoff), JSON outputs, prompts in `backend/app/prompts/`.
Frontend: React 18, Vite, TypeScript, Tailwind CSS, Motion (`motion/react`), Lucide icons, Recharts, Shiki (code view).
Integration: Boomi Integration built with Boomi Companion (Jira, Slack webhook, database/SharePoint).
Deploy: backend Docker on Render/Railway (or laptop + Cloudflare Tunnel fallback), frontend on Vercel.

## 7. Timeline (Oct 28)
| Time | What |
|---|---|
| Today (Oct 27) | Push this repo (docs only, no code). Boomi team studies the handoff. Prepare accounts. |
| 8:30 | Arrive, repo cloned, Claude Code logged in, Node 20 + Python 3.11 + Docker ready |
| 9:20–9:35 | Wave 0: T00 scaffold (one person); others set up keys and accounts |
| 9:35–10:30 | Wave 1 in parallel |
| 10:30–11:20 | Wave 2 in parallel |
| 11:20–11:50 | Wave 3: deployment, Boomi switch from mock to live |
| 11:50–12:15 | Wave 4: end-to-end, polish, rehearsal |
| 12:20 | Code freeze |

## 8. Prepare today (no code)
- GitHub repo for PatchPilot and a separate demo target repo; fine-grained token with PR rights.
- Boomi access for the Boomi team; Jira project key; Slack incoming webhook URL.
- Render/Railway + Vercel accounts; Cloudflare Tunnel installed as fallback.
- Choose old library versions for the demo target and confirm CVEs on osv.dev.
- Ask organisers whether the demo target app may be prepared before the event. If not, T15 builds it.
