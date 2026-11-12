"""Relay between Mattermost #incidents and the GitHub repo. Synthetic drill only.

Mattermost -> GitHub
  "@incident diagnose" (reply in an alert thread)  -> opens an issue that asks @claude to diagnose
  "go" (reply in a tracked thread)                  -> dispatches the gated rollback workflow
  "@incident status" / "/incident status"           -> current production release + open incidents
GitHub -> Mattermost (polled every POLL_S seconds; no inbound connection to this laptop needed)
  Claude's finished replies, rollback run state + approver, then on recovery a timeline comment
  on the issue that asks @claude for the postmortem PR.

Logs metadata only, never message or request bodies.
"""
import http.server
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MM = os.environ.get("MM_URL", "http://app:8065")
CHANNEL = os.environ["MM_CHANNEL_ID"]
RELAY_TOKEN = os.environ["MM_RELAY_BOT_TOKEN"]      # posts relay status
CLAUDE_TOKEN = os.environ["MM_CLAUDE_BOT_TOKEN"]    # posts Claude's replies
MONITOR_USER = os.environ["MM_MONITOR_USER_ID"]
HOOK_TOKENS = {os.environ["MM_OUTGOING_TOKEN"], os.environ["MM_SLASH_TOKEN"]}
ALLOWED_USERS = set(os.environ.get("ALLOWED_MM_USERS", "pilotadmin").split(","))
GH = "https://api.github.com"
GH_WEB = "https://github.com"
GH_REPO = os.environ["GH_REPO"]
GH_TOKEN = os.environ["GH_TOKEN"]
SERVICE = os.environ.get("SERVICE_URL", "http://clinic-hours:8070")
POLL_S = int(os.environ.get("POLL_S", "20"))
STATE_FILE = os.environ.get("STATE_FILE", "/data/state.json")
try:
    TZ = ZoneInfo(os.environ.get("DISPLAY_TZ") or "UTC")
except Exception:
    TZ = timezone.utc
TOWNS = ["Fernhill", "Millbrook", "Cedar Falls", "Ashby", "Quarry Point"]

lock = threading.Lock()


def log(msg):
    print(f"{datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def show(iso):
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%-I:%M:%S %p %Z")


# ---------- state ----------
def load():
    try:
        return json.load(open(STATE_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"incidents": {}}


def save(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_FILE)


# ---------- HTTP helpers ----------
def request(method, url, token=None, body=None, gh=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    if gh:
        req.add_header("Authorization", f"Bearer {GH_TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
    elif token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        log(f"{method} {urllib.parse.urlparse(url).path} -> HTTP {e.code}")
        return e.code, None


def gh(method, path, body=None):
    return request(method, f"{GH}/repos/{GH_REPO}{path}", body=body, gh=True)


def mm_post(message, root_id="", as_claude=False):
    s, p = request("POST", f"{MM}/api/v4/posts", CLAUDE_TOKEN if as_claude else RELAY_TOKEN,
                   {"channel_id": CHANNEL, "message": message, "root_id": root_id})
    return p["id"] if s == 201 else None


# ---------- GitHub facts ----------
def releases():
    """Return (prod_release, previous_release) from the repo's tags."""
    s, tags = gh("GET", "/tags?per_page=100")
    if s != 200:
        return None, None
    by_sha, prod_sha = {}, None
    for t in tags:
        if t["name"] == "prod":
            prod_sha = t["commit"]["sha"]
        elif re.fullmatch(r"v\d+\.\d+", t["name"]):
            by_sha.setdefault(t["commit"]["sha"], []).append(t["name"])
    key = lambda v: tuple(int(x) for x in v[1:].split("."))
    rel = sorted({v for vs in by_sha.values() for v in vs}, key=key)
    cur = max(by_sha.get(prod_sha, []), key=key, default=None)
    prev = rel[rel.index(cur) - 1] if cur in rel and rel.index(cur) > 0 else None
    return cur, prev


def probe():
    rows = []
    for town in TOWNS:
        try:
            with urllib.request.urlopen(f"{SERVICE}/clinics?town={urllib.parse.quote(town)}", timeout=5) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            code = type(e).__name__
        rows.append(f"| {town} | {code} |")
    return "| Town | HTTP status |\n|---|---|\n" + "\n".join(rows)


# ---------- commands ----------
def cmd_diagnose(root_id, user):
    with lock:
        state = load()
        if root_id in state["incidents"]:
            inc = state["incidents"][root_id]
            mm_post(f"Already tracking this as issue #{inc['issue']}.", root_id)
            return
    s, root = request("GET", f"{MM}/api/v4/posts/{root_id}", RELAY_TOKEN)
    alert = root["message"] if s == 200 else "(alert text unavailable)"
    cur, prev = releases()
    title_m = re.search(r"errors at (\d+%)", alert)
    title = f"Incident: clinic-hours server errors{' at ' + title_m.group(1) if title_m else ''} on {cur or 'unknown release'}"
    body = (f"Opened from Mattermost #incidents by `{user}` at {show(now_iso())}. **Synthetic drill.**\n\n"
            f"### Alert\n{alert}\n\n"
            f"### Synthetic probe by the relay\n{probe()}\n\n"
            f"Production release: `{cur}` · previous release: `{prev}`\n\n"
            "@claude Diagnose this incident following CLAUDE.md: confirm the release in production and the "
            "previous release, read the diff between them, relate it to the alert and probe results above, "
            "and recommend an action (name the exact rollback target if you recommend one). "
            "Do not roll back or move tags.")
    s, issue = gh("POST", "/issues", {"title": title, "body": body})
    if s != 201:
        mm_post(f":x: Couldn't open a GitHub issue (HTTP {s}).", root_id)
        return
    with lock:
        state = load()
        state["incidents"][root_id] = {
            "issue": issue["number"], "url": issue["html_url"], "phase": "diagnosing",
            "current": cur, "target": prev, "posted_comments": {},
            "timeline": [["Alert raised", datetime.fromtimestamp(root["create_at"] / 1000, timezone.utc).isoformat(timespec="seconds") if s and root else now_iso()],
                         [f"Diagnosis requested by {user}", now_iso()]],
        }
        save(state)
    log(f"incident opened: issue #{issue['number']}")
    mm_post(f":mag: Opened [issue #{issue['number']}]({issue['html_url']}) and asked Claude to diagnose. "
            f"Its reply will appear here (usually within a minute).", root_id)


def cmd_go(root_id, user):
    with lock:
        state = load()
        inc = state["incidents"].get(root_id)
    if not inc:
        mm_post("This thread isn't a tracked incident. Reply `@incident diagnose` in the alert's thread first.", root_id)
        return
    if inc["phase"] not in ("diagnosed",):
        mm_post(f"Not ready for Go (current step: {inc['phase'].replace('_', ' ')}).", root_id)
        return
    if not inc.get("target"):
        mm_post(":x: No earlier release to roll back to.", root_id)
        return
    reason = f"issue #{inc['issue']}, Go from {user}"
    s, _ = gh("POST", "/actions/workflows/rollback.yml/dispatches",
              {"ref": "main", "inputs": {"target": inc["target"], "reason": reason}})
    if s != 204:
        mm_post(f":x: Couldn't start the rollback workflow (HTTP {s}).", root_id)
        return
    with lock:
        state = load()
        inc = state["incidents"][root_id]
        inc.update(phase="rollback_requested", rollback_requested_at=now_iso(), rollback_reason=reason)
        inc["timeline"].append([f"Go given by {user} in Mattermost", now_iso()])
        save(state)
    log(f"rollback dispatched for issue #{inc['issue']} -> {inc['target']}")
    mm_post(f":arrows_counterclockwise: Rollback to `{inc['target']}` requested. It won't run until it's "
            "approved in GitHub; I'll post the approval link in a moment.", root_id)


def cmd_status():
    cur, _ = releases()
    state = load()
    open_ = [f"#{i['issue']} ({i['phase'].replace('_', ' ')})" for i in state["incidents"].values() if i["phase"] != "done"]
    return f"Production release: `{cur}`. Open incidents: {', '.join(open_) or 'none'}."


# ---------- polling GitHub ----------
CLAUDE_DONE = re.compile(r"Claude (finished|encountered an error)")


def clean_claude(body):
    # Drop the action's header line ("**Claude finished ...** —— [View job](...)") and the rule under it.
    lines = body.splitlines()
    if lines and CLAUDE_DONE.search(lines[0]):
        lines = lines[1:]
    text = re.sub(r"<img[^>]*>", "", "\n".join(lines)).strip()
    return text[3:].strip() if text.startswith("---") else text


def poll_incident(root_id, inc):
    changed = False
    # 1) Claude replies on the issue
    s, comments = gh("GET", f"/issues/{inc['issue']}/comments?per_page=100")
    for c in comments or []:
        if c["user"]["login"] != "github-actions[bot]" or not CLAUDE_DONE.search(c["body"]):
            continue
        if inc["posted_comments"].get(str(c["id"])) == c["updated_at"]:
            continue
        inc["posted_comments"][str(c["id"])] = c["updated_at"]
        changed = True
        mm_post(f"{clean_claude(c['body'])}\n\n_From [issue #{inc['issue']}]({c['html_url']})_", root_id, as_claude=True)
        if inc["phase"] == "diagnosing":
            inc["phase"] = "diagnosed"
            inc["timeline"].append(["Claude posted diagnosis", now_iso()])
            mm_post(f"Reply **Go** in this thread to request a rollback to `{inc['target']}` "
                    "(it still needs approval in GitHub).", root_id)
        elif inc["phase"] == "postmortem":
            inc["phase"] = "awaiting_pr"
            inc["timeline"].append(["Claude posted postmortem", now_iso()])
            m = re.search(r"/tree/(claude/issue-\d+-[\w.-]+)", c["body"])
            if m:
                inc["pm_branch"] = m.group(1)
    # 1b) Postmortem: only call it done once a pull request really exists
    if inc["phase"] == "awaiting_pr":
        s, pulls = gh("GET", "/pulls?state=all&per_page=50")
        pr = next((p for p in pulls or [] if p["head"]["ref"].startswith(f"claude/issue-{inc['issue']}-")), None)
        if pr:
            inc.update(phase="done", pr=pr["number"])
            inc["timeline"].append([f"Postmortem PR #{pr['number']} opened", now_iso()])
            changed = True
            mm_post(f":white_check_mark: Drill complete. Postmortem: [PR #{pr['number']}: {pr['title']}]({pr['html_url']}). "
                    "Review it and merge it in GitHub.", root_id)
        elif not inc.get("warned_pr"):
            inc["warned_pr"] = True
            changed = True
            br = inc.get("pm_branch")
            how = (f"[Open the PR yourself]({GH_WEB}/{GH_REPO}/compare/main...{br}?expand=1) from branch `{br}`."
                   if br else "Check Claude's comment on the issue for the branch.")
            mm_post(f":warning: Claude wrote the postmortem but no pull request exists yet. {how} "
                    "I'll post the PR link here once it's open.", root_id)
    # 2) Rollback run
    if inc["phase"] in ("rollback_requested", "rollback_waiting"):
        s, runs = gh("GET", "/actions/workflows/rollback.yml/runs?event=workflow_dispatch&per_page=10")
        run = next((r for r in (runs or {}).get("workflow_runs", [])
                    if f"issue #{inc['issue']}," in r["display_title"] and r["created_at"] >= inc["rollback_requested_at"][:19]), None)
        if run and inc["phase"] == "rollback_requested":
            inc.update(phase="rollback_waiting", run_id=run["id"], run_url=run["html_url"])
            changed = True
            mm_post(f":lock: Waiting for your approval in GitHub. Open [{run['display_title']}]({run['html_url']}) "
                    "(in the Actions list it's the run with the yellow clock) → **Review deployments** → "
                    "tick **production** → add a comment → **Approve and deploy**.", root_id)
        if run and run["status"] == "completed":
            s, appr = gh("GET", f"/actions/runs/{run['id']}/approvals")
            a = (appr or [{}])[0]
            who = a.get("user", {}).get("login", "unknown")
            note = f' ("{a["comment"]}")' if a.get("comment") else ""
            changed = True
            if run["conclusion"] == "success":
                inc["phase"] = "rolled_back"
                inc["rolled_back_at"] = now_iso()
                inc["timeline"].append([f"Rollback approved by {who}{note}; prod moved to {inc['target']}", now_iso()])
                mm_post(f":white_check_mark: Rollback approved by **{who}**{note}. `prod` now points at "
                        f"`{inc['target']}`; the deployer will redeploy within about 10 seconds. "
                        "Waiting for the monitor to confirm recovery.", root_id)
            else:
                inc["phase"] = "diagnosed"
                inc["timeline"].append([f"Rollback not completed ({run['conclusion']}, {a.get('state', 'no approval')} by {who})", now_iso()])
                mm_post(f":warning: Rollback run ended `{run['conclusion']}` ({a.get('state', 'no approval')} by {who}{note}). "
                        "Reply **Go** to request it again.", root_id)
    # 3) Recovery -> timeline + postmortem request
    if inc["phase"] == "rolled_back":
        s, thread = request("GET", f"{MM}/api/v4/posts/{root_id}/thread", RELAY_TOKEN)
        rec = [p for p in (thread or {}).get("posts", {}).values()
               if p["user_id"] == MONITOR_USER and "RECOVERED" in p["message"]]
        if rec:
            t = datetime.fromtimestamp(min(p["create_at"] for p in rec) / 1000, timezone.utc).isoformat(timespec="seconds")
            inc["timeline"].append(["Monitor confirmed recovery", t])
            rows = "\n".join(f"| {show(ts)} | {what} |" for what, ts in sorted(inc["timeline"], key=lambda x: x[1]))
            body = (f"### Recovered\nThe monitor reports errors back to normal on `{inc['target']}`.\n\n"
                    f"### Timeline ({TZ.key if hasattr(TZ, 'key') else 'UTC'})\n| Time | Event |\n|---|---|\n{rows}\n\n"
                    "@claude Write the postmortem for this incident following CLAUDE.md, using the alert, your "
                    "diagnosis and the timeline above. Open a pull request adding it under `lessons/`.")
            inc["timeline"].pop()   # re-added on success; avoids duplicates across retries
            cs, _ = gh("POST", f"/issues/{inc['issue']}/comments", {"body": body})
            if cs == 201:
                inc["timeline"].append(["Monitor confirmed recovery", t])
                inc["phase"] = "postmortem"
                changed = True
                mm_post(f":memo: Recovery confirmed. I've added the timeline to [issue #{inc['issue']}]({inc['url']}) "
                        "and asked Claude for the postmortem PR.", root_id)
            elif not inc.get("warned_comment"):
                inc["warned_comment"] = True
                changed = True
                mm_post(f":warning: Recovery confirmed, but GitHub refused my comment on issue #{inc['issue']} "
                        f"(HTTP {cs}), so Claude hasn't been asked for the postmortem yet. I'll keep retrying.", root_id)
    return changed


def poller():
    while True:
        try:
            with lock:
                state = load()
            for root_id, inc in list(state["incidents"].items()):
                if inc["phase"] != "done" and poll_incident(root_id, inc):
                    with lock:
                        fresh = load()
                        fresh["incidents"][root_id] = inc
                        save(fresh)
        except Exception as e:
            log(f"poll error: {type(e).__name__}: {e}")
        time.sleep(POLL_S)


# ---------- Mattermost webhooks ----------
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        ctype = self.headers.get("Content-Type", "")
        data = json.loads(raw) if "json" in ctype else {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        log(f"RECV path={self.path} bytes={len(raw)}")
        if data.get("token") not in HOOK_TOKENS:
            return self.reply(403, {"text": "bad token"})
        user = data.get("user_name", "")
        if user not in ALLOWED_USERS:
            return self.reply(200, {})
        if self.path == "/slash":
            return self.reply(200, {"response_type": "ephemeral", "text": cmd_status()})
        text = data.get("text", "").strip()
        s, post = request("GET", f"{MM}/api/v4/posts/{data.get('post_id')}", RELAY_TOKEN)
        root_id = (post or {}).get("root_id") or data.get("post_id")
        low = text.lower()
        if low.startswith("@incident diagnose"):
            threading.Thread(target=cmd_diagnose, args=(root_id, user), daemon=True).start()
        elif re.fullmatch(r"(@incident\s+)?go[.!]?", low):
            threading.Thread(target=cmd_go, args=(root_id, user), daemon=True).start()
        elif low.startswith("@incident status"):
            threading.Thread(target=lambda: mm_post(cmd_status(), root_id if post and post.get("root_id") else ""), daemon=True).start()
        elif low.startswith("@incident"):
            threading.Thread(target=lambda: mm_post("Commands: `@incident diagnose` (in an alert thread), `go`, `@incident status`.", root_id), daemon=True).start()
        self.reply(200, {})

    def reply(self, code, obj):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    threading.Thread(target=poller, daemon=True).start()
    log(f"relay up: repo={GH_REPO} poll={POLL_S}s")
    http.server.ThreadingHTTPServer(("", 8080), Handler).serve_forever()
