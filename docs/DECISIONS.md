# Decisions and background (from planning chat, Oct 27, 2026)

## Hackathon facts
- EasyStepIn AI Hackathon 2026 — Wed Oct 28, 2026, EasyStepIn office. Arrive 8:30 AM sharp.
- Schedule: 9:00–9:20 kickoff, 9:20–12:20 build sprint (3 h), 12:20–12:25 code freeze, 12:25–1:30 demos, 1:30–2:00 results.
- Team min 5, locked at registration (no swaps/additions). One team per person.
- Must build a working AI-powered solution. Boomi integration via Boomi Companion is mandatory.
- All code written during the event. API keys provided at kickoff.
- Competition: 7+ teams, including strong ones — the demo must clearly work live.

## Our own expectations for the project
1. Fully automated tool (no human in the loop for the normal path).
2. Useful in day-to-day work at an IT / service company — a real tool, not just a demo.
3. Boomi is a part of the solution (integration backbone), not the product itself.
4. Not a simple/common AI task (email summaries, chatbots, drafting). It must solve a complex, high-impact problem
   that existing tools do not already solve.
Revenue generation optional. Excluded: anything on Elev8/PG, and billing/invoice automation (another team's idea).

## Ideas considered and why rejected
| Idea | Why not |
|---|---|
| DealPilot (lead/RFP → proposal) | Email + AI drafting is common now |
| ScopeGuard (unbilled scope creep) | Good, but close to billing and harder to demo convincingly |
| ModernizeIQ (legacy code → priced proposal) | Not day-to-day use |
| AccountRadar (client churn prediction) | Weekly, not daily; needs lots of mock data |
| IncidentZero (self-diagnosing incidents) | Strong runner-up; kept as backup idea |
| AccessGuard, ReleaseGate, SmartDispatch | Less differentiated or lower demo impact |

## Why PatchPilot
- Every service company patches dependencies and passes client security audits — daily value.
- Scanners only list CVEs; PatchPilot reasons about our code (reachability) and produces a tested fix — rare.
- Boomi has a real job: scheduling, Jira, Slack, compliance logging.
- Live demo: a real vulnerability is found, proven reachable, fixed, and ticketed in front of judges.
- Fits the lead's cybersecurity background, so the pitch is confident.

## Team model
- Dev team builds with Claude Code using `/run-task` on the task board.
- Boomi sub-team (3–4) builds B1–B4 in Boomi Companion from `docs/BOOMI_HANDOFF.md`; dev team gives contracts only.
- Everything runs in parallel using mock modes until live switch in wave 3.

## UI direction
Professional, motion-rich, UX-friendly security console (React + Tailwind + Motion), with ready-made premium
components (shadcn/ui, Magic UI / Aceternity UI, Tremor) to save time — see docs/UI_SPEC.md.

## Judging story (one line)
"300 alerts become the 3 that matter — each with a tested fix, a Jira ticket and an audit trail. Automatically, every day."

## Scope lock (Oct 27)
- Vulnerability source: **OSV only** (OSV-Scanner, fallback OSV.dev API). No extra scanners for the event —
  the 3-hour sprint has no slack, and our edge is reachability + tested fix, not the number of scanners.
- **Added (Oct 27): CISA KEV + EPSS enrichment** — two free public feeds, ~25 min of build spread over T02/T07/T12/T13,
  no new scanner. Adds "actively exploited" to the risk score and the UI/Jira/Slack.
- **Alerts channel (Oct 27): Slack** instead of Microsoft Teams — Slack incoming webhook from Boomi B2/B3; field
  `slack_sent` replaces `teams_sent` in contracts and the compliance table.
- **Compliance database (Oct 27): Supabase PostgreSQL** (moved from Neon). Boomi connects through the Supabase
  Session pooler (IPv4, port 5432). Our app database stays SQLite.
- **Languages (Oct 27): the app is not Python-only.** Every ecosystem OSV understands is scanned and scored
  (Python, JavaScript/TypeScript, Java, Go, Rust, PHP, .NET, Ruby). Reachability: Python deep (AST), all others
  generic (text search + AI). Auto-fix with tests: Python + npm at the event; others get an upgrade PR marked
  "tests not run" when their toolchain is missing. Demo repo gets a small Node part (lodash) to show two languages.
- Roadmap (pitch slide only, not built at the event):
  1. AI-written security proof test in each PR (fails before the fix, passes after).
  2. Secret scanning (gitleaks), code scanning (Bandit/Semgrep), container scanning, license checks.
  3. Deep (parser-based) reachability for JavaScript, Java and Go (tree-sitter); full toolchains in the image; GitLab/Bitbucket merge requests.
