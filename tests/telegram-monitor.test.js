import test from 'node:test';
import assert from 'node:assert/strict';

function minutes(p){return Number(p.hour)*60+Number(p.minute)}

test('monitor window starts at 09:30 IST',()=>{
  assert.equal(minutes({hour:'09',minute:'29'})<570,true);
  assert.equal(minutes({hour:'09',minute:'30'})>=570,true);
});

test('monitor window ends at 15:30 IST',()=>{
  assert.equal(minutes({hour:'15',minute:'30'})<=930,true);
  assert.equal(minutes({hour:'15',minute:'31'})>930,true);
});

test('only Pending to another status is alert-worthy',()=>{
  const shouldAlert=(previous,current)=>Boolean(previous==='⏳ Pending'&&current!=='⏳ Pending');
  assert.equal(shouldAlert('⏳ Pending','🎯 Target'),true);
  assert.equal(shouldAlert('⏳ Pending','❌ SL'),true);
  assert.equal(shouldAlert('⏳ Pending','⚠️ Invalidated level'),true);
  assert.equal(shouldAlert('⏳ Pending','✅ Trade Active'),true);
  assert.equal(shouldAlert('🎯 Target','🎯 Target'),false);
  assert.equal(shouldAlert('⏳ Pending','⏳ Pending'),false);
});
