import assert from 'node:assert/strict';
import {
  shouldAlertOnStatusChange,
  isWithinSummaryWindow,
} from './telegram-monitor.js';

assert.equal(shouldAlertOnStatusChange(null, '⏳ Pending'), false);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '⏳ Pending'), false);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '✅ Trade Active'), true);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '⚠️ Invalidated level'), true);
assert.equal(shouldAlertOnStatusChange('✅ Trade Active', '🎯 Target'), true);
assert.equal(shouldAlertOnStatusChange('✅ Trade Active', '❌ SL'), true);
assert.equal(shouldAlertOnStatusChange('🎯 Target', '❌ SL'), true);

assert.equal(isWithinSummaryWindow(16 * 60 + 30), true);
assert.equal(isWithinSummaryWindow(16 * 60 + 45), true);
assert.equal(isWithinSummaryWindow(2 * 60 + 33), false);
assert.equal(isWithinSummaryWindow(18 * 60 + 1), false);

console.log('telegram-monitor tests passed');
