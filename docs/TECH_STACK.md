# Tech stack

One page for "what do we use, where, and why". Exact library versions are pinned by T00 on the day
(`backend/requirements.txt`, `frontend/package.json`). Diagrams: `docs/DIAGRAMS.md`.

## At a glance
| Layer | Choice | Why |
|---|---|---|
| Backend language | Python 3.11 | Same language as the demo target, so we can parse it with the standard `ast` module |
| API framework | FastAPI + Uvicorn | Async, Pydantic-native, automatic OpenAPI docs at `/docs` |
| Live progress | Server-Sent Events (`sse-starlette`) | One-way stream is all we need; simpler than WebSockets, works through proxies |
| Persistence | SQLModel on SQLite | Zero setup, one file, good enough for a demo and a daily job |
| Compliance log (Boomi side) | PostgreSQL on Supabase (free plan, Session pooler), written by Boomi B2, read by B4 | Real audit trail outside our app; Boomi Database connector |
| HTTP client | httpx | Async, timeouts and retries for OSV, Boomi and LLM calls |
| Git | GitPython (clone, branch, commit) + PyGithub (pull requests) | Mature, simple APIs |
| Vulnerability data | OSV-Scanner CLI (`--format json`); fallback OSV.dev `querybatch` API | Free, open, covers PyPI with fixed-version ranges |
| Exploit data | CISA KEV JSON feed + FIRST EPSS API (`services/threat_intel.py`) | Free, no key; tells which CVEs attackers actually use — boosts real risk |
| Code analysis | Python `ast` (import alias map + call resolution); text import/symbol search for other languages | Deterministic where possible; AI judges the matches |
| Fix toolchains | Python + Node.js in the Docker image; others used if installed | Python + npm fixes are fully tested at the event |
| Tests | pytest (our code and the scanned repo's tests inside a temp venv) | Standard; fixer uses it to prove the upgrade is safe |
| AI | Provider-agnostic client `app/services/llm.py` (`LLM_PROVIDER=anthropic|openai`) | Keys and provider are only known at kickoff |
| Frontend | React 18 + Vite + TypeScript | Fast dev server, typed API client |
| Styling | Tailwind CSS + shadcn/ui components themed with our tokens | Professional look without building primitives |
| Motion | Motion (`motion/react`) + Magic UI / Aceternity pieces (NumberTicker, AnimatedBeam, BorderBeam) | Motion-rich UI required by the brief |
| Charts / code | Recharts (or Tremor) · Shiki (`github-dark`) · lucide-react icons | Stat cards, trends, highlighted evidence lines |
| Integration | Boomi Integration, built with Boomi Companion (processes B1–B4) | Mandatory; Boomi owns Jira, Slack and the compliance log |
| Deploy | Backend: Docker on Render or Railway · Frontend: Vercel · Fallback: laptop + Cloudflare Tunnel | Public URLs so Boomi can call us; tunnel if a host fails |

## Backend
- Layout: `app/api` (routers) · `app/core` (config, db, logging, events bus) · `app/models` (tables + schemas) ·
  `app/services` (one module per pipeline stage) · `app/pipeline.py` (orchestrator) · `app/prompts/*.md`.
- Config: `pydantic-settings` reads `.env`. No global state except the SSE event bus.
- Every response and request body is a Pydantic model that matches `docs/API_CONTRACTS.md`.
- Scanned code runs only inside `/tmp/patchpilot/<scan_id>` in its own virtualenv, never with our secrets.

## AI usage (runtime, inside the product)
| Stage | Prompt (`app/prompts/`) | Input | Output (Pydantic) |
|---|---|---|---|
| symbols (T05) | `extract_symbols.md` | package, CVE, summary, details, references | `{package, import_names[], symbols[], safe_usage_notes, confidence}` |
| reachability (T06) | `reachability_verdict.md` | symbols, safe_usage_notes, evidence snippets (±15 lines) | `{reachability, confidence, explanation}` |
| fix (T08) | `patch_code.md` | package, old→new version, failing test output, relevant files | `{diff (unified), explanation}` |

Rules: JSON only, validated; on invalid JSON retry once with the validation error, then fall back safely
(exact fallbacks are defined in each task file). No AST matches → `not_reachable` without an LLM call.

## Frontend
- Routes: `/` Overview · `/scans/:id` live scan · `/findings/:id` detail · `/integrations` · `/compliance`.
- `src/lib/api.ts` is the only place that calls the backend; `src/lib/types.ts` mirrors the contracts;
  `src/lib/mock/` fixtures when `VITE_USE_MOCK=true`.
- Design tokens and motion rules: `docs/UI_SPEC.md` (dark-first, teal accent, Inter + JetBrains Mono).

## Integration (Boomi)
| ID | Direction | Endpoint |
|---|---|---|
| B1 | Boomi → PatchPilot | `POST ${BACKEND_URL}/api/scans` with `X-API-Key` |
| B2 | PatchPilot → Boomi | `POST ${BOOMI_BASE_URL}/patchpilot/findings` → Jira + Slack + compliance log, returns `jira_key` |
| B3 | PatchPilot → Boomi | `POST ${BOOMI_BASE_URL}/patchpilot/scan-summary` → Slack summary message |
| B4 | PatchPilot → Boomi | `GET ${BOOMI_BASE_URL}/patchpilot/compliance` → audit rows |

## Modes and environment
Full checklist with owners and sources: `docs/CONFIG.md`.

| Variable | Values | Default | Effect |
|---|---|---|---|
| `LLM_MODE` | `mock` / `live` | `mock` | mock returns canned JSON per prompt |
| `BOOMI_MODE` | `mock` / `live` | `mock` | mock returns fake `jira_key`, still logs integration events |
| `GITHUB_MODE` | `mock` / `live` | `mock` | mock returns a fake PR URL, no push |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | from kickoff | — | provider selection (base URL only for gateways) |
| `BOOMI_BASE_URL`, `BOOMI_USER`, `BOOMI_TOKEN`, `BOOMI_B2/B3/B4_PATH` | from Boomi team | contract paths | B2–B4 calls |
| `DEMO_REPO_URL` | demo-target repo | — | default repo for scans and B1 |
| `GITHUB_TOKEN` | repo-scoped PAT | — | push branch + open PR on the demo target |
| `PATCHPILOT_API_KEY` | shared secret | — | B1 auth |
| `BACKEND_URL`, `FRONTEND_URL`, `VITE_API_BASE_URL` | URLs | localhost | CORS and client base URL |

## Build tooling (Claude Code, during the sprint)
| Model | Effort | Tasks |
|---|---|---|
| Opus 5.5 | high | T03, T06, T08, T17 |
| Sonnet 5.5 | high | T00 |
| Sonnet 5.5 | medium | T01, T02, T04, T05, T09, T10, T11, T12, T13, T16, T18 |
| Haiku 5.5 | low | T07, T14, T15 |

One task per fresh session. Queue and commands: `tasks/BOARD.md` → "Task queue".
