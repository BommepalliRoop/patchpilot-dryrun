# Demo-day runbook (T17)

How to go live, prove it, fall back, and clean up. Commands run from `backend/` with the repo-root `.env` loaded.
Demo flow itself: `docs/DEMO_SCRIPT.md`. Env vars: `docs/CONFIG.md`.

## 1. Tools
| Command | What it does |
|---|---|
| `python -m app.seed` | Adds 2 historical scans (Globex clean scan two days ago, Acme Retail `demo-target` yesterday: 40 real advisories → 1 reachable P1 fixed, Jira + Slack). Only writes SQLite, works offline |
| `python -m app.seed --reset` | Demo reset first (below), then seed. `--if-empty` = only when there are no scans |
| `POST /api/demo/reset` (UI: Shift+R) | Clears DB, SSE buffers and `WORK_DIR` (keeps `WORK_DIR/cache`: pip, npm, KEV). In `GITHUB_MODE=live` also closes our open PRs and deletes `patchpilot/*` branches on every scanned GitHub repo + `DEMO_REPO_URL` (RISKS O3). Needs `DEMO_MODE=true` + `X-API-Key` |
| `python -m app.e2e --base-url <BACKEND_URL>` | Clicks "Run scan" through the API, prints each stage with timings, passes when a P1/P2 finding has a Jira key + Slack within `--budget` (default 120 s). `--expect-live` also fails while any mode is `mock` |

## 2. Go live one switch at a time (LLM → GitHub → Boomi)
After **each** switch: restart the backend, check `GET /api/health` (sidebar badges show the same), then
`python -m app.seed --reset && python -m app.e2e --base-url <BACKEND_URL>`. Only move on when it prints `PASS`.

1. `LLM_MODE=live` (+ `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`). Expect fewer reachable findings than mock
   (the mock verdict says "reachable" for every AST match). Watch the log for `LLM` latency / 429 retries (N1).
2. `GITHUB_MODE=live` + `GITHUB_TOKEN` (fine-grained, demo-target only, Contents RW + Pull requests RW).
   PR links in the UI must open real PRs. Then `--reset` once to check it closes them and deletes the branches.
3. `BOOMI_MODE=live` after `python -m app.services.boomi_client ping` returns `ok: true`. The Jira ticket and the
   Slack message must appear; the Compliance page reads B4.
4. Final proof: `python -m app.e2e --base-url <BACKEND_URL> --expect-live` → `PASS: Jira SEC-… + Slack in …s`.

## 3. Fallback when something live fails on stage (RISKS O1)
1. Set only the failing switch back to `mock` (`LLM_MODE` / `GITHUB_MODE` / `BOOMI_MODE`), restart. Each one is independent.
2. Venue network down: all three `mock` + `THREAT_INTEL=mock`, restart, `python -m app.seed --reset`. The seeded
   scans carry the whole story (P1 PyYAML, fix, PR, Jira, Slack). A new scan still needs GitHub (clone) and OSV.
3. Backend unreachable: frontend with `VITE_USE_MOCK=true` replays a scan with no backend at all.
4. Last resort: play the screen recording (`patchpilot-demo-backup-mock.mp4`, 68 s, mock modes; record a live one
   after step 2.4 succeeds).

## 4. Before / after every rehearsal
- Before: `scripts/warmup.sh` (or `.ps1`), then `python -m app.seed --reset`. The first fix of the day fills the
  pip / npm cache; later runs reuse it, so do one full run before the judges arrive.
- After: `python -m app.seed --reset` (or Shift+R) so no rehearsal PRs, branches or rows are left behind (O3).
  Boomi side: the Boomi team empties practice rows in the compliance log and Jira (not ours to delete).

## 5. Gotchas found in the T17 dry run
| Symptom | Cause | Fix |
|---|---|---|
| Clone of the *public* demo repo fails: `could not read Username … terminal prompts disabled` | `GITHUB_TOKEN` is set but invalid / expired / for another account; the cloner always sends it to github.com | Fix or unset `GITHUB_TOKEN` (public repos need none) |
| Every PyPI fix `needs_human: package_not_in_manifest … requirements-dev.txt` | osv-scanner reported the package from `requirements-dev.txt` (`-r requirements.txt`) | Fixed in T17: the fixer follows `-r` to the file that pins the package |
| npm fix `install_failed: SELF_SIGNED_CERT_IN_CHAIN`, git/pip fail behind a proxy | `clean_env` dropped proxy + CA-bundle variables | Fixed in T17: `HTTP(S)_PROXY`, `NO_PROXY`, `NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `GIT_SSL_CAINFO`, `SSL_CERT_DIR`, `CURL_CA_BUNDLE` pass through |
| Scan fails at `scan` with `OSV.dev API unavailable` | osv-scanner missing and api.osv.dev blocked | Install osv-scanner (Docker image has it); on a locked-down network pre-download its offline DB |
| Flask fix `needs_human` (install_failed) | Flask 3.x needs a newer `click` than the pinned 7.1.2 | Expected and honest; not part of the demo story |

## 6. Measured (dry run, Oct 27, all modes mock, real clone + osv-scanner + pip/npm on demo-target)
| Run | Start → Jira + Slack | Start → done | Result |
|---|---|---|---|
| API e2e check | 30.6 s | 30.6 s | PASS (budget 120 s); 40 alerts, 3 PRs |
| UI rehearsal 1 | — | 40.3 s | P1 PyYAML 5.3.1 → 6.0.3 + AI patch, tests passed, PR, Jira, Slack; 0 console errors |
| UI rehearsal 2 (after Shift+R-style API reset + seed) | — | 44.0 s | same; 0 console errors |
Live LLM / GitHub / Boomi were **not** exercised in the dry run (no keys, Boomi B1–B4 not built yet); do section 2 on the day.
