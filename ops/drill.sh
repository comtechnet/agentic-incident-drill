#!/usr/bin/env bash
# Drill control. Usage: ops/drill.sh up | down | status
#   up     start Mattermost sandbox, production (current prod tag), traffic, monitor, deployer
#   down   stop everything (data in Docker volumes is kept)
#   status show what's running and what's deployed
set -euo pipefail
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"; cd "$root"
mm="$HOME/work/mm-test"
deployer_pid() { pgrep -f "$root/ops/deployer.sh|ops/deployer.sh" | head -1; }
case "${1:-status}" in
  up)
    (cd "$mm" && docker compose up -d >/dev/null 2>&1)
    for _ in $(seq 1 40); do curl -sf http://127.0.0.1:8065/api/v4/system/ping >/dev/null && break; sleep 3; done
    [ -f ops/monitor.env ] || ops/init-monitor.sh
    git rev-parse -q --verify refs/tags/prod >/dev/null || git tag prod 'v1.3^{}'
    ops/deploy.sh "$(git tag --points-at prod | grep -E '^v[0-9]+\.[0-9]+$' | sort -V | tail -1)"
    docker compose -f ops/compose.yaml up -d --build loadgen monitor >/dev/null 2>&1
    if [ -f ops/relay.env ]; then docker compose -f ops/compose.yaml up -d --build relay >/dev/null 2>&1
    else echo "relay not configured yet: run ops/init-relay.sh"; fi
    [ -n "$(deployer_pid)" ] || { setsid nohup ops/deployer.sh >> ops/deployer.log 2>&1 < /dev/null & disown; }
    "$0" status ;;
  down)
    pid=$(deployer_pid); [ -n "$pid" ] && kill "$pid" && echo "deployer stopped"
    docker compose -f ops/compose.yaml stop >/dev/null 2>&1 && echo "production, traffic, monitor stopped"
    (cd "$mm" && docker compose stop >/dev/null 2>&1) && echo "Mattermost stopped" ;;
  status)
    echo "prod tag  -> $(git tag --points-at prod 2>/dev/null | grep -E '^v' | tr '\n' ' ')"
    echo "deployed  -> $(curl -s --max-time 2 http://127.0.0.1:8070/healthz || echo 'not running')"
    echo "deployer  -> $( [ -n "$(deployer_pid)" ] && echo "running (pid $(deployer_pid))" || echo stopped)"
    docker ps --filter name=drill-prod --filter name=mm-pilot --format '{{.Names}}\t{{.Status}}' ;;
  *) echo "usage: $0 up|down|status" >&2; exit 2 ;;
esac
