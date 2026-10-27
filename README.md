# PatchPilot — AI vulnerability-to-fix autopilot

EasyStepIn AI Hackathon 2026 · Team PatchPilot

> 300 alerts become the 3 that matter — each with a tested fix, a Jira ticket and an audit trail. Automatically, every day.

**Status:** planning complete — no application code yet. All code is written during the event (Oct 28, 9:20–12:20).

## What it does
IT service companies maintain many client codebases. Dependency scanners report hundreds of CVEs, mostly in library
code the application never calls, so the dangerous ones stay open for weeks. PatchPilot, for every client repo:

1. Scans dependencies (OSV-Scanner).
2. AI extracts the vulnerable functions from each advisory.
3. Python AST + AI prove whether our code actually calls them (file:line evidence, inside a web route or not).
4. Scores real risk: CVSS × reachability × exposure → P1–P4.
5. Upgrades the library, runs the tests, lets AI patch broken code (max 2 retries).
6. Opens a GitHub pull request with the explanation.
7. Boomi creates the Jira ticket, posts the Teams alert and writes the compliance log.

```mermaid
flowchart LR
    B1[Boomi B1<br/>daily schedule] --> API[PatchPilot<br/>FastAPI engine]
    UI[React dashboard] <--> API
    API --> OSV[OSV-Scanner]
    API --> LLM[LLM]
    API --> GH[GitHub PR]
    API --> B2[Boomi B2/B3/B4]
    B2 --> J[Jira]
    B2 --> T[Teams]
    B2 --> L[(Compliance log)]
```

## Requirements
**Functional**
- Fully automated: daily via Boomi (B1) or on demand from the dashboard; no human in the normal path.
- Reachability with evidence (file, line, code snippet, in-route flag) for every finding.
- Risk score and priority P1–P4 per finding.
- Tested fix: upgrade + test run + AI patch (max 2 tries) → `fixed` or `needs_human`.
- One GitHub PR per vulnerable package, never auto-merged.
- Boomi: Jira issue + Teams alert + compliance log per finding; Teams summary per scan; compliance report per client.
- Live dashboard: overview stats, live pipeline view, finding detail, integrations, compliance.

**Non-functional**
- Professional, motion-rich, dark-first UI ([UI spec](docs/UI_SPEC.md)).
- Mock mode for every external service (`LLM_MODE`, `BOOMI_MODE`, `GITHUB_MODE`) so lanes never block.
- Security: only allowed repos are scanned, scanned code runs in a temp venv without our secrets, secrets masked in logs,
  AI patches restricted ([RISKS](docs/RISKS.md)).
- Scan → Jira + Teams in under 2 minutes on the demo repo.
- Contracts are the source of truth ([API contracts](docs/API_CONTRACTS.md)).

## Tech stack
Full details with reasons: [docs/TECH_STACK.md](docs/TECH_STACK.md).

**Backend** (`backend/`)
| Purpose | Choice |
|---|---|
| Language | Python 3.11 |
| API framework / server | FastAPI + Uvicorn |
| Live progress | Server-Sent Events (`sse-starlette`) |
| Database | SQLite via SQLModel |
| Config | `pydantic-settings` (`.env`) |
| HTTP client | httpx |
| Git / GitHub | GitPython · PyGithub |
| Vulnerability data | OSV-Scanner CLI (fallback: OSV.dev API) |
| CVSS score | `cvss` |
| Versions / names | `packaging` |
| Code analysis | Python `ast` |
| Tests | pytest |

**AI**
| Purpose | Choice |
|---|---|
| Client | Provider-agnostic `app/services/llm.py` (`anthropic` / `openai`-compatible; keys at kickoff) |
| Prompts | `backend/app/prompts/*.md`: extract_symbols, reachability_verdict, patch_code, pr_description |
| Output | JSON only, validated with Pydantic, retry once, safe fallback |

**Frontend** (`frontend/`)
| Purpose | Choice |
|---|---|
| Framework | React 18 + Vite + TypeScript |
| Styling | Tailwind CSS + shadcn/ui |
| Motion | Motion (`motion/react`) + Magic UI / Aceternity UI (NumberTicker, AnimatedBeam, BorderBeam) |
| Routing | react-router-dom |
| Charts | Recharts (or Tremor) |
| Code / diff view | Shiki (`github-dark`) |
| Icons | lucide-react |
| Fonts | Inter · JetBrains Mono |

**Integration and deployment**
| Purpose | Choice |
|---|---|
| Integration | Boomi Integration built with Boomi Companion — processes B1–B4 ([handoff](docs/BOOMI_HANDOFF.md)) |
| Backend hosting | Docker on Railway or Render |
| Frontend hosting | Vercel |
| Fallback | Laptop + Cloudflare Tunnel |

**Build tooling:** Claude Code — Opus 5.5 (hard tasks), Sonnet 5.5 (most tasks), Haiku 5.5 (small tasks); model and
effort per task in [tasks/BOARD.md](tasks/BOARD.md).

## Documents
| You are | Read |
|---|---|
| Claude Code (first session) | [CONTEXT.md](CONTEXT.md), then [CLAUDE.md](CLAUDE.md) |
| Anyone | [Decisions](docs/DECISIONS.md) · [Plan](docs/PLAN.md) · [Setup](docs/SETUP.md) |
| Developer using Claude Code | [CLAUDE.md](CLAUDE.md), then [Task board](tasks/BOARD.md) |
| Architect / reviewer | [Tech stack](docs/TECH_STACK.md) · [Architecture](docs/ARCHITECTURE.md) · [Diagrams](docs/DIAGRAMS.md) |
| Boomi team | [Boomi handoff](docs/BOOMI_HANDOFF.md) (+ [boomi/](boomi/README.md) for their exports) |
| Whoever collects keys and URLs | [Config](docs/CONFIG.md) |
| Safety questions | [Risks](docs/RISKS.md) |
| Practice run | [Dry run](docs/DRY_RUN.md) |
| Presenter | [Demo script](docs/DEMO_SCRIPT.md) |
| Using / testing the app | [User guide](docs/USER_GUIDE.md) |
| UI developers | [UI spec](docs/UI_SPEC.md) |

## How we work on the day
1. Open the repo in Claude Code.
2. Pick your lane in [tasks/BOARD.md](tasks/BOARD.md).
3. Open a new session, set the model **and effort** listed for the task, then run `/run-task T0X`.
4. When Claude finishes, its NEXT block names the next task, model, effort and command. Run `/next-task` any time.
