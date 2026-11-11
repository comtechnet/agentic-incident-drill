import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { findByTown, towns } from './clinics.js';

const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
const metrics = { requests: 0, errors_5xx: 0, latency_ms_total: 0, started_at: new Date().toISOString() };

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function route(req, res) {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/healthz') return send(res, 200, { ok: true, version: VERSION });
  if (url.pathname === '/metrics') {
    const avg = metrics.requests ? metrics.latency_ms_total / metrics.requests : 0;
    return send(res, 200, { version: VERSION, ...metrics, avg_latency_ms: Number(avg.toFixed(2)) });
  }
  if (url.pathname === '/towns') return send(res, 200, { towns: towns() });
  if (url.pathname === '/clinics') {
    const town = url.searchParams.get('town');
    if (!town) return send(res, 400, { error: 'town query parameter is required' });
    return send(res, 200, { town, clinics: findByTown(town) });
  }
  return send(res, 404, { error: 'not found' });
}

export function createApp() {
  return createServer((req, res) => {
    const start = performance.now();
    const counted = !['/healthz', '/metrics'].includes(new URL(req.url, 'http://localhost').pathname);
    res.on('finish', () => {
      if (!counted) return;
      metrics.requests += 1;
      metrics.latency_ms_total += performance.now() - start;
      if (res.statusCode >= 500) metrics.errors_5xx += 1;
    });
    try {
      route(req, res);
    } catch (err) {
      // Log the error type and route only; never request bodies or query values.
      console.error(`500 on ${new URL(req.url, 'http://localhost').pathname}: ${err.name}: ${err.message}`);
      send(res, 500, { error: 'internal error' });
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.PORT ?? 8070);
  createApp().listen(port, () => console.log(`clinic-hours v${VERSION} listening on :${port}`));
}
