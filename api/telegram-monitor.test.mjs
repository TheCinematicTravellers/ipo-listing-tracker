import assert from 'node:assert/strict';
import { shouldAlertOnStatusChange } from './telegram-monitor.js';

assert.equal(shouldAlertOnStatusChange(null, '⏳ Pending'), false);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '⏳ Pending'), false);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '✅ Trade Active'), true);
assert.equal(shouldAlertOnStatusChange('⏳ Pending', '⚠️ Invalidated level'), true);
assert.equal(shouldAlertOnStatusChange('✅ Trade Active', '🎯 Target'), true);
assert.equal(shouldAlertOnStatusChange('✅ Trade Active', '❌ SL'), true);
assert.equal(shouldAlertOnStatusChange('🎯 Target', '❌ SL'), true);

console.log('telegram-monitor state transition tests passed');
