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
                                    Boomi (B2/B3/B4): Jira · Slack · Compliance log
```

## Pipeline stages (backend/app/pipeline.py)
Each stage emits an SSE event `{scan_id, stage, status, message, progress, data}` on the event bus.

| # | Stage | Module | Input → Output |
|---|---|---|---|
| 1 | clone | services/cloner.py | repo_url, branch → local path `/tmp/patchpilot/<scan_id>/repo` |
| 2 | scan | services/ecosystems.py + services/scanner.py + services/threat_intel.py | path → list[RawVuln] (osv-scanner `--format json`), each enriched with `kev`, `kev_date_added`, `epss`, `epss_percentile` |
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

## Language support (services/ecosystems.py)
PatchPilot works on any repo whose dependencies OSV understands. Depth differs per language:

| Ecosystem (OSV name) | Manifest / lockfile detected | Scan + exploit data | Reachability | Auto-fix + tests | Test command |
|---|---|---|---|---|---|
| PyPI (Python) | `requirements.txt`, `poetry.lock`, `Pipfile.lock` | ✅ | **deep** — Python `ast` | ✅ (`requirements.txt` pins) | `pytest -q` |
| npm (JavaScript/TypeScript) | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | ✅ | generic (text + AI) | ✅ `npm install <pkg>@<v> --ignore-scripts` | `npm test` |
| Maven (Java/Kotlin) | `pom.xml`, `gradle.lockfile` | ✅ | generic | bump version in manifest | `mvn -q test` / `gradle test` |
| Go | `go.mod` | ✅ | generic | `go get <mod>@<v>` | `go test ./...` |
| crates.io (Rust) | `Cargo.lock` | ✅ | generic | `cargo update -p <crate> --precise <v>` | `cargo test` |
| Packagist (PHP) | `composer.lock` | ✅ | generic | `composer require <pkg>:<v> --no-scripts` | `vendor/bin/phpunit` |
| NuGet (.NET) | `packages.lock.json`, `*.csproj` | ✅ | generic | bump `PackageReference` | `dotnet test` |
| RubyGems (Ruby) | `Gemfile.lock` | ✅ | generic | `bundle update <gem> --conservative` | `bundle exec rspec` |

**Detection.** `ecosystems.detect(repo_path)` lists the manifests found (skipping `node_modules`, `vendor`, `.venv`, `target`)
→ `languages: [{ecosystem, manifests[], analysis: deep|generic}]` on the scan. OSV-Scanner scans them all in one run (`-r`).

**Generic reachability (all non-Python languages).**
1. Import search per language (regex table): `import`/`require(` (JS/TS), `import` (Java/Kotlin/Go), `use` (Rust/PHP),
   `using` (C#), `require` (Ruby) — finds files that use the vulnerable package at all.
2. Symbol search: the vulnerable function names from the symbols stage (e.g. `_.template`, `template(`) in those files.
3. Snippets ±15 lines → same LLM verdict prompt (`reachability_verdict`) with the language named.
4. Package never imported in source → `not_reachable` (it is only a transitive dependency), no LLM call.
5. Generic verdicts are capped at confidence 0.8 and say "text + AI analysis" in the explanation (honest about depth).
`in_route` for generic languages: AI judges from the snippet (Express `app.get(`, Spring `@GetMapping`, etc.).

**Fix adapters.** One adapter per ecosystem with `bump(repo, package, version)`, `install()`, `test()`.
The Docker image ships **Python and Node.js**; for other ecosystems the adapter runs only if the toolchain is on the
PATH. If it is not, PatchPilot still bumps the manifest and opens the PR, with `fix_status: fixed_untested` and a
clear "tests not run by PatchPilot" label — never presented as tested. Installs never run package scripts
(`--ignore-scripts`, `--no-scripts`) — see RISKS S15.

**Git hosts.** Clone works for any HTTPS git URL on the allow-list (GitHub, GitLab, Bitbucket). Fix PRs:
GitHub (required) via PyGithub; GitLab merge requests via `python-gitlab` when `GITLAB_TOKEN` is set (stretch, T09).
Other hosts → `needs_human` with the patch diff attached in the finding.

## Threat intelligence (services/threat_intel.py)
- CISA KEV: one JSON file `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` (~1.8 MB, ~1,800 CVEs).
  Download once per day, cache on disk under `WORK_DIR/cache/kev.json`; look up by `cveID`.
- FIRST EPSS: `https://api.first.org/data/v1/epss?cve=<id1>,<id2>,...` — batch up to 100 CVE ids per call; cache per CVE for 24 h.
- Timeout 10 s each, no retry storm (one retry). Feed down → `kev=false`, `epss=null`, timeline note
  "threat feed unavailable"; the scan never fails because of these feeds.
- Mock/offline: fixtures `backend/tests/fixtures/kev_sample.json`, `epss_sample.json` when `THREAT_INTEL=mock`.
- Checked Oct 27: none of the demo CVEs is in KEV; PyYAML CVE-2020-14343 EPSS 0.06 = top 7% (percentile 0.93).

## Reachability algorithm
1. Walk all `.py` files (skip venv, tests, migrations) with `ast`.
2. Build an import alias map: `import yaml as y` → `y` means `yaml`; `from yaml import load` → `load` means `yaml.load`.
3. Collect every `ast.Call`, resolve its dotted name through the alias map.
4. Match against VulnSymbols. Each match → evidence `{file, line, code_snippet (±15 lines), in_route}`.
   `in_route` = enclosing function has a Flask/FastAPI route decorator (`@app.route`, `@app.get`, `@router.post` …).
5. Send matches to the LLM for a verdict (handles cases like `yaml.load(..., Loader=SafeLoader)` = safe).
6. No matches → `not_reachable` without an LLM call (fast, cheap).

## Risk score
`score = min(10, cvss × reach_w × exposure_w × threat_w)`; reach_w: reachable 1.0, unsure 0.6, not_reachable 0.3;
exposure_w: 1.5 if any evidence `in_route` else 1.0;
threat_w: 1.3 if `kev` (actively exploited), else 1.1 if `epss_percentile` ≥ 0.9, else 1.0.
A `not_reachable` finding stays below P1 even when in KEV (max score 10 × 0.3 × 1.3 = 3.9 → P4) — reachability decides.
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
- scans: id, client_name, repo_url, branch, auto_fix, owner_email, languages_json, status, current_stage, started_at, finished_at,
  total_alerts, reachable_count, p1_count (the other `stats` fields are computed from findings)
- findings: id, scan_id, cve_id, aliases_json, ecosystem, analysis, package, installed_version, fixed_version, summary, cvss, kev, kev_date_added,
  epss, epss_percentile, vulnerable_symbols_json,
  reachability, confidence, evidence_json, ai_explanation, score, priority, status, fix_id, jira_key, jira_url, slack_sent,
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
