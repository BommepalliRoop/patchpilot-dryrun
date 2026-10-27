# Demo script (5 minutes)

1. (30 s) Problem: "Service companies get hundreds of vulnerability alerts. Most are noise; the real ones wait for weeks."
2. (20 s) Show Integrations page: Boomi B1 schedules daily scans for every client repo.
3. (60 s) Click Run scan on Acme Retail demo repo → live pipeline animates → Noise funnel: 12 alerts → 2 reachable → 1 P1.
4. (60 s) Open the P1 finding: CVE, the exact line calling yaml.load inside a web route, AI explanation, risk score.
5. (45 s) Fix card: version upgraded, AI patched one broken call, tests passed → open the real GitHub PR.
6. (45 s) Boomi results: Jira ticket created, Teams alert in the channel, compliance log row (show B4 page).
7. (20 s) Close: "Every client, every day, no manual triage. 300 alerts become the 3 that matter — already fixed."

Backup: if live services fail, flip to `*_MODE=mock` and run the seeded demo (T17 seed). Keep a screen recording of a full run.
