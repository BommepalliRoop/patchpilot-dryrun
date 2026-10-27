# Setup checklist (do tonight, test before 8:30 AM)

## Every developer
- [ ] Node 20+, Python 3.11, Git, Docker (optional), VS Code
- [ ] Claude Code installed and logged in; open repo folder and run `claude`
- [ ] GitHub CLI: `gh auth login` (lets Claude Code push branches and open PRs)
- [ ] OSV-Scanner installed (`osv-scanner --version`)
- [ ] Repo cloned; read CLAUDE.md and your lane in tasks/BOARD.md

## Claude Code add-ons (optional, test tonight)
- [ ] A docs MCP server (e.g. Context7) for up-to-date library docs (Motion, FastAPI, shadcn/ui)
- [ ] Playwright MCP server so Claude can open and check the UI in a browser
- [ ] frontend-design plugin, if available in your plugin marketplace
- Multiple folders: start `claude` in a parent folder, or use `/add-dir <path>` / `--add-dir <path>`

## Lead / shared accounts
- [ ] GitHub repo for PatchPilot + separate demo-target repo
- [ ] Render or Railway account (backend), Vercel account (frontend), cloudflared installed (fallback)
- [ ] Jira project key for Boomi B2, Slack incoming webhook URL
- [ ] Boomi team has access to Boomi + docs/BOOMI_HANDOFF.md
- [ ] Demo library versions confirmed on osv.dev
