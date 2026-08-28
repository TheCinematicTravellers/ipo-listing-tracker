import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';

test('fno_movers.json is valid JSON with finite numeric market fields', () => {
  const raw = fs.readFileSync(new URL('../fno_movers.json', import.meta.url), 'utf8');
  const data = JSON.parse(raw);

  for (const row of [...(data.gainers || []), ...(data.losers || [])]) {
    for (const key of ['change_pct', 'open', 'high', 'low', 'cmp', 'volume']) {
      if (row[key] !== null && row[key] !== undefined) {
        assert.equal(typeof row[key], 'number', `${row.symbol}.${key} must be numeric`);
        assert.ok(Number.isFinite(row[key]), `${row.symbol}.${key} must be finite`);
      }
    }
  }
});
