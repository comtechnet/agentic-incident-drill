#!/usr/bin/env bash
# Write ops/monitor.env (mode 600): monitor bot token, #incidents channel, display time zone.
# Local only (gitignored) -- the time zone is a personal setting and stays out of the repo.
set -euo pipefail
cd "$(dirname "$0")"
secrets="${MM_SECRETS:-$HOME/work/mm-test/.secrets.json}"
read -r token channel < <(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["monitor_bot_token"],d["channel_id"])' "$secrets")
tz="${DISPLAY_TZ:-$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)}"
umask 077
printf 'MM_URL=http://app:8065\nMM_BOT_TOKEN=%s\nMM_CHANNEL_ID=%s\nDISPLAY_TZ=%s\n' "$token" "$channel" "$tz" > monitor.env
echo "monitor.env written (display time zone: $tz)"
