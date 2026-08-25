export function orbBodyOver50(open, high, low, close) {
  const range = Number(high) - Number(low);
  return range > 0 && Math.abs(Number(close) - Number(open)) / range > 0.5;
}

export function validOrb(candles) {
  return candles.length === 3 && candles.every(c => orbBodyOver50(c[1], c[2], c[3], c[4]));
}

export function targetFor(entry, sl, direction) {
  const risk = direction === 'LONG' ? entry - sl : sl - entry;
  return direction === 'LONG' ? entry + 0.4 * risk : entry - 0.4 * risk;
}
