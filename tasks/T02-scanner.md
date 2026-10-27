# T02 — Repo cloner and OSV scanner

| Field | Value |
|---|---|
| Owner lane | Dev A |
| Model | Sonnet 5.5 |
| Wave | 1 |
| Depends on | T00 |
| Unblocks | T03 |
| Branch | `t02-scanner` |

## Goal
Clone a repo and turn osv-scanner output into RawVuln objects.

## Scope
- `cloner.clone(repo_url, branch, scan_id) -> Path` using GitPython into `/tmp/patchpilot/<scan_id>/repo`; supports token via GITHUB_TOKEN; cleanup function.
- `scanner.scan(path) -> list[RawVuln]`: run `osv-scanner scan source -r <path> --format json` (fall back to `--lockfile requirements.txt` style if needed; detect CLI version). Parse package, installed version, vuln id, aliases (prefer CVE id), summary, details, CVSS score (parse severity vector; if missing use database_specific severity → map CRITICAL 9.5/HIGH 8/MEDIUM 5.5/LOW 3), fixed versions.
- If osv-scanner is not installed, fall back to querying `https://api.osv.dev/v1/querybatch` with packages parsed from requirements.txt.
- Save a sample output to `backend/tests/fixtures/osv_sample.json` for other tasks.

## Acceptance criteria
- Running against the demo target (or a tiny fixture repo) returns ≥3 RawVuln with CVE ids and fixed versions.
- Tests use the saved fixture, no network.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T02: Repo cloner and OSV scanner`, push, and print the NEXT block.
