.PHONY: dev backend frontend test lint seed e2e

# Windows without make: powershell -File scripts/dev.ps1
PY ?= python

dev:
	@$(MAKE) -j2 backend frontend

backend:
	cd backend && $(PY) -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && $(PY) -m pytest -q
	cd frontend && npm run build

lint:
	cd backend && $(PY) -m ruff check app tests
	cd frontend && npm run lint

# T17 demo tools (docs/RUNBOOK.md)
seed:
	cd backend && $(PY) -m app.seed --reset

e2e:
	cd backend && $(PY) -m app.e2e
