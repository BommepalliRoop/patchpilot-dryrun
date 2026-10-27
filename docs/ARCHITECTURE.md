# Architecture

Diagrams (HLD + LLD, Mermaid): `docs/DIAGRAMS.md`. Stack details: `docs/TECH_STACK.md`.

## High level
```
Boomi scheduler (B1) ──POST /api/scans──┐
Dashboard "Run scan" ───────────────────┤
                                        ▼
                         ┌──────── PatchPilot engine (FastAPI) ────────┐
GitHub client repos ───▶ │ cloner → scanner → symbols(AI) → reachability(AST+AI) │
                         │ → risk → fixer(upgrade, pytest, AI patch) → github_pr  │
                         └───────────┬───────────────┬───────────────┬──────┘
                                     │               │               │
                               Fix pull request   SQLite + SSE    boomi_client
                                 (GitHub)         → Dashboard      │
                                                                   ▼
                                    Boomi (B2/B3/B4): Jira · Teams · Compliance log
```

## Pipeline stages (backend/app/pipeline.py)
Each stage emits an SSE event `{scan_id, stage, status, message, progress, data}` on the event bus.

| # | Stage | Module | Input → Output |
|---|---|---|---|
| 1 | clone | services/cloner.py | repo_url, branch → local path `/tmp/patchpilot/<scan_id>/repo` |
| 2 | scan | services/scanner.py | path → list[RawVuln] (osv-scanner `--format json`) |
| 3 | symbols | services/symbols.py | RawVuln advisory text → VulnSymbols {package, symbols[]} (LLM) |
| 4 | reachability | services/reachability.py | repo path + symbols → Verdict {reachable, confidence, evidence[]} |
| 5 | risk | services/risk.py | cvss, verdict, exposure → score 0–10, priority P1–P4 |
| 6 | fix | services/fixer.py | finding → FixResult {new_version, patch_diff, tests_passed, attempts} |
| 7 | pr | services/github_pr.py | FixResult → pr_url |
| 8 | notify | services/boomi_client.py | finding + pr → Boomi B2; scan summary → B3 |

Only reachable findings (and `unsure` with confidence ≥ 0.5) go to stages 6–8. `auto_fix=false` skips fix + pr
but still notifies Boomi (`event: finding.open`, `fix_status: not_attempted`).

**Group by package for fix + PR.** Several CVEs often hit the same package (e.g. 3 requests CVEs). Stages 6–7 run
once per package: bump to the smallest version that fixes *all* its routed CVEs, one branch, one PR listing every
CVE. Stage 8 still sends one B2 call per finding; findings of the same package share the `pr_url`.

## Reachability algorithm
1. Walk all `.py` files (skip venv, tests, migrations) with `ast`.
2. Build an import alias map: `import yaml as y` → `y` means `yaml`; `from yaml import load` → `load` means `yaml.load`.
3. Collect every `ast.Call`, resolve its dotted name through the alias map.
4. Match against VulnSymbols. Each match → evidence `{file, line, code_snippet (±15 lines), in_route}`.
   `in_route` = enclosing function has a Flask/FastAPI route decorator (`@app.route`, `@app.get`, `@router.post` …).
5. Send matches to the LLM for a verdict (handles cases like `yaml.load(..., Loader=SafeLoader)` = safe).
6. No matches → `not_reachable` without an LLM call (fast, cheap).

## Risk score
`score = min(10, cvss × reach_w × exposure_w)`; reach_w: reachable 1.0, unsure 0.6, not_reachable 0.3;
exposure_w: 1.5 if any evidence `in_route` else 1.0.
Priority: ≥9 P1, ≥7 P2, ≥4 P3, else P4.

## Fix engine
1. Copy repo to a work dir, create branch `patchpilot/<package>-<new-version>` (one per package, see grouping above).
2. Bump the package in `requirements.txt` to the smallest "fixed" version from OSV.
3. `python -m venv .venv && pip install -r requirements.txt && pytest -q` (install 180 s, tests 120 s). Create the venv
   once per package fix; on retries only re-run pytest (and `pip install <pkg>==<v>` if the version changed).
   Use the venv's own interpreter (`.venv/bin/python` on Linux, `.venv\Scripts\python.exe` on Windows).
   If `pip install` itself fails, try the next fixed / newer release (max 3) before giving up.
4. Fail → LLM gets {diff so far, test output, relevant files} → returns unified diff → apply → re-test. Max 2 attempts.
5. Still failing → status `needs_human`.

## Data model (SQLite via SQLModel)
- scans: id, client_name, repo_url, branch, auto_fix, owner_email, status, current_stage, started_at, finished_at,
  total_alerts, reachable_count, p1_count (the other `stats` fields are computed from findings)
- findings: id, scan_id, cve_id, aliases_json, package, installed_version, fixed_version, summary, cvss, vulnerable_symbols_json,
  reachability, confidence, evidence_json, ai_explanation, score, priority, status, fix_id, jira_key, jira_url, teams_sent,
  compliance_log_id, timeline_json
- fixes: id, scan_id, package, new_version, patch_diff, tests_passed, attempts, pr_url, status
  (one row per package fix; findings point to it via fix_id)
- integration_events: id, finding_id (nullable for B3/B4), process (B1–B4), direction, endpoint, request_json, response_json,
  status_code, ok, summary, created_at

## Security of the engine
Full threat and failure list: `docs/RISKS.md`.
Scanned code runs only inside a temp virtualenv under `WORK_DIR` (default `<system temp>/patchpilot/<scan_id>`, i.e.
`/tmp/patchpilot/...` in Docker); no secrets are passed to it (clean env for pip/pytest); workdirs are deleted after
the scan. `POST /api/scans` only accepts repos under `ALLOWED_REPO_PREFIXES`, so the public URL cannot be used to
run strangers' code on our server.
