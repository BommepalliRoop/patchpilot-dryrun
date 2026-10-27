# Boomi artefacts

Owned by the Boomi team. Boomi processes live in the Boomi platform; this folder holds their documentation
so the repo shows the whole solution. How to contribute: `docs/BOOMI_HANDOFF.md` section 11.

| Folder | Process | Status |
|---|---|---|
| `B0/` | Setup: runtime, listener, auth, connections | todo |
| `B1/` | Daily scan trigger (Boomi → PatchPilot) | todo |
| `B2/` | Finding notification → Jira + Slack + compliance log | todo |
| `B3/` | Scan summary → Slack message | todo |
| `B4/` | Compliance report | todo |

Each folder: `README.md` (what it does, shapes, connections — no secrets), `screenshot.png` (process canvas),
`sample-response.json` (real response from a test call), and an XML export if your account allows it.

Never commit tokens, passwords, API keys or webhook URLs.
