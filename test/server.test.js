import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/server.js';

let server, base;
before(async () => {
  server = createApp().listen(0);
  await new Promise((r) => server.once('listening', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

test('healthz reports version', async () => {
  const r = await fetch(`${base}/healthz`);
  assert.equal(r.status, 200);
  assert.match((await r.json()).version, /^\d+\.\d+\.\d+$/);
});

test('clinics requires town', async () => {
  assert.equal((await fetch(`${base}/clinics`)).status, 400);
});

test('clinics lookup succeeds', async () => {
  const r = await fetch(`${base}/clinics?town=Millbrook`);
  assert.equal(r.status, 200);
  assert.ok((await r.json()).clinics.length > 0);
});

test('metrics counts requests', async () => {
  const m = await (await fetch(`${base}/metrics`)).json();
  assert.ok(m.requests >= 2);
  assert.equal(m.errors_5xx, 0);
});
