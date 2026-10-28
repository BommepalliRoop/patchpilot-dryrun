# Demo script (5 minutes)

1. (30 s) Problem: "Service companies get hundreds of vulnerability alerts. Most are noise; the real ones wait for weeks."
2. (20 s) Show Integrations page: Boomi B1 schedules daily scans for every client repo.
3. (60 s) Click Run scan; point at "Languages detected: Python · JavaScript" — it is not a Python-only tool; on Acme Retail demo repo → live pipeline animates → Noise funnel: ~30 alerts → 2 reachable → 1 P1.
4. (60 s) Open the P1 finding: CVE, the exact line calling yaml.load inside a web route, AI explanation, risk score,
   and the threat chip "EPSS top 7% most likely to be exploited" (CISA KEV is checked too — say: "if it were on the
   government's actively-exploited list, it would jump the queue").
5. (45 s) Fix card: version upgraded, AI patched one broken call, tests passed → open the real GitHub PR.
6. (45 s) Boomi results: Jira ticket created, Slack alert in the channel, compliance log row (show B4 page).
7. (20 s) Close: "Every client, every day, no manual triage. 300 alerts become the 3 that matter — already fixed."

Backup: if live services fail, flip to `*_MODE=mock` and run the seeded demo (`python -m app.seed --reset`). Keep a screen recording of a full run. Step by step: `docs/RUNBOOK.md`.

## If a judge asks: "Is it safe to auto-fix?" (RISKS O4)
Say it in 20 seconds, in this order:
1. **Never auto-merged.** PatchPilot only opens a pull request; a human reviews and merges it.
2. **Tests must pass.** The upgrade runs the repo's own test suite; if it still fails after 2 AI retries the finding is `needs_human` and the PR is labelled `tests-not-run` / not presented as fixed.
3. **The AI patch is fenced in (S6).** It may only touch `.py` files named in the failing traceback (or that import the package) plus the package's requirements line; never `tests/`, `.github/`, `setup.py`, `conftest.py`; max 200 changed lines; no `..` or absolute paths.
4. **Everything is audited.** Each finding creates a Jira ticket (B2) and a compliance-log row (B4) that can be exported.
