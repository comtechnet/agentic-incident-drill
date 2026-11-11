#!/usr/bin/env bash
# Build the clinic-hours image for a release tag from the tag's exact contents.
# Usage: ops/build-release.sh v1.3
set -euo pipefail
tag="${1:?usage: build-release.sh <tag>}"
cd "$(git rev-parse --show-toplevel)"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || { echo "no such tag: $tag" >&2; exit 1; }
git archive --format=tar "$tag" | docker build -q -t "clinic-hours:$tag" - >/dev/null
echo "built clinic-hours:$tag"
