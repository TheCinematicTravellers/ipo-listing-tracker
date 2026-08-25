import assert from 'node:assert/strict';
import { stateFor } from '../api/fno-movers.js';

const orb = [
  ['2026-08-25T09:15:00+05:30', 100, 105, 99, 104],
  ['2026-08-25T09:20:00+05:30', 104, 110, 101, 108],
  ['2026-08-25T09:25:00+05:30', 108, 109, 100, 105],
];

function oneMinute(ts, open, high, low, close) {
  return [ts, open, high, low, close];
}

// LONG: ORB high is entry, ORB low is pre-entry invalidation, target is 0.4R.
const longTarget = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 106, 110, 105, 109),
  oneMinute('2026-08-25T09:32:00+05:30', 109, 114, 108, 113),
], 'LONG');
assert.deepEqual(longTarget, { status: '🎯 Target', result: '0.4R ✅' });

const longInvalidated = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 106, 108, 99, 100),
], 'LONG');
assert.deepEqual(longInvalidated, { status: '⚠️ Invalidated level', result: '⚠️' });

// LONG: once entry occurs, a later SL must remain SL even if a later candle reaches target.
const longSl = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 106, 111, 104, 105),
  oneMinute('2026-08-25T09:32:00+05:30', 105, 107, 99, 100),
  oneMinute('2026-08-25T09:33:00+05:30', 100, 114, 100, 113),
], 'LONG');
assert.deepEqual(longSl, { status: '❌ SL', result: '❌' });

// LONG: same candle touches target and SL after entry. Use conservative SL policy.
const longAmbiguous = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 106, 114, 99, 105),
], 'LONG');
assert.deepEqual(longAmbiguous, { status: '❌ SL', result: '❌' });

// SHORT mirror: ORB low is entry, ORB high is pre-entry invalidation, target is 0.4R.
const shortTarget = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 103, 104, 99, 100),
  oneMinute('2026-08-25T09:32:00+05:30', 100, 101, 94, 95),
], 'SHORT');
assert.deepEqual(shortTarget, { status: '🎯 Target', result: '0.4R ✅' });

const shortInvalidated = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 103, 111, 102, 110),
], 'SHORT');
assert.deepEqual(shortInvalidated, { status: '⚠️ Invalidated level', result: '⚠️' });

const shortSl = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 103, 105, 98, 99),
  oneMinute('2026-08-25T09:32:00+05:30', 99, 111, 97, 100),
  oneMinute('2026-08-25T09:33:00+05:30', 100, 100, 94, 95),
], 'SHORT');
assert.deepEqual(shortSl, { status: '❌ SL', result: '❌' });

// SHORT: same candle touches target and SL after entry. Use conservative SL policy.
const shortAmbiguous = stateFor(orb, [
  oneMinute('2026-08-25T09:31:00+05:30', 103, 111, 94, 100),
], 'SHORT');
assert.deepEqual(shortAmbiguous, { status: '❌ SL', result: '❌' });

console.log('stateFor tests passed');
