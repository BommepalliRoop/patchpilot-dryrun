# Task board — who runs what, in which order

## Lanes (dev team)
| Lane | Person | Tasks in order |
|---|---|---|
| Lead | Roop | T00 → (help) → T17 → T18 |
| Dev A — backend core | ___ | T01 → T02 → T03 |
| Dev B — AI | ___ | T04 → T05 → T07 → T06 |
| Dev C — fix + integration + deploy | ___ | T10 → T08 → T09 → T16 |
| Dev D — UI | ___ | T11 → T12 → T13 → T14 |
| Dev E / presenter (if you have a 5th dev) | ___ | T15 → demo prep; otherwise Lead does T15 right after T00 |
| Boomi team (3–4) | ___ | B2 → B1 → B3 → B4 (docs/BOOMI_HANDOFF.md) |

If you have fewer developers, merge lanes A+B or C+E. Never merge two UI tasks with backend tasks on one person.

## Waves (Oct 28)
| Wave | Time | Parallel tasks | Gate to next wave |
|---|---|---|---|
| 0 | 9:20–9:35 | T00 (Lead only). Others: install deps, paste kickoff keys into `.env`, Boomi team starts B2 | T00 merged to main |
| 1 | 9:35–10:30 | T01, T02, T04, T10, T11, T15, Boomi B2 | each task's acceptance passes |
| 2 | 10:30–11:20 | T03, T05, T07, T06, T08, T12, T13, Boomi B1 | pipeline runs end-to-end in mock mode |
| 3 | 11:20–11:50 | T09, T14, T16, Boomi B3/B4, switch BOOMI_MODE=live | public URLs + live Boomi |
| 4 | 11:50–12:15 | T17, T18 | two clean rehearsals |
| — | 12:20 | Code freeze | |

## Dependency graph
```
T00 ─┬─ T01 ─┐
     ├─ T02 ─┴─ T03 ───────────────┐
     ├─ T04 ─┬─ T05 ── T06 ────────┤
     │       └─ T08 ── T09 ────────┤
     ├─ T07 ───────────────────────┤
     ├─ T10 ───────────────────────┼── T17 ── T18
     ├─ T11 ─┬─ T12 ───────────────┤
     │       ├─ T13 ───────────────┤
     │       └─ T14 ───────────────┤
     ├─ T15 (separate repo) ───────┤
     └─ T16 (after T03 + T11) ─────┘
Boomi: B2 → B1 → B3 → B4  (contract-only dependency; mocks until live)
```

## Model and effort guide
| Model | Effort | Use for | Tasks |
|---|---|---|---|
| Opus 5.5 | high | Hard reasoning, orchestration, tricky correctness | T03, T06, T08, T17 |
| Sonnet 5.5 | high | Foundation every lane depends on (signatures must be exact) | T00 |
| Sonnet 5.5 | medium | Normal feature work and UI | T01, T02, T04, T05, T09, T10, T11, T12, T13, T16, T18 |
| Haiku 5.5 | low | Small, well-defined tasks | T07, T14, T15 |

Why not `xhigh`/`max`: the sprint is 3 hours. Higher effort is slower and rarely needed for these scopes.
Only raise effort if a task fails its acceptance tests twice in a row.

Setting them in Claude Code: pick model and effort in the `/model` picker (CLI) or the model menu (desktop app)
**before** typing `/run-task`. Each task file also lists its model and effort in its header table.

## One task = one fresh session
Start every task in a **new Claude Code session** (CLI: `/clear` or a new `claude`; desktop app: New session).
A clean context is faster and cheaper, and each task file plus CLAUDE.md carries all the context needed.

## Task queue — what to run after each task
When a task is done, open a new session, set the model and effort from this table, and paste the command.

| Done | Next in same lane | Model | Effort | Command | Also unblocked for other lanes |
|---|---|---|---|---|---|
| T00 | T15 (only if no Dev E), else help others | Haiku 5.5 | low | `/run-task T15` | T01, T02, T04, T07, T10, T11 |
| T01 | T02 | Sonnet 5.5 | medium | `/run-task T02` | T10 event logging |
| T02 | T03 (needs T01 done) | Opus 5.5 | high | `/run-task T03` | — |
| T03 | Help T17 prep (run full mock scan) | — | — | `/next-task` | T16 (with T11) |
| T04 | T05 | Sonnet 5.5 | medium | `/run-task T05` | T08 |
| T05 | T07 | Haiku 5.5 | low | `/run-task T07` | T06 |
| T07 | T06 | Opus 5.5 | high | `/run-task T06` | — |
| T06 | Tune prompts on the demo target | — | — | `/next-task` | T17 (part) |
| T10 | T08 (needs T04 done) | Opus 5.5 | high | `/run-task T08` | — |
| T08 | T09 | Sonnet 5.5 | medium | `/run-task T09` | — |
| T09 | T16 (needs T03 + T11 done) | Sonnet 5.5 | medium | `/run-task T16` | T17 (part) |
| T16 | Share BACKEND_URL with Boomi team, help T17 | — | — | `/next-task` | Boomi B1 live |
| T11 | T12 | Sonnet 5.5 | medium | `/run-task T12` | T13, T14 |
| T12 | T13 | Sonnet 5.5 | medium | `/run-task T13` | — |
| T13 | T14 | Haiku 5.5 | low | `/run-task T14` | — |
| T14 | UI polish list for T18 | — | — | `/next-task` | — |
| T15 | Demo prep (`docs/DEMO_SCRIPT.md`) | — | — | `/next-task` | T02/T06/T08 real-target tests |
| T17 (all of wave 2–3 done first) | T18 | Sonnet 5.5 | medium | `/run-task T18` | everyone joins T18 |
| T18 | Code freeze 12:20 | — | — | — | — |

The `/run-task` command prints the same information in its NEXT block, computed from the live `tasks/STATUS.md`.

## How to run a task
```
# 1. new session   2. set model + effort from the table   3. run:
/run-task T06
```
or paste this prompt:
```
Read CLAUDE.md, docs/ARCHITECTURE.md, docs/API_CONTRACTS.md and tasks/T06-reachability.md.
Implement T06 exactly within its scope. Create branch t06-reachability. Mark it in_progress in tasks/STATUS.md.
Write tests for every acceptance criterion and run them. When all pass, update STATUS.md to done,
commit "T06: Reachability analyzer (AST + AI)", push, and end with the NEXT block.
```
When Claude ends, it prints which tasks are now unblocked. Run `/next-task` any time to see it again.
