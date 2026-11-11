#!/usr/bin/env bash
# Deployer: keeps production on whatever release the `prod` git tag points at.
# Polls every 10s. If the repo has an `origin` remote, fetches tags first (step 3: GitHub moves `prod`).
# Usage: ops/deployer.sh        (runs until stopped; logs to stdout)
set -uo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
current() { sed -n 's/^PROD_VERSION=//p' ops/.env 2>/dev/null; }
echo "deployer: watching tag 'prod' (currently deployed: $(current || echo none))"
while true; do
  git remote get-url origin >/dev/null 2>&1 && git fetch -q --force origin 'refs/tags/*:refs/tags/*' 2>/dev/null
  if git rev-parse -q --verify refs/tags/prod >/dev/null; then
    want=$(git tag --points-at prod | grep -E '^v[0-9]+\.[0-9]+$' | sort -V | tail -1)
    if [ -z "$want" ]; then
      echo "$(date -u +%FT%TZ) prod points at a commit with no release tag; ignoring"
    elif [ "$want" != "$(current)" ]; then
      echo "$(date -u +%FT%TZ) prod moved: $(current || echo none) -> $want"
      ops/deploy.sh "$want"
    fi
  fi
  sleep 10
done
