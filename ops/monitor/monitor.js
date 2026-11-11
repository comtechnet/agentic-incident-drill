// Drill monitor: polls clinic-hours /metrics, posts to Mattermost #incidents when the
// 5xx rate over a sliding window crosses a threshold, and posts again on recovery.
// Posts counts and rates only -- never request or response bodies.
const TARGET = process.env.TARGET ?? 'http://clinic-hours:8070';
const WEBHOOK = process.env.MM_WEBHOOK_URL;
const POLL_MS = Number(process.env.POLL_MS ?? 5000);
const WINDOW_MS = Number(process.env.WINDOW_MS ?? 30000);
const ALERT_RATE = Number(process.env.ALERT_RATE ?? 0.10);   // alert at >= 10% errors
const CLEAR_RATE = Number(process.env.CLEAR_RATE ?? 0.02);   // recover at < 2% errors
const MIN_REQUESTS = Number(process.env.MIN_REQUESTS ?? 10);
if (!WEBHOOK) { console.error('MM_WEBHOOK_URL is required'); process.exit(1); }

let samples = [];          // { t, requests, errors, version }
let state = 'ok';          // 'ok' | 'alerting'
let alertStartedAt = null;

async function post(text) {
  const r = await fetch(WEBHOOK, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }) });
  console.log(`posted to Mattermost: HTTP ${r.status}`);
}

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
    state = 'alerting'; alertStartedAt = new Date();
    await post([
      `#### :rotating_light: ALERT: clinic-hours server errors at ${pct(w.rate)}`,
      `| | |`, `|---|---|`,
      `| Version in production | v${w.version} |`,
      `| Errors (last ${WINDOW_MS / 1000}s) | ${w.errors} of ${w.requests} requests |`,
      `| Threshold | ${pct(ALERT_RATE)} |`,
      `| Started | ${alertStartedAt.toISOString()} |`,
      ``, `_Synthetic drill. Reply in this thread to coordinate._`,
    ].join('\n'));
  } else if (state === 'alerting' && w.rate < CLEAR_RATE) {
    const mins = ((Date.now() - alertStartedAt) / 60000).toFixed(1);
    state = 'ok';
    await post(`#### :white_check_mark: RECOVERED: clinic-hours errors back to ${pct(w.rate)} on v${w.version} (alert lasted ${mins} min)`);
  }
}

console.log(`monitor watching ${TARGET} every ${POLL_MS / 1000}s`);
setInterval(() => tick().catch((e) => console.log(`tick failed: ${e.name}: ${e.message}`)), POLL_MS);
