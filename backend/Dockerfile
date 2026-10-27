# Placeholder (T16 finalises: osv-scanner, Node.js, non-root user, no .env baked in — RISKS S2).
FROM python:3.11-slim

WORKDIR /srv/app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .

ENV WORK_DIR=/tmp/patchpilot
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
