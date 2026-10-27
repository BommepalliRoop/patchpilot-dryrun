# PatchPilot — Full context handoff for Claude Code

This file carries over everything from the planning chat (claude.ai, Oct 27, 2026) so Claude Code can continue
without re-explanation. Read it together with CLAUDE.md. If anything here conflicts with docs/API_CONTRACTS.md,
the contracts file wins.

---------------------------------------------------------------------
## 1. Who and what
- Lead: Roop (Associate Software Engineer, EasyStepIn, Bangalore). Interested in cybersecurity.
- Event: EasyStepIn AI Hackathon 2026, Wed Oct 28, 2026, EasyStepIn office.
- Team: dev team (builds the app with Claude Code) + Boomi sub-team of 3–4 (builds integration in Boomi Companion).
- Project chosen: **PatchPilot – AI vulnerability-to-fix autopilot**.

## 2. Hackathon rules (hard constraints)
- Arrive 8:30 AM. Kickoff 9:00–9:20. **Build sprint 9:20–12:20 (3 hours).** Code freeze 12:20–12:25.
  Demos 12:25–1:30. Results 1:30–2:00. Start is on time even if a team is late.
- Build a **working AI-powered solution**. **Boomi integration via Boomi Companion is mandatory.**
- **All code must be written during the event.** API keys are provided at kickoff (provider not known in advance).
- Team min 5, locked at registration, no swaps. Bring laptop, charger, ready dev environment.
- Competition: 7+ teams, some strong — the live demo must work reliably.

## 3. Roop's own requirements for the project
1. Fully automated (no human in the normal path).
2. Useful every day in an IT / service company — a real tool, not just a demo.
3. Boomi is part of the solution (integration backbone), not the product itself.
4. Not a simple/common AI task (email summaries, chatbots, drafting). Must be a complex, high-impact problem
   existing tools don't already solve.
- Revenue generation optional.
- Excluded: anything on Elev8 / PG projects; billing / invoice automation (another team's idea).
- UI must be professional, UX-friendly, motion-rich ("motion UI").

## 4. Ideas considered (do not revisit unless asked)
DealPilot (RFP→proposal: too common), ScopeGuard (scope creep: near billing), ModernizeIQ (not daily),
AccountRadar (churn: weekly, heavy mock data), IncidentZero (self-healing incidents: **backup idea**),
AccessGuard, ReleaseGate, SmartDispatch (less differentiated).

## 5. The product
**Problem:** Service companies maintain many client codebases. Scanners report hundreds of CVEs, mostly in code
never called. Teams can't separate real risk from noise; dangerous ones stay open for weeks → incidents, failed
audits (ISO 27001 / SOC 2). Fixing is manual.

**Solution (fully automated, daily via Boomi or on demand):**
1. Clone repo (any language: Python deep, others text + AI) → 2. OSV-Scanner finds vulnerable dependencies → 3. AI extracts vulnerable functions from the
advisory → 4. Python AST + AI decide if our code actually calls them (file:line evidence, in-route detection) →
5. Risk score = CVSS × reachability × exposure × exploit data (CISA KEV, EPSS) → P1–P4 → 6. Upgrade to nearest safe version, run pytest, AI patches
breaking code (max 2 retries) → 7. Open GitHub PR with explanation → 8. Boomi: Jira ticket, Slack alert,
compliance log.

**Pitch line:** "300 alerts become the 3 that matter — each with a tested fix, a Jira ticket and an audit trail.
Automatically, every day."

**Why it wins:** daily use · beyond scanners (reasoning + tested fix) · Boomi has a real job · dramatic live demo ·
fits the lead's security background.

## 6. Tech stack (decided)
- Backend: Python 3.11, FastAPI, SQLModel + SQLite, httpx, sse-starlette, GitPython, PyGithub, OSV-Scanner CLI
  (fallback: OSV.dev querybatch API), pytest, Python `ast`.
- AI: provider-agnostic client `backend/app/services/llm.py` (anthropic/openai via LLM_PROVIDER), JSON outputs
  validated by Pydantic, prompts in `backend/app/prompts/*.md`, mock mode.
- Frontend: React 18 + Vite + TypeScript + Tailwind + Motion (`motion/react`) + lucide-react + Recharts + Shiki;
  components from shadcn/ui, Magic UI / Aceternity UI (NumberTicker, AnimatedBeam, BorderBeam), Tremor.
  (Streamlit was considered and dropped for a more professional UI.)
- Integration: Boomi Integration built with Boomi Companion — processes B1–B4.
- Deploy: backend Docker on Render/Railway, frontend on Vercel, fallback local + Cloudflare Tunnel.

## 7. Boomi split (contract-only coupling)
| ID | Process | Direction |
|---|---|---|
| B1 | Daily schedule → `POST /api/scans` (X-API-Key) | Boomi → PatchPilot |
| B2 | `POST /patchpilot/findings` → Jira + Slack + compliance log → returns jira_key | PatchPilot → Boomi (most important) |
| B3 | `POST /patchpilot/scan-summary` → Slack summary message | PatchPilot → Boomi |
| B4 | `GET /patchpilot/compliance` → audit rows | PatchPilot → Boomi |
Payloads: `contracts/boomi/*.json`. Details: docs/BOOMI_HANDOFF.md. Dev team uses `BOOMI_MODE=mock` until live.

## 8. How work is organised in this repo
- `tasks/T00–T18` one file each (owner lane, model, wave, depends on, scope, acceptance criteria).
- `tasks/BOARD.md` lanes + waves + dependency graph + model guide; `tasks/STATUS.md` live progress.
- Run a task: `/run-task T06`. See what's unblocked: `/next-task`. Each finished task prints a NEXT block.
- Models: Opus 5.5 → T03, T06, T08, T17 · Haiku 5.5 → T07, T14, T15 · Sonnet 5.5 → the rest.
- Waves: 0 (9:20–9:35) T00 · 1 (9:35–10:30) T01 T02 T04 T10 T11 T15 + B2 · 2 (10:30–11:20) T03 T05 T06 T07 T08
  T12 T13 + B1 · 3 (11:20–11:50) T09 T14 T16 + B3/B4 + live switch · 4 (11:50–12:15) T17 T18 · 12:20 freeze.
- Every external dependency has a mock mode: LLM_MODE, BOOMI_MODE, GITHUB_MODE (default mock).

## 9. Demo plan
Demo target: separate small Flask repo with old pinned libraries (e.g. PyYAML 5.3.1 used unsafely in a POST route,
Flask/Werkzeug/Jinja2/requests/urllib3 present but not reachable). Expected: ~30 alerts (pins checked on OSV.dev Oct 27, see T15) → 2 reachable → 1 P1 → fixed PR →
Jira + Slack + compliance row. Script: docs/DEMO_SCRIPT.md. Backup: mock-mode run + screen recording.

## 10. Open items / to confirm
- Ask organisers: may the demo target repo be prepared before the event? If not, build it in T15.
- Boomi team to share BOOMI_BASE_URL + auth by 10:30; we share BACKEND_URL after T16.
- Confirm demo library CVEs on osv.dev; Jira project key; Slack webhook URL.
- Fill names in tasks/BOARD.md.

## 11. Where to read next
CLAUDE.md → docs/DECISIONS.md → docs/PLAN.md → docs/ARCHITECTURE.md → docs/API_CONTRACTS.md → docs/UI_SPEC.md →
tasks/BOARD.md → your task file.

## 12. First prompt to use in Claude Code
"Read CONTEXT.md and CLAUDE.md, then tasks/BOARD.md. Summarise the plan in 10 lines, list my lane's tasks in order
with their models, and confirm you understand the mock-mode and /run-task workflow. Do not write code yet."
