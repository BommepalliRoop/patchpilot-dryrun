---
description: Show which PatchPilot tasks are unblocked right now
---
Read `tasks/STATUS.md` and `tasks/BOARD.md`. List:
1. Tasks `in_progress` and who owns them.
2. Tasks whose dependencies are all `done` but are still `todo` — with lane, model and the exact command `/run-task <id>`.
3. Anything blocking the next wave gate, and the fastest way to unblock it (e.g. use a mock mode).
Show model and effort for every task (from its task file header), and remind: start each task in a new session.
Keep it to a short table. Do not change any files.
