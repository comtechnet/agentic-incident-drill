import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { findByTown, formatHours, toResult, towns } from '../src/clinics.js';

test('formatHours splits a range', () => {
  assert.deepEqual(formatHours('08:00-17:00'), { open: '08:00', close: '17:00' });
});

test('findByTown is case-insensitive and returns weekday hours', () => {
  const r = findByTown('millbrook');
  assert.ok(r.length > 0);
  assert.equal(r[0].town, 'Millbrook');
  assert.equal(r[0].weekdays.wed.close, '19:00');
});

test('unknown town returns empty list', () => {
  assert.deepEqual(findByTown('Nowhere'), []);
});

test('five fictional towns', () => {
  assert.equal(towns().length, 5);
});

test('results include Saturday hours', () => {
  const r = findByTown('Millbrook');
  assert.deepEqual(r[0].saturday, { open: '09:00', close: '13:00' });
});

test('town with a clinic that has no Saturday hours succeeds', () => {
  const r = findByTown('Fernhill');
  assert.ok(r.length > 0);
  assert.ok(r.some((c) => c.saturday === null));
});

test('toResult works for every clinic in data/clinics.json', () => {
  const { clinics } = JSON.parse(
    readFileSync(new URL('../data/clinics.json', import.meta.url), 'utf8'),
  );
  for (const c of clinics) {
    assert.doesNotThrow(() => toResult(c), `clinic ${c.id}`);
  }
});
