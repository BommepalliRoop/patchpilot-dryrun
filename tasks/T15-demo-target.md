# T15 — Demo target vulnerable repo

| Field | Value |
|---|---|
| Owner lane | Dev E / Presenter |
| Model | Haiku 5.5 |
| Wave | 1 |
| Depends on | — |
| Unblocks | T02, T06, T08, T17 |
| Branch | `t15-demo-target` |

## Goal
A small, realistic client app to scan (separate GitHub repo).

## Scope
- Flask app `demo-target/` with ~6 files: routes (POST /import uses `yaml.load` on request data, unsafe), utils that import jinja2 but never use the sandbox, requests used only in a background job, etc.
- `requirements.txt` pins old versions confirmed on osv.dev (decide today): e.g. PyYAML 5.3.1, Jinja2 2.10, requests 2.19.1, urllib3 1.24.1, Pillow (imported nowhere).
- Target outcome: ~10–12 alerts, 2 reachable, 1 P1 in a route.
- Tests with pytest that pass on old versions; include one call that breaks after the PyYAML upgrade (e.g. `yaml.load(x)` without Loader) so the AI patch step has real work.
- Push to its own repo; put URL in `.env` as DEMO_REPO_URL.

## Acceptance criteria
- osv-scanner on it reports the expected alerts; pytest passes on the old versions.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T15: Demo target vulnerable repo`, push, and print the NEXT block.
