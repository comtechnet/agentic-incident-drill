#!/usr/bin/env bash
# Write ops/monitor.env (mode 600) with the Mattermost incoming-webhook URL, as seen from the docker network.
set -euo pipefail
cd "$(dirname "$0")"
secrets="${MM_SECRETS:-$HOME/work/mm-test/.secrets.json}"
url=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["incoming_webhook_url"])' "$secrets")
umask 077
echo "MM_WEBHOOK_URL=${url/127.0.0.1:8065/app:8065}" > monitor.env
echo "monitor.env written"
