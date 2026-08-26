import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLockedSet, statusCounts } from './orb-lock.mjs';

test('9:30 locked set does not accept later additions', () => {
  const first = buildLockedSet(
    [{ symbol: 'A' }, { symbol: 'B' }],
    [{ symbol: 'C' }, { symbol: 'D' }]
  );
  const later = buildLockedSet(
    [{ symbol: 'X' }, { symbol: 'Y' }],
    [{ symbol: 'Z' }],
    first
  );
  assert.deepEqual(later, first);
});

test('summary counts only the locked set rows', () => {
  assert.deepEqual(
    statusCounts([
      { status: '🎯 Target' },
      { status: '✅ Trade Active' },
      { status: '❌ SL' },
      { status: '⏳ Pending' },
      { status: '⚠️ Invalidated level' }
    ]),
    { target: 1, active: 1, sl: 1, pending: 1, invalidated: 1 }
  );
});
