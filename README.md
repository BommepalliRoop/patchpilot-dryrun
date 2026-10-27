# PatchPilot — AI vulnerability-to-fix autopilot

EasyStepIn AI Hackathon 2026 · Team PatchPilot

> 300 alerts become the 3 that matter — each with a tested fix, a Jira ticket and an audit trail. Automatically, every day.

## Start here
| You are | Read |
|---|---|
| Claude Code (first session) | `CONTEXT.md`, then `CLAUDE.md` |
| Anyone | `docs/DECISIONS.md`, `docs/PLAN.md`, `docs/SETUP.md` |
| Developer using Claude Code | `CLAUDE.md`, then `tasks/BOARD.md` |
| Architect / reviewer | `docs/TECH_STACK.md`, `docs/ARCHITECTURE.md`, `docs/DIAGRAMS.md` |
| Boomi team | `docs/BOOMI_HANDOFF.md` |
| Presenter | `docs/DEMO_SCRIPT.md` |

## How we work on the day
1. Open the repo in Claude Code.
2. Pick your lane in `tasks/BOARD.md`.
3. Open a new session, set the model **and effort** listed for the task (`/model`), then run `/run-task T0X`.
4. When Claude finishes, its NEXT block names the next task, model, effort and command (queue: `tasks/BOARD.md`). Run `/next-task` any time.
