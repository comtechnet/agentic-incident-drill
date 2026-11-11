import { test } from 'node:test';
import assert from 'node:assert/strict';
import { findByTown, formatHours, towns } from '../src/clinics.js';

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
