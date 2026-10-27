# User guide — how PatchPilot is used and tested

## 1. What PatchPilot needs from a client
The only input is a **GitHub repository**. Public and private both work:

| Repo type | What is needed |
|---|---|
| Public | Nothing extra for scanning. To open the fix PR, our `GITHUB_TOKEN` needs write access to it |
| Private | Our `GITHUB_TOKEN` (fine-grained) must include that repo with **Contents: read/write**, **Pull requests: read/write**, **Metadata: read** |
| Both | The repo URL must start with one of `ALLOWED_REPO_PREFIXES` (safety rule: we install and test the code) |

**Any language — what the repo must contain**
PatchPilot detects the languages from the dependency files it finds. One repo can have several (e.g. Python backend + JS tools).

| Language | Dependency file we read | Reachability | Auto-fix |
|---|---|---|---|
| Python | `requirements.txt` (pinned `==`), `poetry.lock`, `Pipfile.lock` | Deep (code parser) | ✅ tested with `pytest` |
| JavaScript / TypeScript | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | Text + AI | ✅ tested with `npm test` |
| Java / Kotlin | `pom.xml`, `gradle.lockfile` | Text + AI | Upgrade PR; tested if Maven/Gradle is installed |
| Go | `go.mod` | Text + AI | Upgrade PR; tested if Go is installed |
| Rust, PHP, .NET, Ruby | `Cargo.lock`, `composer.lock`, `packages.lock.json`, `Gemfile.lock` | Text + AI | Upgrade PR; tested if the toolchain is installed |

| Requirement | Why | If missing |
|---|---|---|
| Exact versions (a lockfile, or `==` pins for Python) | Vulnerabilities belong to specific versions | Unpinned entries are skipped |
| Tests that pass today | Prove the upgrade did not break anything | Python/npm: `needs_human`; others: PR marked "tests not run" |
| GitHub host | PRs are opened with the GitHub API | GitLab: merge request if `GITLAB_TOKEN` is set (stretch), else `needs_human` with the diff |
| Web routes (optional) | "Called inside a web route" → higher risk | Still works; exposure just isn't boosted |

**What the client's team gets:** one PR per vulnerable package (never auto-merged — they review and merge),
a Jira issue per real finding, a Slack alert, and a compliance log row for audits.

## 2. One-time setup (operator — us)
1. Backend and frontend running (local `make dev` / `scripts/dev.ps1`, or deployed URLs).
2. `.env` filled (see `docs/CONFIG.md`): `ALLOWED_REPO_PREFIXES` includes the client's GitHub org,
   `GITHUB_TOKEN` can access the repo, LLM key set, modes set (`mock` or `live`).
3. Boomi: B1 client list contains the client (`client_name`, `repo_url`, `branch`, `auto_fix`, `owner_email`);
   B2–B4 live, Jira project and Slack channel ready.
4. Open the dashboard → sidebar badges show LLM / Boomi / GitHub as `mock` or `live`.

## 3. How it runs — step by step
**Start a scan** (either way):
- **Automatic:** Boomi B1 runs every day at 09:00 for every client in its list.
- **Manual:** Dashboard → **Run scan** → fill in:

| Field | Example | Notes |
|---|---|---|
| Client name | `Acme Retail` | Shown in Jira, Slack and compliance |
| Repo URL | `https://github.com/BommepalliRoop/demo-target` | Must be allowed (section 1) |
| Branch | `main` | |
| Auto-fix | on | Off = find and notify only, no upgrade/PR |
| Owner email | `owner@easystepin.com` | Optional; passed to Boomi |

**What happens next** (watch it live on the scan page):
| # | Stage | What you see |
|---|---|---|
| 1 | clone | Repo downloaded to a temp folder |
| 2 | scan | Languages detected (e.g. Python · deep, JavaScript · text + AI), then total alerts found by OSV (e.g. ~30 on the demo repo), each tagged with CISA KEV + EPSS exploit data |
| 3 | symbols | AI names the dangerous function for each alert (e.g. `yaml.load`) |
| 4 | reachability | Each alert marked reachable / unsure / not reachable, with file:line evidence |
| 5 | risk | Score 0–10 and priority P1–P4 |
| 6 | fix | Per package: upgrade, run tests, AI patch if tests break (max 2 tries) |
| 7 | pr | GitHub PR opened per fixed package |
| 8 | notify | Boomi: Jira issue + Slack alert + compliance row per finding; summary card at the end |

## 4. How to test it (demo repo)
Use the T15 demo repo. Run each check and tick it.

**A. Mock mode first** (`LLM_MODE=mock`, `BOOMI_MODE=mock`, `GITHUB_MODE=mock`) — proves the app without any keys.
- [ ] Overview page loads, stats count up, sidebar badges say `mock`.
- [ ] Run scan → all 8 stages light up in order; log stream moves; ends with `done`.
- [ ] "Languages detected" shows Python (deep) and JavaScript (text + AI).
- [ ] Findings table: ~35 alerts (PyPI + npm); filter "reachable" leaves pyyaml (+ requests) and lodash findings.
- [ ] lodash finding: `tools/report.js` line with `_.template`, analysis chip "Text + AI", fix 4.17.15 → 4.18.0, `npm test` passed.
- [ ] PyYAML finding: P1, evidence `app/routes.py:<line>` highlighted, "in route" tag, AI explanation.
- [ ] Threat chips: "EPSS … top 7%" on PyYAML; no KEV chip (not on the KEV list); `THREAT_INTEL=off` hides chips, scan still works.
- [ ] Fix card: version `5.3.1 → 6.0.x`, attempts shown, tests passed, fake PR link.
- [ ] Integration card: fake Jira key (`SEC-1xx`), Slack sent, compliance id.
- [ ] Integrations page: B2/B3 events appear in the activity feed.
- [ ] Compliance page: row for the PyYAML finding, CSV export downloads.

**B. Live mode** — switch one at a time (CONFIG.md section 7) and repeat the scan.
- [ ] `LLM_MODE=live`: verdicts and explanations come from the real model; still P1 for PyYAML.
- [ ] `GITHUB_MODE=live`: a real PR appears on the demo repo — title `[PatchPilot][P1] ...`, body explains why,
      diff changes `requirements.txt` (+ the AI patch), branch `patchpilot/pyyaml-<version>`.
- [ ] `BOOMI_MODE=live`: real Jira issue (priority Highest, labels `patchpilot`, `security`), Slack message with PR + Jira
      buttons, compliance row; the dashboard shows the real Jira key.
- [ ] Boomi B1 "Execute" starts a scan without touching the dashboard.
- [ ] Whole run from Run scan to Slack alert < 2 minutes.

**C. Negative tests** (should fail safely, not crash)
- [ ] Repo URL outside `ALLOWED_REPO_PREFIXES` → error "repo not allowed", no scan.
- [ ] Wrong/missing `X-API-Key` on `POST /api/scans` from a script → 401.
- [ ] Same repo started twice quickly → second request returns the same scan id.
- [ ] Repo with no tests → finding ends `needs_human`, Slack message says "needs review".
- [ ] Boomi URL wrong / Boomi down → scan still completes; integration event shows failed.
- [ ] Refresh the scan page mid-scan → progress resumes, no lost stages.
- [ ] Demo reset (Shift+R + key) → dashboard empty, demo PR branches removed.

## 5. What to show judges (order)
Run scan → live pipeline + noise funnel (~30 → 2 → 1) → P1 finding evidence → fix card + real PR on GitHub →
Jira issue + Slack message → Compliance page. Script: `docs/DEMO_SCRIPT.md`.
