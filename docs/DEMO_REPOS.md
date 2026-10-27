# Demo client repos (hand this file to teammates / other AIs)

## Why these repos exist
PatchPilot scans a client's GitHub repo for vulnerable dependencies, decides with AI whether the
vulnerable function is actually reachable from the client's code, scores real risk (OSV + CISA KEV + EPSS),
upgrades the library, runs tests, lets AI patch breakage (max 2 retries), opens a pull request, and
notifies Boomi (Jira ticket, Slack alert, compliance log).

To demo and test that, we need a small set of fake "client" repos on GitHub. Each one is a tiny,
realistic app with deliberately old dependencies. Together they must cover: several languages,
public and private access, reachable vs not-reachable vulnerabilities, a KEV-listed vulnerability,
a test that breaks after the upgrade, and one clean repo that must produce zero findings.

All repos live under the GitHub account `BommepalliRoop`. They are separate from the patchpilot repo.

## Rules for whoever builds them (human or AI)
1. Keep each app small: 5-8 source files, one test command that passes on the OLD versions.
2. Vulnerable code must be intentionally weak but benign: no working exploit payloads, no malware, no real secrets, no real hostnames. Use fake values (`changeme`, `example.com`).
3. Pin exact versions (no ranges) so results are repeatable. Commit lockfiles where the ecosystem has them.
4. After building, run `osv-scanner scan source -r .` (or `--lockfile`) and write the real alert count and the reachable packages into the repo README. Version numbers below were chosen from memory of public advisories; the scanner output is the truth. If a pin shows fewer alerts than expected, bump to an older version.
5. Each repo needs a README with: purpose, how to run tests, expected PatchPilot outcome (table below).
6. Install and tests must work on Windows and Linux (Python 3.11, Node 20, Java 17).
7. Do not add huge-advisory packages (Pillow, Tomcat, Spring Boot full stack). They slow the demo.

## The five repos

| # | Repo name | Visibility | Language | Role in demo |
|---|---|---|---|---|
| 1 | `demo-target` | public | Python (Flask) + small Node tool | Main demo. Already specified in `tasks/T15-demo-target.md`. |
| 2 | `shop-api` | private | Python (FastAPI or Django) | Proves private-repo clone with a token, second Python shape. |
| 3 | `node-inventory` | public | JavaScript (Express) | Node ecosystem, prototype pollution and SSRF style findings. |
| 4 | `billing-service` | private | Java (Maven) | KEV-listed vuln (Log4Shell), shows threat intel scoring. |
| 5 | `clean-service` | public | Python | Zero vulnerabilities. Must end with "no action needed". |

### 1. demo-target (public) — build exactly as `tasks/T15-demo-target.md`
Flask 1.1.2, Werkzeug 1.0.1, Jinja2 2.11.2, PyYAML 5.3.1, requests 2.25.1, urllib3 1.26.4, plus `tools/report.js` with lodash 4.17.15.
Expected: ~33 Python alerts plus 6 lodash alerts. Reachable: PyYAML `yaml.load` in `POST /import` (P1), `requests.get` in a background job (P3/P4). Others not reachable. 2 PRs. One test breaks after the PyYAML upgrade.

### 2. shop-api (private) — Python
Small order API (`POST /orders`, `POST /login`, `GET /health`).
Suggested pins: `Django==3.1.0` or `fastapi` with `starlette==0.14.2`, `PyJWT==1.7.1`, `Jinja2==2.11.2`, `cryptography==3.3.1`, `pytest`.
Make reachable: `jwt.decode(token, SECRET)` called without an explicit `algorithms=` argument in the login/auth code (old PyJWT issue). Make not reachable: Jinja2 and cryptography only pulled in transitively, never called directly.
Expected: 1-2 reachable findings, 1 PR per package, a test that breaks after the PyJWT 2.x upgrade (`jwt.decode` now requires `algorithms`, `jwt.encode` returns `str`), so the AI patch step has real work.
Extra purpose: checks the private-repo path, so PatchPilot needs a GitHub token with `repo` scope (see `docs/CONFIG.md`).

### 3. node-inventory (public) — JavaScript
Small Express API for stock items (`GET /items`, `POST /items`, `POST /fetch-price`).
Suggested pins in `package.json` + committed `package-lock.json`: `express@4.17.1`, `lodash@4.17.20`, `axios@0.21.1`, `jsonwebtoken@8.5.1`, `minimist@1.2.5` (via a CLI helper, not called from the API).
Make reachable: `_.merge(defaults, req.body)` (prototype pollution class), `axios.get(req.body.url)` (SSRF class). Not reachable: minimist only used in a dev script that is not imported by the server.
Test command: `npm test` with `node --test`. One test should break after the axios 1.x upgrade (changed error shape or default import), so AI patch has work.
Expected: reachable findings in 2 packages, 2 PRs.

### 4. billing-service (private) — Java / Maven
Tiny service with `InvoiceService` and a `Main` that logs user-supplied strings.
`pom.xml` pins: `org.apache.logging.log4j:log4j-core:2.14.1` (Log4Shell, CVE-2021-44228, in CISA KEV, very high EPSS), `com.fasterxml.jackson.core:jackson-databind:2.9.8`, `org.yaml:snakeyaml:1.26`. JUnit 5 tests via `mvn -q test`.
Make reachable: `logger.info("invoice for {}", userInput)` and `new ObjectMapper().readValue(...)` on request text.
Expected: log4j finding scores P1 because KEV = true. Note: PatchPilot's deepest reachability is Python; for Java it is "scan + AI" level, same as lodash in repo 1. That is fine and should show up honestly in the UI.
Upgrade target: log4j-core 2.17.1 or newer (2.20.0 is safe). Keep tests simple so the upgrade passes or breaks in one obvious place.

### 5. clean-service (public) — Python, zero vulnerabilities
A small FastAPI or Flask app using current releases only (latest Flask, requests, PyYAML with `yaml.safe_load`, pytest). Include a lockfile or exact pins.
Expected: OSV returns 0 alerts, PatchPilot shows "no vulnerable dependencies", no PR, no Jira ticket, but a compliance log entry is still written ("scan clean"). Before publishing, run osv-scanner and confirm 0; if a new advisory appears, bump the pin.

## Expected PatchPilot outcome (for the demo script and tests)

| Repo | Alerts (approx) | Reachable | Top priority | PRs | Notes |
|---|---|---|---|---|---|
| demo-target | ~39 | 2 packages | P1 (PyYAML) | 2 | AI patches a broken `yaml.load` call |
| shop-api | 10-25 | 1-2 | P1/P2 (PyJWT) | 1-2 | Private clone; AI patches `jwt.decode` |
| node-inventory | 10-20 | 2 | P2 | 2 | Node scan + AI |
| billing-service | 10-30 | 1-2 | P1 (log4j, KEV) | 1-2 | Threat intel (KEV/EPSS) on screen |
| clean-service | 0 | 0 | none | 0 | Clean path, compliance log only |

## How to publish (per repo)
```bash
cd D:\hackathon\<repo-name>
git init -b main
git add . && git commit -m "Initial demo client app"
gh repo create BommepalliRoop/<repo-name> --public   # use --private for shop-api and billing-service
git push -u origin main
```
Then add the URL to `.env` (`DEMO_REPO_URL` for repo 1; the others are entered in the UI) and record the real osv-scanner counts in each README.

## Ready-to-paste prompt for another AI
> Build the repo `<name>` described in section `<n>` of `docs/DEMO_REPOS.md`. Follow the "Rules for whoever builds them". Keep it small. Pin exact versions. Make the tests pass on the old versions. Run osv-scanner and put the real alert count and the reachable packages in the README. Do not include secrets or working exploits.
