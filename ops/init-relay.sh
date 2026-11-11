#!/usr/bin/env bash
# Write ops/relay.env (mode 600). Reads Mattermost values from the sandbox's .secrets.json and
# prompts for the GitHub fine-grained token with hidden input (never echoed, never in shell history).
# Re-run any time to replace the GitHub token (e.g. after it expires).
set -euo pipefail
cd "$(dirname "$0")"
secrets="${MM_SECRETS:-$HOME/work/mm-test/.secrets.json}"
repo="$(git remote get-url origin | sed -E 's#.*github.com[:/]##; s#\.git$##')"
mm_vals=$(python3 - "$secrets" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for k, v in [("MM_CHANNEL_ID", "channel_id"), ("MM_RELAY_BOT_TOKEN", "relay_bot_token"),
             ("MM_CLAUDE_BOT_TOKEN", "bot_token"), ("MM_MONITOR_USER_ID", "monitor_bot_user_id"),
             ("MM_OUTGOING_TOKEN", "outgoing_webhook_token"), ("MM_SLASH_TOKEN", "slash_command_token")]:
    print(f"{k}={d[v]}")
PY
)
read -rsp "Paste the GitHub fine-grained token for $repo (input hidden): " ghtok; echo
[[ "$ghtok" == github_pat_* ]] || { echo "That doesn't look like a fine-grained token (should start with github_pat_)." >&2; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ghtok" "https://api.github.com/repos/$repo/issues?per_page=1")
[ "$code" = 200 ] || { echo "Token check failed: GitHub returned HTTP $code for $repo. Received ${#ghtok} characters (a complete fine-grained token is usually 93)." >&2
  [ "$code" = 401 ] && echo "401 = GitHub didn't recognise the token: usually an incomplete paste. Use GitHub's copy button and paste again." >&2
  exit 1; }
tz="${DISPLAY_TZ:-$(sed -n 's/^DISPLAY_TZ=//p' monitor.env 2>/dev/null)}"
umask 077
{ echo "MM_URL=http://app:8065"; echo "$mm_vals"; echo "GH_REPO=$repo"; echo "GH_TOKEN=$ghtok"
  echo "DISPLAY_TZ=${tz:-UTC}"; echo "ALLOWED_MM_USERS=pilotadmin"; } > relay.env
unset ghtok
echo "relay.env written (mode 600). Token verified against $repo."
