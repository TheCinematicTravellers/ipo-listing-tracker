export function buildLockedSet(gainers, losers, existing = null) {
  if (existing?.length) return existing;
  return [
    ...gainers.slice(0, 10).map(x => ({ ...x, direction: 'LONG' })),
    ...losers.slice(0, 10).map(x => ({ ...x, direction: 'SHORT' }))
  ];
}

export function statusCounts(rows) {
  const out = { target: 0, active: 0, sl: 0, pending: 0, invalidated: 0 };
  for (const row of rows) {
    const s = String(row.status || '⏳ Pending');
    if (s === '🎯 Target') out.target++;
    else if (s === '✅ Trade Active') out.active++;
    else if (s === '❌ SL') out.sl++;
    else if (s === '⚠️ Invalidated level') out.invalidated++;
    else out.pending++;
  }
  return out;
}
