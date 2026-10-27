# T09 — GitHub pull request creator

| Field | Value |
|---|---|
| Owner lane | Dev C |
| Model | Sonnet 5.5 |
| Effort | medium |
| Wave | 3 |
| Depends on | T08 |
| Unblocks | T17 |
| Branch | `t09-github-pr` |

## Goal
Push the fix branch and open a clear PR.

## Scope
- `github_pr.open_pr(repo_url, branch, fix, finding) -> pr_url` with PyGithub; push using token; title `[PatchPilot][{priority}] Fix {cve_id} in {package}` (several CVEs in one package → `Fix {n} CVEs in {package}`, highest priority wins; body lists every CVE).
- PR body from prompt `prompts/pr_description.md` (or template): risk summary, why reachable with file:line, change summary, test results, rollback note, label `security`.
- `GITHUB_MODE=mock` returns a fake URL and writes the body to the DB.

- `fixed_untested` PRs get label `tests-not-run` and a bold line at the top of the body: "PatchPilot could not run this project's tests — please run them before merging."
- **Stretch (only if wave 3 has time):** GitLab merge requests via `python-gitlab` when the repo host is GitLab and `GITLAB_TOKEN` is set; otherwise GitLab repos end as `needs_human` with the diff stored.

## Acceptance criteria
- Live: one real PR opened on the demo repo. Mock: deterministic URL.

## Hardening (docs/RISKS.md)
Implement and test these rows: S4, N11, L7.

## Rules
- Follow CLAUDE.md and docs/API_CONTRACTS.md exactly. Stay inside this task's scope.
- Use mock modes for anything another lane has not finished.

## When done
Update `tasks/STATUS.md`, commit `T09: GitHub pull request creator`, push, and print the NEXT block.
