.PHONY: dev backend frontend test lint

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
