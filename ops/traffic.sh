#!/usr/bin/env bash
# Send N lookups spread across all five fictional towns; print status-code counts.
# Usage: ops/traffic.sh [N]   (default 50)
set -euo pipefail
n="${1:-50}"; towns=(Fernhill Millbrook "Cedar%20Falls" Ashby "Quarry%20Point")
for i in $(seq 1 "$n"); do
  curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8070/clinics?town=${towns[$((i % 5))]}"
done | sort | uniq -c
