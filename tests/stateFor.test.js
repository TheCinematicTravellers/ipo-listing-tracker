import test from 'node:test';
import assert from 'node:assert/strict';
import { stateFor } from '../api/fno-movers.js';

const orb = [
  ['2026-08-25 09:15:00', 100, 105, 99, 104, 0],
  ['2026-08-25 09:20:00', 104, 106, 101, 105, 0],
  ['2026-08-25 09:25:00', 105, 107, 102, 106, 0],
];

// ORB High = 107, ORB Low = 99, risk = 8, long target = 110.2.
test('touching ORB low before a long break invalidates the level', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 106.5, 98.9, 100, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '⚠️ Invalidated level',
    result: '⚠️',
  });
});

test('a long break that reaches the real 0.4R target is Target', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 111, 106, 110, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '🎯 Target',
    result: '0.4R ✅',
  });
});

test('a long break without target or SL remains active', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 109, 106, 108, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '✅ Trade Active',
    result: '⚖️',
  });
});

test('a short break that reaches the 0.4R target is Target', () => {
  assert.deepEqual(stateFor(orb, [
    ['2026-08-25 09:30:00', 100, 100, 95, 96, 0],
  ], 'SHORT'), {
    status: '🎯 Target',
    result: '0.4R ✅',
  });
});
