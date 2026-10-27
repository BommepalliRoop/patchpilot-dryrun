# T15 — Demo target vulnerable repo

| Field | Value |
|---|---|
| Owner lane | Dev E / Presenter |
| Model | Haiku 5.5 |
| Effort | low |
| Wave | 1 |
| Depends on | — |
| Unblocks | T02, T06, T08, T17 |
| Branch | `t15-demo-target` |

## Goal
A small, realistic client app to scan (separate GitHub repo). Build it in a sibling folder `D:\hackathon\demo-target`, **not** inside the patchpilot repo, and push to `github.com/BommepalliRoop/demo-target`.

## Scope
- Flask app `demo-target/` with ~6 files: routes (POST /import uses `yaml.load` on request data, unsafe), utils that import jinja2 but never use the sandbox, requests used only in a background job, etc.
- `requirements.txt` pins (checked on OSV.dev Oct 27, unique advisories after alias de-dup): Flask 1.1.2 (2), Werkzeug 1.0.1 (10), Jinja2 2.11.2 (5), MarkupSafe 1.1.1 (0), itsdangerous 1.1.0 (0), click 7.1.2 (0), PyYAML 5.3.1 (1: CVE-2020-14343), requests 2.25.1 (4), urllib3 1.26.4 (11) = **~33 alerts**. Do not add Pillow (100+ advisories would slow the demo).
- Target outcome: ~30 alerts → reachable findings in exactly 2 packages (PyYAML `yaml.load` in a POST route = P1; one plain `requests.get` in a background job = P3/P4) → 1 P1 → 2 PRs (one per package). Several requests CVEs may be marked reachable — fine, they share one PR.
- Werkzeug/Jinja2/urllib3 are only used through Flask/requests, never called directly, so they show as not reachable.
- `pip install -r requirements.txt` must succeed on Python 3.11 (PyYAML 5.3.1 builds from source; checked).
- Tests with pytest that pass on old versions; include one call that breaks after the PyYAML upgrade (e.g. `yaml.load(x)` without Loader) so the AI patch step has real work.
- Push to its own repo; put URL in `.env` as DEMO_REPO_URL.

## Acceptance criteria
- osv-scanner on it reports the expected alerts (record the real number in STATUS.md note; demo script and funnel use it); pytest passes on the old versions under Python 3.11.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T15: Demo target vulnerable repo`, push, and print the NEXT block.
