// Drill monitor: polls clinic-hours /metrics, posts to Mattermost #incidents (as the 'monitor'
// bot) when the 5xx rate over a sliding window crosses a threshold, and replies in that
// alert's thread on recovery.
// Posts counts and rates only -- never request or response bodies.
const TARGET = process.env.TARGET ?? 'http://clinic-hours:8070';
const MM_URL = process.env.MM_URL ?? 'http://app:8065';
const MM_TOKEN = process.env.MM_BOT_TOKEN;
const CHANNEL = process.env.MM_CHANNEL_ID;
const DISPLAY_TZ = process.env.DISPLAY_TZ || 'UTC';
const POLL_MS = Number(process.env.POLL_MS ?? 5000);
const WINDOW_MS = Number(process.env.WINDOW_MS ?? 30000);
const ALERT_RATE = Number(process.env.ALERT_RATE ?? 0.10);   // alert at >= 10% errors
const CLEAR_RATE = Number(process.env.CLEAR_RATE ?? 0.02);   // recover at < 2% errors
const MIN_REQUESTS = Number(process.env.MIN_REQUESTS ?? 10);
if (!MM_TOKEN || !CHANNEL) { console.error('MM_BOT_TOKEN and MM_CHANNEL_ID are required'); process.exit(1); }

let samples = [];          // { t, requests, errors, version }
let state = 'ok';          // 'ok' | 'alerting'
let alertStartedAt = null;
let alertPostId = null;    // recovery is posted as a reply in the alert's thread

// Post as the 'monitor' bot. Returns the new post's id.
async function post(message, rootId = '') {
  const r = await fetch(`${MM_URL}/api/v4/posts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${MM_TOKEN}` },
    body: JSON.stringify({ channel_id: CHANNEL, message, root_id: rootId }),
  });
  console.log(`posted to Mattermost: HTTP ${r.status}`);
  return r.ok ? (await r.json()).id : null;
}

const when = (d) => d.toLocaleString('en-US', { timeZone: DISPLAY_TZ, month: 'short', day: 'numeric',
  hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' });

function windowStats(now) {
  samples = samples.filter((s) => now - s.t <= WINDOW_MS);
  if (samples.length < 2) return null;
  const a = samples[0], b = samples[samples.length - 1];
  const requests = b.requests - a.requests, errors = b.errors - a.errors;
  return { requests, errors, rate: requests ? errors / requests : 0, version: b.version };
}

const pct = (x) => `${(x * 100).toFixed(0)}%`;

async function tick() {
  const now = Date.now();
  let m;
  try {
    m = await (await fetch(`${TARGET}/metrics`, { signal: AbortSignal.timeout(3000) })).json();
  } catch (e) {
    console.log(`metrics unreachable: ${e.name}`);   // e.g. mid-deploy; don't alert on a blip
    return;
  }
  const last = samples[samples.length - 1];
  if (last && (m.requests < last.requests || m.version !== last.version)) samples = [];  // restart/new version
  samples.push({ t: now, requests: m.requests, errors: m.errors_5xx, version: m.version });

  const w = windowStats(now);
  if (!w || w.requests < MIN_REQUESTS) return;
  console.log(`v${w.version} window=${WINDOW_MS / 1000}s requests=${w.requests} 5xx=${w.errors} rate=${pct(w.rate)} state=${state}`);

  if (state === 'ok' && w.rate >= ALERT_RATE) {
    // Build the message first, change state only once it is posted, so a failure retries next tick.
    const startedAt = new Date();
    const id = await post([
      `#### :rotating_light: ALERT: clinic-hours server errors at ${pct(w.rate)}`,
      `- **Version in production:** v${w.version}`,
      `- **Errors (last ${WINDOW_MS / 1000}s):** ${w.errors} of ${w.requests} requests`,
      `- **Alert threshold:** ${pct(ALERT_RATE)}`,
      `- **Started:** ${when(startedAt)}`,
      ``, `_Synthetic drill. Reply in this thread to coordinate._`,
    ].join('\n'));
    if (id) { state = 'alerting'; alertStartedAt = startedAt; alertPostId = id; }
  } else if (state === 'alerting' && w.rate < CLEAR_RATE) {
    const mins = ((Date.now() - alertStartedAt) / 60000).toFixed(1);
    const id = await post(`#### :white_check_mark: RECOVERED: clinic-hours errors back to ${pct(w.rate)} on v${w.version} (alert lasted ${mins} min, cleared ${when(new Date())})`, alertPostId ?? '');
    if (id) { state = 'ok'; alertPostId = null; }
  }
}

console.log(`monitor watching ${TARGET} every ${POLL_MS / 1000}s`);
setInterval(() => tick().catch((e) => console.log(`tick failed: ${e.name}: ${e.message}`)), POLL_MS);
