#!/bin/sh
# RISKS N10: wake the deployed backend before a demo. Usage: scripts/warmup.sh https://your-backend
url="${1%/}/api/health"
for i in $(seq 1 12); do
  if curl -fsS --max-time 15 "$url"; then echo; exit 0; fi
  echo "attempt $i failed, retrying in 10 s"; sleep 10
done
echo "backend did not answer at $url" >&2; exit 1
