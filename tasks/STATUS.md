# Task status

Update your row when you start (`in_progress`) and finish (`done`). Keep notes to one line.

| Task | Title | Lane | Model | Effort | Wave | Depends on | Status | Note |
|---|---|---|---|---|---|---|---|---|
| T00 | Repo scaffold and shared foundations | Lead | Sonnet 5.5 | high | 0 | — | done | Backend+frontend scaffold, stubbed Part A routes, 50 tests pass; S4,S12,S13,E1,E2,E8,O2 done; ran on Python 3.13 (3.11 not installed locally) |
| T01 | Data models and persistence | Dev A | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T02 | Repo cloner and OSV scanner | Dev A | Sonnet 5.5 | medium | 1 | T00 | done | cloner (async git, clean env), ecosystems.detect, scanner (osv-scanner CLI v1/v2 + OSV.dev fallback), threat_intel (KEV+EPSS, mock/live/off); S2,S3,N2,N3,N12,E7,E13,L1,L2,L4,L6,L8 tested; 102 tests pass; live smoke on demo-target: 39 vulns PyPI+npm |
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
| T15 | Demo target vulnerable repo | Dev E / Presenter | Haiku 5.5 | low | 1 | — | done | Pushed to github.com/BommepalliRoop/demo-target (public, main). pytest 6/6 on Python 3.11.9. osv-scanner 2.7.0 lockfile mode: 110 entries (PyPI 104, npm 6); PyYAML 1 advisory, lodash 6, both ecosystems reported; entries duplicated GHSA/PYSEC, certifi/idna transitive extras (API estimate was 39) |
| T16 | Deployment | Dev C | Sonnet 5.5 | medium | 3 | T03, T11 | todo | |
| T17 | End-to-end integration and demo seed | Lead | Opus 5.5 | high | 4 | T03, T06, T08, T09, T10, T12, T13 | todo | |
| T18 | Polish and rehearsal | Everyone | Sonnet 5.5 | medium | 4 | T17 | todo | |
| B1–B4 | Boomi processes | Boomi team | Boomi Companion | — | 1–3 | contracts | todo | |
