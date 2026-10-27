# T02 — Repo cloner and OSV scanner

| Field | Value |
|---|---|
| Owner lane | Dev A |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 1 |
| Depends on | T00 |
| Unblocks | T03 |
| Branch | `t02-scanner` |

## Goal
Clone a repo and turn osv-scanner output into RawVuln objects.

## Scope
- `cloner.clone(repo_url, branch, scan_id) -> Path` using GitPython into `/tmp/patchpilot/<scan_id>/repo`; supports token via GITHUB_TOKEN; cleanup function.
- `scanner.scan(path) -> list[RawVuln]`: run `osv-scanner scan source -r <path> --format json` (fall back to `--lockfile requirements.txt` style if needed; detect CLI version). Note: osv-scanner exits with code **1 when it finds vulnerabilities** — that is success, not an error. Parse package, installed version, vuln id, aliases (prefer CVE id), summary, details, CVSS score (compute the base score from the CVSS v3/v4 vector with the `cvss` PyPI package; if missing use database_specific severity → map CRITICAL 9.5/HIGH 8/MEDIUM 5.5/LOW 3), fixed versions.
- If osv-scanner is not installed, fall back to querying `https://api.osv.dev/v1/querybatch` with packages parsed from requirements.txt.
- Save a sample output to `backend/tests/fixtures/osv_sample.json` for other tasks.
- `threat_intel.enrich(vulns) -> vulns` per docs/ARCHITECTURE.md "Threat intelligence": CISA KEV lookup (daily cached file) +
  FIRST EPSS batch lookup; sets `kev`, `kev_date_added`, `epss`, `epss_percentile`. `THREAT_INTEL=live|mock|off`
  (mock = fixtures `kev_sample.json` / `epss_sample.json`, saved by this task). Called by the pipeline right after `scanner.scan`.

- **All languages:** `ecosystems.detect(path)` per docs/ARCHITECTURE.md "Language support" (manifest table, skip vendored dirs) → scan `languages`. Scan with `osv-scanner scan source -r` so every manifest is included; each RawVuln carries `ecosystem` (OSV name). The requirements.txt-only fallback becomes: OSV.dev querybatch for every detected lockfile we can parse (PyPI + npm at minimum).

## Acceptance criteria
- Running against the demo target (or a tiny fixture repo) returns ≥3 RawVuln with CVE ids and fixed versions.
- Tests use the saved fixtures, no network. Threat intel: KEV hit, KEV miss, EPSS present, feed down → `kev=false`, `epss=null`, no exception.

- Fixture repo with `requirements.txt` + `package-lock.json` → findings for both PyPI and npm; `languages` lists both with the right `analysis`.

## Hardening (docs/RISKS.md)
Implement and test these rows: S2, S3, N2, N3, N12, E7, E13, L1, L2, L4, L6, L8.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T02: Repo cloner and OSV scanner`, push, and print the NEXT block.
