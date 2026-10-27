# PatchPilot backend image (T16). Build from the repo root:
#   docker build -f backend/Dockerfile -t patchpilot-api .
# RISKS S2: no .env is copied in (see .dockerignore); configuration comes only from host env vars.
FROM node:20-slim AS node

FROM python:3.11-slim

ARG OSV_SCANNER_VERSION=2.7.0
ARG OSV_SCANNER_SHA256_AMD64=160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b
ARG OSV_SCANNER_SHA256_ARM64=4061ef4c021ed3c47f203b818f337e351336cc5cd67c0274fc36bd1dfc728dd7
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# pinned osv-scanner release, checksum verified
RUN set -eu; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$arch" in \
      amd64) sha="$OSV_SCANNER_SHA256_AMD64" ;; \
      arm64) sha="$OSV_SCANNER_SHA256_ARM64" ;; \
      *) echo "unsupported arch $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/osv-scanner \
      "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_${arch}"; \
    echo "${sha}  /usr/local/bin/osv-scanner" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/osv-scanner

# Node.js 20 + npm for the npm fix adapter
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN useradd --create-home --uid 10001 patchpilot \
    && mkdir -p /data /tmp/patchpilot \
    && chown patchpilot:patchpilot /data /tmp/patchpilot

WORKDIR /srv/app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN chown -R patchpilot:patchpilot /srv

ENV WORK_DIR=/tmp/patchpilot \
    DATABASE_URL=sqlite:////data/patchpilot.db \
    PYTHONUNBUFFERED=1 \
    PORT=8000

USER patchpilot
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=4)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
