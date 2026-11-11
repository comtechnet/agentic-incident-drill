#!/usr/bin/env bash
# Deploy a release: build its image if missing, record it in ops/.env, (re)start the service.
# Usage: ops/deploy.sh v1.3
set -euo pipefail
tag="${1:?usage: deploy.sh <tag>}"
cd "$(dirname "$0")"
docker image inspect "clinic-hours:$tag" >/dev/null 2>&1 || ./build-release.sh "$tag"
echo "PROD_VERSION=$tag" > .env
docker compose up -d --force-recreate --no-deps clinic-hours >/dev/null 2>&1
for _ in $(seq 1 20); do curl -sf http://127.0.0.1:8070/healthz >/dev/null && { echo "deployed $tag: $(curl -s http://127.0.0.1:8070/healthz)"; exit 0; }; sleep 1; done
echo "deploy $tag: service did not become healthy" >&2; exit 1
