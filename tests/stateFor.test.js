import test from 'node:test';
import assert from 'node:assert/strict';
import { stateFor } from '../api/fno-movers.js';

const orb = [
  ['2026-08-25 09:15:00', 100, 105, 99, 104, 0],
  ['2026-08-25 09:20:00', 104, 106, 101, 105, 0],
  ['2026-08-25 09:25:00', 105, 107, 102, 106, 0],
];

test('touching ORB low before a long break does not invalidate the level', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 107, 102, 105, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '⏳ Pending',
    result: '⏳',
  });
});

test('a strict ORB-high break that reaches 0.4R on the breakout candle is Target', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 109, 104, 108, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '🎯 Target',
    result: '0.4R ✅',
  });
});

test('a strict ORB-low break invalidates a long setup before entry', () => {
  const oneMin = [
    ['2026-08-25 09:30:00', 106, 106.5, 98.9, 100, 0],
  ];
  assert.deepEqual(stateFor(orb, oneMin, 'LONG'), {
    status: '⚠️ Invalidated level',
    result: '⚠️',
  });
});
