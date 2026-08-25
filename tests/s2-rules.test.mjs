import assert from 'node:assert/strict';
import { orbBodyOver50, validOrb, targetFor } from '../lib/s2-rules.js';
assert.equal(orbBodyOver50(100,110,98,107),true);
assert.equal(orbBodyOver50(100,110,98,105),false);
assert.equal(validOrb([[0,100,110,98,107],[0,100,112,99,108],[0,108,115,107,114]]),true);
assert.equal(targetFor(110,105,'LONG'),112);
assert.equal(targetFor(100,105,'SHORT'),98);
console.log('S2 rule tests passed');
