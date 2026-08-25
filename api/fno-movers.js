import crypto from 'node:crypto';

const IST = 'Asia/Kolkata';
const MASTER_URL = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json';
const LOGIN_URL = 'https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword';
const QUOTE_URL = 'https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/';
const CANDLE_URL = 'https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData';

let cachedMaster = null;
let cachedAt = 0;

function base32ToBuffer(s) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = s.replace(/=+$/,'').replace(/\s/g,'').toUpperCase();
  let bits = '';
  for (const ch of clean) { const v = alphabet.indexOf(ch); if (v < 0) throw new Error('Invalid TOTP secret'); bits += v.toString(2).padStart(5,'0'); }
  const out = []; for (let i=0;i+8<=bits.length;i+=8) out.push(parseInt(bits.slice(i,i+8),2));
  return Buffer.from(out);
}
function totp(secret, now=Date.now()) {
  const counter=Math.floor(now/1000/30), b=Buffer.alloc(8); b.writeBigUInt64BE(BigInt(counter));
  const h=crypto.createHmac('sha1',base32ToBuffer(secret)).update(b).digest(), o=h[h.length-1]&15;
  const code=((h[o]&127)<<24)|((h[o+1]&255)<<16)|((h[o+2]&255)<<8)|(h[o+3]&255); return String(code%1000000).padStart(6,'0');
}
function headers(apiKey,jwt,macAddress){ return {'Content-Type':'application/json','Accept':'application/json','X-UserType':'USER','X-SourceID':'WEB','X-ClientLocalIP':'127.0.0.1','X-ClientPublicIP':process.env.ANGEL_CLIENT_PUBLIC_IP||'127.0.0.1','X-MACAddress':macAddress,'X-PrivateKey':apiKey,...(jwt?{'Authorization':`Bearer ${jwt}`}:{})}; }
function normalize(s){return String(s).trim().toUpperCase().replace(/-EQ$/,'');}
async function getMaster(){
  if(cachedMaster&&Date.now()-cachedAt<10*60*1000)return cachedMaster;
  const r=await fetch(MASTER_URL,{headers:{Accept:'application/json'},cache:'no-store'}); if(!r.ok)throw new Error(`Instrument master HTTP ${r.status}`);
  const arr=await r.json(),map=new Map(); for(const x of arr){if(x.exch_seg!=='NSE'||x.instrumenttype)continue;const k=normalize(x.symbol||x.tradingsymbol),t=normalize(x.tradingsymbol||'');if(k&&!map.has(k))map.set(k,x.token);if(t&&!map.has(t))map.set(t,x.token);} cachedMaster=map;cachedAt=Date.now();return map;
}
async function login(){
  const apiKey=process.env.ANGEL_API_KEY,client=process.env.ANGEL_CLIENT_ID,pin=process.env.ANGEL_PIN,secret=process.env.ANGEL_TOTP_SECRET,macAddress=process.env.ANGEL_MAC_ADDRESS||'00:00:00:00:00:00';
  if(!apiKey||!client||!pin||!secret)throw new Error('Missing Angel One environment variables');
  const r=await fetch(LOGIN_URL,{method:'POST',headers:headers(apiKey,null,macAddress),body:JSON.stringify({clientcode:client,password:pin,totp:totp(secret)})}),d=await r.json();
  if(!r.ok||!d?.data?.jwtToken)throw new Error(`Angel login failed: ${d?.message||r.status}`); return {apiKey,jwt:d.data.jwtToken,macAddress};
}
async function quote(auth,tokens){
  const r=await fetch(QUOTE_URL,{method:'POST',headers:headers(auth.apiKey,auth.jwt,auth.macAddress),body:JSON.stringify({mode:'FULL',exchangeTokens:{NSE:tokens}})}),d=await r.json();
  if(!r.ok||d?.status===false)throw new Error(`Quote failed: ${d?.message||r.status}`); return d?.data?.fetched||[];
}
async function candles(auth,token,from,to){
  const r=await fetch(CANDLE_URL,{method:'POST',headers:headers(auth.apiKey,auth.jwt,auth.macAddress),body:JSON.stringify({exchange:'NSE',symboltoken:String(token),interval:'FIVE_MINUTE',fromdate:from,todate:to})});
  const d=await r.json(); if(!r.ok||d?.status===false)throw new Error(`Candle failed: ${d?.message||r.status}`); return d?.data||[];
}
function asNum(x){const n=Number(x);return Number.isFinite(n)?n:null;}
function stamp(){return new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}).format(new Date());}
function dateIST(){return new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric'}).format(new Date());}
function istParts(d=new Date()){const p=new Intl.DateTimeFormat('en-CA',{timeZone:IST,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d);const o={};for(const x of p)o[x.type]=x.value;return o;}
function fmtISTDateTime(d){const p=istParts(d);return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;}
function stateFor(row,candlesNow){
  if(!candlesNow||candlesNow.length<3)return {status:'⏳ Pending',result:'⏳'};
  const completed=candlesNow.filter(c=>{const t=new Date(c[0]);const p=istParts(t);return Number(p.hour)*60+Number(p.minute)<570;});
  if(completed.length<3)return {status:'⏳ Pending',result:'⏳'};
  const orb=completed.slice(-3), orbHigh=Math.max(...orb.map(c=>Number(c[2]))), orbLow=Math.min(...orb.map(c=>Number(c[3])));
  const after=candlesNow.filter(c=>new Date(c[0])>=new Date(orb[2][0]));
  for(const c of after){const high=Number(c[2]),low=Number(c[3]),close=Number(c[4]); if(high>orbHigh){const entry=orbHigh,sl=Number(c[3]),risk=Math.max(entry-sl,0); if(risk<=0)return {status:'⚠️ Invalidated level',result:'⚠️'}; const target=entry+0.4*risk; if(low<=sl)return {status:'❌ SL',result:'❌'}; if(high>=target)return {status:'🎯 Target',result:'0.4R ✅'}; return {status:'✅ Trade Active',result:'⚖️'};} if(low<orbLow)return {status:'⚠️ Invalidated level',result:'⚠️'}; if(close>orbHigh)return {status:'⚠️ Invalidated level',result:'⚠️'}; }
  return {status:'⏳ Pending',result:'⏳'};
}

export default async function handler(req,res){
  res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Methods','GET,OPTIONS');res.setHeader('Access-Control-Allow-Headers','Content-Type');res.setHeader('Cache-Control','no-store, max-age=0');
  if(req.method==='OPTIONS')return res.status(204).end();if(req.method!=='GET')return res.status(405).json({error:'GET only'});
  try{
    const raw=await fetch('https://raw.githubusercontent.com/TheCinematicTravellers/ipo-listing-tracker/main/fno_universe.json',{cache:'no-store'}).then(r=>r.json()),symbols=Array.isArray(raw)?raw:JSON.parse(raw.content),master=await getMaster();
    const matched=symbols.map(s=>({symbol:s,token:master.get(normalize(s))})).filter(x=>x.token),missing=symbols.filter(s=>!master.get(normalize(s))),auth=await login(),rows=[];
    for(let i=0;i<matched.length;i+=50){const batch=matched.slice(i,i+50),fetched=await quote(auth,batch.map(x=>String(x.token))),byToken=new Map(fetched.map(x=>[String(x.symbolToken),x]));for(const m of batch){const q=byToken.get(String(m.token));if(!q)continue;const open=asNum(q.open),high=asNum(q.high),low=asNum(q.low),cmp=asNum(q.ltp),close=asNum(q.close),volume=asNum(q.tradeVolume??q.volume);if([open,high,low,cmp,close].some(v=>v===null)||!close)continue;rows.push({symbol:m.symbol,token:m.token,change_pct:(cmp/close-1)*100,open,high,low,cmp,volume:volume??0});}}
    const eq=(a,b)=>Math.abs(a-b)<1e-7,openLow=rows.filter(x=>eq(x.open,x.low)),openHigh=rows.filter(x=>eq(x.open,x.high));
    const gainers=openLow.sort((a,b)=>b.change_pct-a.change_pct).slice(0,10),losers=openHigh.sort((a,b)=>a.change_pct-b.change_pct).slice(0,10);
    const now=new Date(),p=istParts(now),dayStart=`${p.year}-${p.month}-${p.day} 09:15`,dayEnd=fmtISTDateTime(now),states=new Map();
    if(Number(p.hour)*60+Number(p.minute)>=555){
      for(const x of [...gainers,...losers]){try{const cs=await candles(auth,x.token,dayStart,dayEnd);states.set(x.symbol,stateFor(x,cs));}catch(e){states.set(x.symbol,{status:'⏳ Pending',result:'⏳'});}}
    }
    for(const x of [...gainers,...losers]){const s=states.get(x.symbol)||{status:'⏳ Pending',result:'⏳'};x.status=s.status;x.result=s.result;x.change_pct=Number(x.change_pct.toFixed(2));}
    return res.status(200).json({date_ist:dateIST(),updated_ist:stamp(),timezone:IST,universe_size:symbols.length,available:rows.length,matched:matched.length,missing,eligible_open_low:openLow.length,eligible_open_high:openHigh.length,gainers,losers});
  }catch(e){console.error(e);return res.status(500).json({error:e.message||'AUTO feed failed'});}
}
