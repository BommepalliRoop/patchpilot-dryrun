# Dry run — practice the full build today (Oct 27)

Goal: run tomorrow's 3-hour sprint today with the whole team (dev lanes + Boomi team), measure how long each
task really takes, find blockers, and fix the **plan** (not keep the code).

## ⚠ Rule: practice code must not be reused tomorrow
The hackathon says all code is written during the event. So:
- Dev team builds in a **separate throwaway repo** `BommepalliRoop/patchpilot-dryrun` (a copy of today's planning
  docs), **never** in `BommepalliRoop/patchpilot`. Nothing from the dry-run repo is copied, merged or pushed into
  `patchpilot`. Tomorrow everyone starts from a clean clone of `patchpilot`.
- Boomi team builds in a separate Boomi folder named `DRYRUN - PatchPilot` and does not reuse those processes
  tomorrow (rebuilding is faster the second time — that is the point of practice).
- Only **lessons** come back: timings, prompt fixes, plan changes → we update the planning docs in `patchpilot`.
- Ask the organisers if a rehearsal is fine. If they say no, stop and only do the setup checklist.

## What to share
| Who | File |
|---|---|
| Boomi team | `docs/BOOMI_HANDOFF.md` (+ `contracts/boomi/*.json`) |
| Dev team | `CLAUDE.md`, `tasks/BOARD.md`, this file |
| Whoever collects keys | `docs/CONFIG.md` |

## Setup (30 min before starting)
1. Lead creates `patchpilot-dryrun` (private) and pushes the current `patchpilot` main to it:
   ```bash
   git clone https://github.com/BommepalliRoop/patchpilot.git patchpilot-dryrun
   cd patchpilot-dryrun
   git remote set-url origin https://github.com/BommepalliRoop/patchpilot-dryrun.git
   git push -u origin main
   ```
2. Also create a throwaway `demo-target-dryrun` repo for T15.
3. Everyone clones `patchpilot-dryrun`, opens it in Claude Code, checks `docs/SETUP.md` items.
4. LLM key: no kickoff keys today — use a team member's own key, or run everything with `LLM_MODE=mock`
   (that is also a real test of the mock paths).
5. Boomi team: Boomi access, Jira project, Slack channel + webhook, compliance log store (BOOMI_HANDOFF section 3–4).

## Schedule (same as tomorrow, shift the clock to your start time)
| Wave | Minutes from start | Dev team | Boomi team |
|---|---|---|---|
| 0 | 0–15 | Lead: T00 | B0 setup |
| 1 | 15–70 | T01 T02 T04 T10 T11 T15 | B0 → B2 |
| 2 | 70–120 | T03 T05 T07 T06 T08 T12 T13 | B2 test with curl, then B1 |
| 3 | 120–150 | T09 T14 T16, switch modes to live | B1 → our BACKEND_URL, B3, B4 |
| 4 | 150–175 | T17 T18, full demo twice | watch Jira/Slack/log during demo |
| — | 180 | Stop. Retro (15 min) | Retro |

Run each task exactly like tomorrow: new session → model + effort from BOARD.md → `/run-task Txx` → follow the NEXT block.

## Timing log (fill in live — this is the main output)
| Task | Person | Model / effort | Start | End | Minutes | Planned (wave) | Blocked by / problems | Fix for tomorrow |
|---|---|---|---|---|---|---|---|---|
| T00 | | Sonnet / high | | | | 15 | | |
| T01 | | Sonnet / medium | | | | 55 | | |
| T02 | | Sonnet / medium | | | | 55 | | |
| T04 | | Sonnet / medium | | | | 55 | | |
| T10 | | Sonnet / medium | | | | 55 | | |
| T11 | | Sonnet / medium | | | | 55 | | |
| T15 | | Haiku / low | | | | 55 | | |
| T03 | | Opus / high | | | | 50 | | |
| T05 | | Sonnet / medium | | | | 50 | | |
| T07 | | Haiku / low | | | | 50 | | |
| T06 | | Opus / high | | | | 50 | | |
| T08 | | Opus / high | | | | 50 | | |
| T12 | | Sonnet / medium | | | | 50 | | |
| T13 | | Sonnet / medium | | | | 50 | | |
| T09 | | Sonnet / medium | | | | 30 | | |
| T14 | | Haiku / low | | | | 30 | | |
| T16 | | Sonnet / medium | | | | 30 | | |
| T17 | | Opus / high | | | | 25 | | |
| T18 | | Sonnet / medium | | | | 25 | | |
| B0 | | Boomi Companion | | | | 40 | | |
| B2 | | Boomi Companion | | | | 75 | | |
| B1 | | Boomi Companion | | | | 30 | | |
| B3 | | Boomi Companion | | | | 30 | | |
| B4 | | Boomi Companion | | | | 30 | | |

Also note: wave gate times actually hit, first time the full pipeline ran in mock mode, first live Jira ticket,
demo run length, LLM cost/tokens if visible, any RISKS.md must-have that did not fit.

## Retro questions (15 min)
1. Which tasks overran? Split them, move scope out, or change model/effort?
2. Where did lanes wait on each other? Did mock mode really unblock them?
3. Which task-file instructions were unclear or wrong? (Fix the task file.)
4. Did any contract field cause a mismatch between backend, frontend or Boomi? (Fix API_CONTRACTS.md + contracts/.)
5. Boomi: which step took longest (auth, Jira, Slack, log)? What should be prepared tonight?
6. Is the demo under 5 minutes and still impressive?

## After the dry run
- Lead updates the planning docs in `patchpilot` (task files, BOARD timings, contracts, handoff) and pushes.
- Archive or delete `patchpilot-dryrun` and `demo-target-dryrun`; Boomi team leaves the DRYRUN folder alone.
- **Reset the Supabase database password** (Project Settings → Database) if it was shared during the practice, and send the
  new one privately to the Boomi team. Empty the practice rows: `DELETE FROM compliance_log;` (practice data only).
- Tomorrow: fresh clone of `patchpilot`, fresh `demo-target`, start at 9:20 with `/run-task T00`.
