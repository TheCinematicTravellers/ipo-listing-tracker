import crypto from 'node:crypto';

const IST = 'Asia/Kolkata';
const MASTER_URL = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json';
const LOGIN_URL = 'https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword';
const QUOTE_URL = 'https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/';

let cachedMaster = null;
let cachedAt = 0;

function base32ToBuffer(s) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = s.replace(/=+$/,'').replace(/\s/g,'').toUpperCase();
  let bits = '';
  for (const ch of clean) {
    const v = alphabet.indexOf(ch);
    if (v < 0) throw new Error('Invalid TOTP secret');
    bits += v.toString(2).padStart(5,'0');
  }
  const out = [];
  for (let i=0; i+8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i,i+8),2));
  return Buffer.from(out);
}

function totp(secret, now = Date.now()) {
  const counter = Math.floor(now / 1000 / 30);
  const b = Buffer.alloc(8);
  b.writeBigUInt64BE(BigInt(counter));
  const h = crypto.createHmac('sha1', base32ToBuffer(secret)).update(b).digest();
  const o = h[h.length - 1] & 15;
  const code = ((h[o]&127)<<24)|((h[o+1]&255)<<16)|((h[o+2]&255)<<8)|(h[o+3]&255);
  return String(code % 1000000).padStart(6,'0');
}

function headers(apiKey, jwt) {
  return {
    'Content-Type':'application/json',
    'Accept':'application/json',
    'X-UserType':'USER',
    'X-SourceID':'WEB',
    'X-PrivateKey':apiKey,
    ...(jwt ? {'Authorization':`Bearer ${jwt}`} : {})
  };
}

function normalize(s) { return String(s).trim().toUpperCase().replace(/-EQ$/,''); }

async function getMaster() {
  if (cachedMaster && Date.now() - cachedAt < 10*60*1000) return cachedMaster;
  const r = await fetch(MASTER_URL, {headers:{Accept:'application/json'}, cache:'no-store'});
  if (!r.ok) throw new Error(`Instrument master HTTP ${r.status}`);
  const arr = await r.json();
  const map = new Map();
  for (const x of arr) {
    if (x.exch_seg !== 'NSE' || x.instrumenttype) continue;
    const key = normalize(x.symbol || x.tradingsymbol);
    if (key && !map.has(key)) map.set(key, x.token);
    const tkey = normalize(x.tradingsymbol || '');
    if (tkey && !map.has(tkey)) map.set(tkey, x.token);
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
  if (!apiKey || !client || !pin || !secret) throw new Error('Missing Angel One environment variables');
  const r = await fetch(LOGIN_URL, {
    method:'POST',
    headers:headers(apiKey),
    body:JSON.stringify({clientcode:client,password:pin,totp:totp(secret)})
  });
  const d = await r.json();
  if (!r.ok || !d?.data?.jwtToken) throw new Error(`Angel login failed: ${d?.message || r.status}`);
  return {apiKey, jwt:d.data.jwtToken};
}

async function quote(auth, tokens) {
  const r = await fetch(QUOTE_URL, {
    method:'POST',
    headers:headers(auth.apiKey, auth.jwt),
    body:JSON.stringify({mode:'FULL',exchangeTokens:{NSE:tokens}})
  });
  const d = await r.json();
  if (!r.ok || d?.status === false) throw new Error(`Quote failed: ${d?.message || r.status}`);
  return d?.data?.fetched || [];
}

function asNum(x) { const n = Number(x); return Number.isFinite(n) ? n : null; }
function stamp() { return new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}).format(new Date()); }
function dateIST() { return new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric'}).format(new Date()); }

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin','*');
  res.setHeader('Access-Control-Allow-Methods','GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers','Content-Type');
  res.setHeader('Cache-Control','no-store, max-age=0');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({error:'GET only'});
  try {
    const raw = await fetch('https://raw.githubusercontent.com/TheCinematicTravellers/ipo-listing-tracker/main/fno_universe.json',{cache:'no-store'}).then(r=>r.json());
    const symbols = Array.isArray(raw) ? raw : JSON.parse(raw.content);
    const master = await getMaster();
    const matched = symbols.map(s=>({symbol:s,token:master.get(normalize(s))})).filter(x=>x.token);
    const missing = symbols.filter(s=>!master.get(normalize(s)));
    const auth = await login();
    const rows = [];
    for (let i=0;i<matched.length;i+=50) {
      const batch = matched.slice(i,i+50);
      const fetched = await quote(auth,batch.map(x=>String(x.token)));
      const byToken = new Map(fetched.map(x=>[String(x.symbolToken),x]));
      for (const m of batch) {
        const q = byToken.get(String(m.token));
        if (!q) continue;
        const open=asNum(q.open), high=asNum(q.high), low=asNum(q.low), cmp=asNum(q.ltp), close=asNum(q.close), volume=asNum(q.tradeVolume ?? q.volume);
        if ([open,high,low,cmp,close].some(v=>v===null) || !close) continue;
        rows.push({symbol:m.symbol,change_pct:(cmp/close-1)*100,open,high,low,cmp,volume:volume??0});
      }
    }
    const eq=(a,b)=>Math.abs(a-b)<0.0000001;
    const openLow=rows.filter(x=>eq(x.open,x.low));
    const openHigh=rows.filter(x=>eq(x.open,x.high));
    const gainers=openLow.sort((a,b)=>b.change_pct-a.change_pct).slice(0,10);
    const losers=openHigh.sort((a,b)=>a.change_pct-b.change_pct).slice(0,10);
    for (const x of [...gainers,...losers]) x.change_pct=Number(x.change_pct.toFixed(2));
    return res.status(200).json({date_ist:dateIST(),updated_ist:stamp(),timezone:IST,universe_size:symbols.length,available:rows.length,matched:matched.length,missing,eligible_open_low:openLow.length,eligible_open_high:openHigh.length,gainers,losers});
  } catch (e) {
    console.error(e);
    return res.status(500).json({error:e.message || 'AUTO feed failed'});
  }
}
