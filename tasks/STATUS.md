# Task status

Update your row when you start (`in_progress`) and finish (`done`). Keep notes to one line.

| Task | Title | Lane | Model | Effort | Wave | Depends on | Status | Note |
|---|---|---|---|---|---|---|---|---|
| T00 | Repo scaffold and shared foundations | Lead | Sonnet 5.5 | high | 0 | — | todo | |
| T01 | Data models and persistence | Dev A | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T02 | Repo cloner and OSV scanner | Dev A | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T03 | Scan orchestrator, SSE and scan API | Dev A | Opus 5.5 | high | 2 | T01, T02 (others via stubs) | todo | |
| T04 | Provider-agnostic LLM client | Dev B | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T05 | Vulnerable symbol extraction (AI) | Dev B | Sonnet 5.5 | medium | 2 | T04 | todo | |
| T06 | Reachability analyzer (AST + AI) | Dev B | Opus 5.5 | high | 2 | T04, T05 | todo | |
| T07 | Risk scorer | Dev B | Haiku 5.5 | low | 2 | T00 | todo | |
| T08 | Fix engine (upgrade, test, AI patch loop) | Dev C | Opus 5.5 | high | 2 | T04 | todo | |
| T09 | GitHub pull request creator | Dev C | Sonnet 5.5 | medium | 3 | T08 | todo | |
| T10 | Boomi client (mock + live) | Dev C | Sonnet 5.5 | medium | 1 | T00 (T01 for event logging) | todo | |
| T11 | Design system and app shell | Dev D | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T12 | Overview and live scan pages | Dev D | Sonnet 5.5 | medium | 2 | T11 | todo | |
| T13 | Finding detail page | Dev D | Sonnet 5.5 | medium | 2 | T11 | todo | |
| T14 | Integrations and compliance pages | Dev D | Haiku 5.5 | low | 3 | T11 | todo | |
| T15 | Demo target vulnerable repo | Dev E / Presenter | Haiku 5.5 | low | 1 | — | in_progress | Pushed to github.com/BommepalliRoop/demo-target (public, main); OSV: 39 alerts (33 PyPI + 6 npm); pytest 6/6 pass on Python 3.11.9 (venv); osv-scanner CLI not run (OSV.dev API used); GitHub repo not created (gh not logged in) |
| T16 | Deployment | Dev C | Sonnet 5.5 | medium | 3 | T03, T11 | todo | |
| T17 | End-to-end integration and demo seed | Lead | Opus 5.5 | high | 4 | T03, T06, T08, T09, T10, T12, T13 | todo | |
| T18 | Polish and rehearsal | Everyone | Sonnet 5.5 | medium | 4 | T17 | todo | |
| B1–B4 | Boomi processes | Boomi team | Boomi Companion | — | 1–3 | contracts | todo | |
