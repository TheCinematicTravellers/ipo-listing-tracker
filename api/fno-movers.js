import crypto from 'node:crypto';

const IST = 'Asia/Kolkata';
const MASTER_URL = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json';
const LOGIN_URL = 'https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword';
const QUOTE_URL = 'https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/';
const CANDLE_URL = 'https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData';

let cachedMaster = null;
let cachedAt = 0;

function b32(s) {
  const a = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const c = s.replace(/=+$/, '').replace(/\s/g, '').toUpperCase();
  let bits = '';
  for (const ch of c) {
    const v = a.indexOf(ch);
    if (v < 0) throw Error('Invalid TOTP secret');
    bits += v.toString(2).padStart(5, '0');
  }
  const out = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(out);
}

function totp(secret, now = Date.now()) {
  const b = Buffer.alloc(8);
  b.writeBigUInt64BE(BigInt(Math.floor(now / 1000 / 30)));
  const h = crypto.createHmac('sha1', b32(secret)).update(b).digest();
  const o = h[h.length - 1] & 15;
  const n = ((h[o] & 127) << 24) | ((h[o + 1] & 255) << 16) | ((h[o + 2] & 255) << 8) | (h[o + 3] & 255);
  return String(n % 1000000).padStart(6, '0');
}

function headers(apiKey, jwt, mac) {
  return {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-UserType': 'USER',
    'X-SourceID': 'WEB',
    'X-ClientLocalIP': '127.0.0.1',
    'X-ClientPublicIP': process.env.ANGEL_CLIENT_PUBLIC_IP || '127.0.0.1',
    'X-MACAddress': mac,
    'X-PrivateKey': apiKey,
    ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}),
  };
}

function norm(s) {
  return String(s).trim().toUpperCase().replace(/-EQ$/, '');
}

async function master() {
  if (cachedMaster && Date.now() - cachedAt < 600000) return cachedMaster;
  const r = await fetch(MASTER_URL, { headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (!r.ok) throw Error(`Instrument master HTTP ${r.status}`);
  const map = new Map();
  for (const x of await r.json()) {
    if (x.exch_seg !== 'NSE' || x.instrumenttype) continue;
    for (const k of [x.symbol, x.tradingsymbol]) {
      const n = norm(k || '');
      if (n && !map.has(n)) map.set(n, x.token);
    }
  }
  cachedMaster = map;
  cachedAt = Date.now();
  return map;
}

async function login() {
  const apiKey = process.env.ANGEL_API_KEY;
  const client = process.env.ANGEL_CLIENT_ID;
  const pin = process.env.ANGEL_PIN;
  const secret = process.env.ANGEL_TOTP_SECRET;
  const mac = process.env.ANGEL_MAC_ADDRESS || '00:00:00:00:00:00';
  if (!apiKey || !client || !pin || !secret) throw Error('Missing Angel One environment variables');
  const r = await fetch(LOGIN_URL, {
    method: 'POST',
    headers: headers(apiKey, null, mac),
    body: JSON.stringify({ clientcode: client, password: pin, totp: totp(secret) }),
  });
  const d = await r.json();
  if (!r.ok || !d?.data?.jwtToken) throw Error(`Angel login failed: ${d?.message || r.status}`);
  return { apiKey, jwt: d.data.jwtToken, mac };
}

async function quote(a, tokens) {
  const r = await fetch(QUOTE_URL, {
    method: 'POST',
    headers: headers(a.apiKey, a.jwt, a.mac),
    body: JSON.stringify({ mode: 'FULL', exchangeTokens: { NSE: tokens } }),
  });
  const d = await r.json();
  if (!r.ok || d?.status === false) throw Error(`Quote failed: ${d?.message || r.status}`);
  return d?.data?.fetched || [];
}

async function candles(a, token, from, to, interval) {
  const r = await fetch(CANDLE_URL, {
    method: 'POST',
    headers: headers(a.apiKey, a.jwt, a.mac),
    body: JSON.stringify({ exchange: 'NSE', symboltoken: String(token), interval, fromdate: from, todate: to }),
  });
  const d = await r.json();
  if (!r.ok || d?.status === false) throw Error(`Candle failed: ${d?.message || r.status}`);
  return d?.data || [];
}

function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

function parts(d = new Date()) {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: IST,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(d);
  const o = {};
  for (const x of p) o[x.type] = x.value;
  return o;
}

function stamp() {
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: IST,
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  }).format(new Date());
}

// S2 state machine:
// LONG = OPEN=LOW -> ORB HIGH break. SHORT = OPEN=HIGH -> ORB LOW break.
// Entry/invalidation use strict breaks (> / <). Target/SL use touches (>= / <=).
// The breakout candle is eligible for the outcome because price can reach 0.4R in that candle.
export function stateFor(orbCandles, oneMin, direction) {
  const orderedOrb = orbCandles
    .filter(c => Array.isArray(c) && c.length >= 5 && Number.isFinite(Date.parse(String(c[0]))))
    .slice()
    .sort((a, b) => Date.parse(String(a[0])) - Date.parse(String(b[0])));

  if (orderedOrb.length < 3) return { status: '⏳ Pending', result: '⏳' };

  const orb = orderedOrb.slice(0, 3);
  const hi = Math.max(...orb.map(c => Number(c[2])));
  const lo = Math.min(...orb.map(c => Number(c[3])));

  const candlesAfterOrb = oneMin
    .filter(c => Array.isArray(c) && c.length >= 5 && Number.isFinite(Date.parse(String(c[0]))))
    .slice()
    .sort((a, b) => Date.parse(String(a[0])) - Date.parse(String(b[0])));

  let entry = null;
  let sl = null;
  let target = null;

  for (const c of candlesAfterOrb) {
    const h = Number(c[2]);
    const l = Number(c[3]);
    if (!Number.isFinite(h) || !Number.isFinite(l)) continue;

    if (entry === null) {
      if (direction === 'LONG') {
        // ORB HIGH must be broken, not merely touched.
        if (h > hi) {
          entry = hi;
          sl = l;
          const risk = entry - sl;
          if (risk <= 0) return { status: '⚠️ Invalidated level', result: '⚠️' };
          target = entry + 0.4 * risk;

          // The breakout candle itself can complete the trade.
          if (h >= target) return { status: '🎯 Target', result: '0.4R ✅' };
          if (l <= sl) return { status: '❌ SL', result: '❌' };
          continue;
        }

        // ORB LOW must be broken, not merely touched, before entry.
        if (l < lo) return { status: '⚠️ Invalidated level', result: '⚠️' };
      } else {
        // ORB LOW must be broken, not merely touched.
        if (l < lo) {
          entry = lo;
          sl = h;
          const risk = sl - entry;
          if (risk <= 0) return { status: '⚠️ Invalidated level', result: '⚠️' };
          target = entry - 0.4 * risk;

          // The breakout candle itself can complete the trade.
          if (l <= target) return { status: '🎯 Target', result: '0.4R ✅' };
          if (h >= sl) return { status: '❌ SL', result: '❌' };
          continue;
        }

        // ORB HIGH must be broken, not merely touched, before entry.
        if (h > hi) return { status: '⚠️ Invalidated level', result: '⚠️' };
      }
    } else if (direction === 'LONG') {
      if (h >= target) return { status: '🎯 Target', result: '0.4R ✅' };
      if (l <= sl) return { status: '❌ SL', result: '❌' };
    } else {
      if (l <= target) return { status: '🎯 Target', result: '0.4R ✅' };
      if (h >= sl) return { status: '❌ SL', result: '❌' };
    }
  }

  return entry === null
    ? { status: '⏳ Pending', result: '⏳' }
    : { status: '✅ Trade Active', result: '⚖️' };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store,max-age=0');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'GET only' });

  try {
    const raw = await fetch('https://raw.githubusercontent.com/TheCinematicTravellers/ipo-listing-tracker/main/fno_universe.json', { cache: 'no-store' }).then(r => r.json());
    const symbols = Array.isArray(raw) ? raw : JSON.parse(raw.content);
    const m = await master();
    const matched = symbols.map(s => ({ symbol: s, token: m.get(norm(s)) })).filter(x => x.token);
    const missing = symbols.filter(s => !m.get(norm(s)));
    const a = await login();
    const rows = [];

    for (let i = 0; i < matched.length; i += 50) {
      const batch = matched.slice(i, i + 50);
      const f = await quote(a, batch.map(x => String(x.token)));
      const by = new Map(f.map(x => [String(x.symbolToken), x]));
      for (const x of batch) {
        const q = by.get(String(x.token));
        if (!q) continue;
        const open = num(q.open), high = num(q.high), low = num(q.low), cmp = num(q.ltp), close = num(q.close), volume = num(q.tradeVolume ?? q.volume);
        if ([open, high, low, cmp, close].some(v => v === null) || !close) continue;
        rows.push({ symbol: x.symbol, token: x.token, change_pct: (cmp / close - 1) * 100, open, high, low, cmp, volume: volume ?? 0 });
      }
    }

    const gainers = rows.filter(x => Math.abs(x.open - x.low) < 1e-7).sort((a, b) => b.change_pct - a.change_pct).slice(0, 10);
    const losers = rows.filter(x => Math.abs(x.open - x.high) < 1e-7).sort((a, b) => a.change_pct - b.change_pct).slice(0, 10);
    const p = parts();
    const start = `${p.year}-${p.month}-${p.day} 09:15`;
    const orbEnd = `${p.year}-${p.month}-${p.day} 09:30`;
    const end = `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;

    for (const x of gainers.concat(losers)) {
      try {
        const orb = await candles(a, x.token, start, orbEnd, 'FIVE_MINUTE');
        const one = await candles(a, x.token, orbEnd, end, 'ONE_MINUTE');
        const s = stateFor(orb, one, gainers.includes(x) ? 'LONG' : 'SHORT');
        x.status = s.status;
        x.result = s.result;
      } catch (e) {
        x.status = '⏳ Pending';
        x.result = '⏳';
      }
      x.change_pct = Number(x.change_pct.toFixed(2));
    }

    return res.status(200).json({
      date_ist: new Intl.DateTimeFormat('en-IN', { timeZone: IST, day: '2-digit', month: 'short', year: 'numeric' }).format(new Date()),
      updated_ist: stamp(),
      timezone: IST,
      universe_size: symbols.length,
      available: rows.length,
      matched: matched.length,
      missing,
      gainers,
      losers,
    });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: e.message || 'AUTO feed failed' });
  }
}
