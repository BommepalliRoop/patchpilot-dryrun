# Deployment (filled in by T16)

## Target
- Backend: Docker on Render or Railway → `BACKEND_URL`
- Frontend: Vercel → `FRONTEND_URL`, env `VITE_API_BASE_URL=${BACKEND_URL}`
- Fallback: local backend + `cloudflared tunnel --url http://localhost:8000`

## Env vars (backend)
See `.env.example`. Set all `*_MODE` to `mock` first, deploy, check `/api/health`, then switch to `live` one at a time.

## Checklist
- [ ] `/api/health` public
- [ ] CORS allows the Vercel domain
- [ ] Boomi team has BACKEND_URL + PATCHPILOT_API_KEY for B1
- [ ] Frontend shows mode badges as live
