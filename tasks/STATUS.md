# Task status

Update your row when you start (`in_progress`) and finish (`done`). Keep notes to one line.

| Task | Title | Lane | Model | Effort | Wave | Depends on | Status | Note |
|---|---|---|---|---|---|---|---|---|
| T00 | Repo scaffold and shared foundations | Lead | Sonnet 5.5 | high | 0 | — | done | Backend+frontend scaffold, stubbed Part A routes, 50 tests pass; S4,S12,S13,E1,E2,E8,O2 done; ran on Python 3.13 (3.11 not installed locally) |
| T01 | Data models and persistence | Dev A | Sonnet 5.5 | medium | 1 | T00 | done | SQLModel tables, repository fns, DB-backed scans/findings/activity/reset routes, contracts/api examples; S8,E8,L10 tested; 73 tests pass (3.13) |
| T02 | Repo cloner and OSV scanner | Dev A | Sonnet 5.5 | medium | 1 | T00 | done | cloner (async git, clean env), ecosystems.detect, scanner (osv-scanner CLI v1/v2 + OSV.dev fallback), threat_intel (KEV+EPSS, mock/live/off); S2,S3,N2,N3,N12,E7,E13,L1,L2,L4,L6,L8 tested; 102 tests pass; live smoke on demo-target: 39 vulns PyPI+npm |
| T03 | Scan orchestrator, SSE and scan API | Dev A | Opus 5.5 | high | 2 | T01, T02 (others via stubs) | done | pipeline.run_scan/run_fix (8 stages, gather limit 4, per-package fix+PR, NotImplementedError stubs logged), POST /api/scans (allow-list, dedup, rate limit, X-API-Key + B1 inbound event), SSE replay/synthetic done, POST fix; S1,S3,S9,S10,N6-N9,E3-E7,L7 tested; 171 tests pass (3.13); live smoke on demo-target: 39 findings, done in 13 s |
| T04 | Provider-agnostic LLM client | Dev B | Sonnet 5.5 | medium | 1 | T00 | done | llm.complete_json: anthropic+openai(+Azure) via httpx, mock canned JSON for 4 prompts, 1 retry on invalid JSON, 429/5xx backoff x3, concurrency 4, token+latency logs; N1,E9,O2 tested; 201 pass (3.13); live key test pending kickoff |
| T05 | Vulnerable symbol extraction (AI) | Dev B | Sonnet 5.5 | medium | 2 | T04 | done | symbols.extract: seed map (pyyaml, jinja2, requests, urllib3, werkzeug, flask, lodash per-CVE) is source of truth in mock; live = LLM + seed fallback; memory+SQLite cache; S7,E10,L2,L3 tested; 225 pass (3.13) |
| T06 | Reachability analyzer (AST + AI) | Dev B | Opus 5.5 | high | 2 | T04, T05 | done | Python AST (alias map, attr chains, getattr, instances, transitive in_route via call graph, add_url_rule) + generic regex for npm/Maven/Go/Rust/PHP/NuGet/Ruby; AST safe patterns (SafeLoader, fixed jinja2 template) skip LLM; S5,S7,E10,L3,L9,L11 tested; 263 pass (3.13); demo-target <0.2 s |
| T07 | Risk scorer | Dev B | Haiku 5.5 | low | 2 | T00 | done | risk.score per ARCHITECTURE formula (round 1 dp, cvss 0-10 ValueError); table tests for boundaries, KEV, EPSS, not_reachable+KEV; stub tests updated; 287 pass (3.13) |
| T08 | Fix engine (upgrade, test, AI patch loop) | Dev C | Opus 5.5 | high | 2 | T04 | todo | |
| T09 | GitHub pull request creator | Dev C | Sonnet 5.5 | medium | 3 | T08 | todo | |
| T10 | Boomi client (mock + live) | Dev C | Sonnet 5.5 | medium | 1 | T00 (T01 for event logging) | done | notify_finding/send_scan_summary/get_compliance + strict B2/B3 models, mock (stable SEC-1xx), live Basic auth, 15 s, 1 retry on 5xx/timeout w/ same Idempotency-Key, every call logged; /api/compliance wired to B4 (502 on failure), CLI ping; N5,N6,S4 tested; 312 pass (3.13) |
| T11 | Design system and app shell | Dev D | Sonnet 5.5 | medium | 1 | T00 | todo | |
| T12 | Overview and live scan pages | Dev D | Sonnet 5.5 | medium | 2 | T11 | todo | |
| T13 | Finding detail page | Dev D | Sonnet 5.5 | medium | 2 | T11 | todo | |
| T14 | Integrations and compliance pages | Dev D | Haiku 5.5 | low | 3 | T11 | todo | |
| T15 | Demo target vulnerable repo | Dev E / Presenter | Haiku 5.5 | low | 1 | — | done | Pushed to github.com/BommepalliRoop/demo-target (public, main). pytest 6/6 on Python 3.11.9. osv-scanner 2.7.0 lockfile mode: 110 entries (PyPI 104, npm 6); PyYAML 1 advisory, lodash 6, both ecosystems reported; entries duplicated GHSA/PYSEC, certifi/idna transitive extras (API estimate was 39) |
| T16 | Deployment | Dev C | Sonnet 5.5 | medium | 3 | T03, T11 | todo | |
| T17 | End-to-end integration and demo seed | Lead | Opus 5.5 | high | 4 | T03, T06, T08, T09, T10, T12, T13 | todo | |
| T18 | Polish and rehearsal | Everyone | Sonnet 5.5 | medium | 4 | T17 | todo | |
| B1–B4 | Boomi processes | Boomi team | Boomi Companion | — | 1–3 | contracts | todo | |
