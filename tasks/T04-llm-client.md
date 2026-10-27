# T04 — Provider-agnostic LLM client

| Field | Value |
|---|---|
| Owner lane | Dev B |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 1 |
| Depends on | T00 |
| Unblocks | T05, T06, T08 |
| Branch | `t04-llm-client` |

## Goal
One place for all model calls.

## Scope
- `llm.complete_json(prompt_name, variables, schema: type[BaseModel]) -> BaseModel`: loads `backend/app/prompts/<prompt_name>.md`, fills `{{variables}}`, calls provider, extracts JSON (strip code fences), validates, retries once with the validation error appended.
- Providers: `anthropic` and `openai` via httpx (selected by LLM_PROVIDER), model from LLM_MODEL. Timeouts 60 s.
- `LLM_MODE=mock`: returns deterministic canned JSON per prompt_name from `backend/app/prompts/mocks/<prompt_name>.json`.
- Log token usage and latency per call.

## Acceptance criteria
- Mock mode returns valid objects for prompts: extract_symbols, reachability_verdict, patch_code, pr_description.
- Live mode tested once with the kickoff key (manual).

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T04: Provider-agnostic LLM client`, push, and print the NEXT block.
