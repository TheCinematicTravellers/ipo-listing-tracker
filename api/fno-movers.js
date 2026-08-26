import crypto from 'node:crypto';
const IST='Asia/Kolkata';
const MASTER_URL='https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json';
const LOGIN_URL='https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword';
const QUOTE_URL='https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/';
const CANDLE_URL='https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData';
let cachedMaster=null,cachedAt=0;
let nextAngelRequestAt=0;

function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms));}
async function paceAngel(minGap=400){
  const now=Date.now();
  const wait=Math.max(0,nextAngelRequestAt-now);
  if(wait>0)await sleep(wait);
  nextAngelRequestAt=Date.now()+minGap;
}
function b32(s){const a='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567',c=s.replace(/=+$/,'').replace(/\s/g,'').toUpperCase();let bits='';for(const ch of c){const v=a.indexOf(ch);if(v<0)throw Error('Invalid TOTP secret');bits+=v.toString(2).padStart(5,'0')}const out=[];for(let i=0;i+8<=bits.length;i+=8)out.push(parseInt(bits.slice(i,i+8),2));return Buffer.from(out)}
function totp(secret,now=Date.now()){const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(now/1000/30)));const h=crypto.createHmac('sha1',b32(secret)).update(b).digest(),o=h[h.length-1]&15;const n=((h[o]&127)<<24)|((h[o+1]&255)<<16)|((h[o+2]&255)<<8)|(h[o+3]&255);return String(n%1000000).padStart(6,'0')}
function headers(apiKey,jwt,mac){return {'Content-Type':'application/json','Accept':'application/json','X-UserType':'USER','X-SourceID':'WEB','X-ClientLocalIP':'127.0.0.1','X-ClientPublicIP':process.env.ANGEL_CLIENT_PUBLIC_IP||'127.0.0.1','X-MACAddress':mac,'X-PrivateKey':apiKey,...jwt?{Authorization:`Bearer ${jwt}`}:{}}}
function norm(s){return String(s).trim().toUpperCase().replace(/-EQ$/,'')}
async function master(){if(cachedMaster&&Date.now()-cachedAt<600000)return cachedMaster;const r=await fetch(MASTER_URL,{headers:{Accept:'application/json'},cache:'no-store'});if(!r.ok)throw Error(`Instrument master HTTP ${r.status}`);const map=new Map();for(const x of await r.json()){if(x.exch_seg!=='NSE'||x.instrumenttype)continue;for(const k of [x.symbol,x.tradingsymbol]){const n=norm(k||'');if(n&&!map.has(n))map.set(n,x.token)}}cachedMaster=map;cachedAt=Date.now();return map}
async function login(){const apiKey=process.env.ANGEL_API_KEY,client=process.env.ANGEL_CLIENT_ID,pin=process.env.ANGEL_PIN,secret=process.env.ANGEL_TOTP_SECRET,mac=process.env.ANGEL_MAC_ADDRESS||'00:00:00:00:00:00';if(!apiKey||!client||!pin||!secret)throw Error('Missing Angel One environment variables');await paceAngel();const r=await fetch(LOGIN_URL,{method:'POST',headers:headers(apiKey,null,mac),body:JSON.stringify({clientcode:client,password:pin,totp:totp(secret)})}),d=await r.json();if(!r.ok||!d?.data?.jwtToken)throw Error(`Angel login failed: ${d?.message||r.status}`);return {apiKey,jwt:d.data.jwtToken,mac}}
async function quote(a,tokens){await paceAngel();const r=await fetch(QUOTE_URL,{method:'POST',headers:headers(a.apiKey,a.jwt,a.mac),body:JSON.stringify({mode:'FULL',exchangeTokens:{NSE:tokens}})}),d=await r.json();if(!r.ok||d?.status===false)throw Error(`Quote failed: ${d?.message||r.status}`);return d?.data?.fetched||[]}
async function angelCandleRequest(a,token,from,to,interval){
  let lastError=null;
  for(let attempt=0;attempt<4;attempt++){
    await paceAngel(400);
    try{
      const r=await fetch(CANDLE_URL,{method:'POST',headers:headers(a.apiKey,a.jwt,a.mac),body:JSON.stringify({exchange:'NSE',symboltoken:String(token),interval,fromdate:from,todate:to})});
      const d=await r.json();
      if(r.ok&&d?.status!==false)return d?.data||[];
      lastError=Error(`Candle failed: ${d?.message||r.status}`);
      const msg=String(d?.message||'').toLowerCase();
      if(r.status!==429&&!msg.includes('rate')&&!msg.includes('throttle')&&!msg.includes('too many'))break;
    }catch(e){lastError=e;}
    await sleep(800*(attempt+1));
  }
  throw lastError||Error('Candle request failed');
}
function num(x){const n=Number(x);return Number.isFinite(n)?n:null}
function parts(d=new Date()){const p=new Intl.DateTimeFormat('en-CA',{timeZone:IST,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),o={};for(const x of p)o[x.type]=x.value;return o}
function stamp(){return new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}).format(new Date())}
function orderedCandles(arr){return (Array.isArray(arr)?arr:[]).filter(c=>Array.isArray(c)&&c.length>=5&&Number.isFinite(Date.parse(String(c[0])))).slice().sort((a,b)=>Date.parse(String(a[0]))-Date.parse(String(b[0])))}

function buildOrb5m(oneMin){
  const groups=new Map();
  for(const c of orderedCandles(oneMin)){
    const p=parts(new Date(String(c[0]))),m=Number(p.minute),h=Number(p.hour);
    if(h!==9||m<15||m>=30)continue;
    const bucket=15+Math.floor((m-15)/5)*5,key=`${p.year}-${p.month}-${p.day} ${String(h).padStart(2,'0')}:${String(bucket).padStart(2,'0')}`;
    const o=num(c[1]),hi=num(c[2]),lo=num(c[3]),cl=num(c[4]);
    if([o,hi,lo,cl].some(v=>v===null))continue;
    const g=groups.get(key);
    if(!g)groups.set(key,[c[0],o,hi,lo,cl]);
    else{g[2]=Math.max(g[2],hi);g[3]=Math.min(g[3],lo);g[4]=cl;}
  }
  return [...groups.values()].sort((a,b)=>Date.parse(String(a[0]))-Date.parse(String(b[0])));
}

export function stateFor(orbCandles, oneMin, direction){
  const ord=orderedCandles;
  const orb=ord(orbCandles).slice(0,3);
  if(orb.length<3)return {status:'⏳ Pending',result:'⏳'};
  const hi=Math.max(...orb.map(c=>Number(c[2]))),lo=Math.min(...orb.map(c=>Number(c[3])));
  if(!Number.isFinite(hi)||!Number.isFinite(lo)||hi<=lo)return {status:'⏳ Pending',result:'⏳'};
  const candles1=ord(oneMin);
  const entry=direction==='LONG'?hi:lo;
  const sl=direction==='LONG'?lo:hi;
  const risk=Math.abs(entry-sl);
  const target=direction==='LONG'?entry+0.4*risk:entry-0.4*risk;
  let active=false;
  for(const c of candles1){
    const h=Number(c[2]),l=Number(c[3]);
    if(!Number.isFinite(h)||!Number.isFinite(l))continue;
    if(!active){
      if(direction==='LONG'){
        const touchedEntry=h>=entry,touchedSl=l<=sl;
        if(touchedEntry&&touchedSl)return {status:'❌ SL',result:'❌'};
        if(touchedEntry){
          active=true;
          if(h>=target)return {status:'🎯 Target',result:'0.4R ✅'};
        }else if(touchedSl){
          return {status:'⚠️ Invalidated level',result:'⚠️'};
        }
      }else{
        const touchedEntry=l<=entry,touchedSl=h>=sl;
        if(touchedEntry&&touchedSl)return {status:'❌ SL',result:'❌'};
        if(touchedEntry){
          active=true;
          if(l<=target)return {status:'🎯 Target',result:'0.4R ✅'};
        }else if(touchedSl){
          return {status:'⚠️ Invalidated level',result:'⚠️'};
        }
      }
    }else if(direction==='LONG'){
      const touchedTarget=h>=target,touchedSl=l<=sl;
      if(touchedTarget&&touchedSl)return {status:'❌ SL',result:'❌'};
      if(touchedTarget)return {status:'🎯 Target',result:'0.4R ✅'};
      if(touchedSl)return {status:'❌ SL',result:'❌'};
    }else{
      const touchedTarget=l<=target,touchedSl=h>=sl;
      if(touchedTarget&&touchedSl)return {status:'❌ SL',result:'❌'};
      if(touchedTarget)return {status:'🎯 Target',result:'0.4R ✅'};
      if(touchedSl)return {status:'❌ SL',result:'❌'};
    }
  }
  return active?{status:'✅ Trade Active',result:'⚖️'}:{status:'⏳ Pending',result:'⏳'};
}

export default async function handler(req,res){
  res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Methods','GET,OPTIONS');res.setHeader('Access-Control-Allow-Headers','Content-Type');res.setHeader('Cache-Control','no-store,max-age=0');
  if(req.method==='OPTIONS')return res.status(204).end();if(req.method!=='GET')return res.status(405).json({error:'GET only'});
  try{
    const raw=await fetch('https://raw.githubusercontent.com/TheCinematicTravellers/ipo-listing-tracker/main/fno_universe.json',{cache:'no-store'}),symbolsData=await raw.json(),symbols=Array.isArray(symbolsData)?symbolsData:JSON.parse(symbolsData.content),m=await master(),matched=symbols.map(s=>({symbol:s,token:m.get(norm(s))})).filter(x=>x.token),missing=symbols.filter(s=>!m.get(norm(s))),a=await login(),rows=[];
    for(let i=0;i<matched.length;i+=50){const batch=matched.slice(i,i+50),f=await quote(a,batch.map(x=>String(x.token))),by=new Map(f.map(x=>[String(x.symbolToken),x]));for(const x of batch){const q=by.get(String(x.token));if(!q)continue;const open=num(q.open),high=num(q.high),low=num(q.low),cmp=num(q.ltp),close=num(q.close),volume=num(q.tradeVolume);if([open,high,low,cmp,close].some(v=>v===null)||!close)continue;rows.push({symbol:x.symbol,token:x.token,change_pct:(cmp/close-1)*100,open,high,low,cmp,volume})}}
    const gainers=rows.filter(x=>Math.abs(x.open-x.low)<1e-7).sort((a,b)=>b.change_pct-a.change_pct).slice(0,10),losers=rows.filter(x=>Math.abs(x.open-x.high)<1e-7).sort((a,b)=>a.change_pct-b.change_pct).slice(0,10);
    const p=parts(),start=`${p.year}-${p.month}-${p.day} 09:15`,end=`${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
    const statusErrors=[];
    for(const x of gainers.concat(losers)){
      try{
        const combined=orderedCandles(await angelCandleRequest(a,x.token,start,end,'ONE_MINUTE'));
        const orb=buildOrb5m(combined);
        const postOrb=combined.filter(c=>{const t=Date.parse(String(c[0]));return t>=Date.parse(`${p.year}-${p.month}-${p.day}T09:30:00+05:30`)});
        if(orb.length<3)throw Error(`Insufficient ORB 5m data: ${orb.length}`);
        const s=stateFor(orb,postOrb,gainers.includes(x)?'LONG':'SHORT');x.status=s.status;x.result=s.result;
      }catch(e){
        console.error(`state ${x.symbol}:`,e);statusErrors.push({symbol:x.symbol,error:e.message||String(e)});
        x.status='⏳ Pending';x.result='⏳';
      }
      x.change_pct=Number(x.change_pct.toFixed(2));
    }
    return res.status(200).json({date_ist:new Intl.DateTimeFormat('en-IN',{timeZone:IST,day:'2-digit',month:'short',year:'numeric'}).format(new Date()),updated_ist:stamp(),timezone:IST,universe_size:symbols.length,available:rows.length,matched:matched.length,missing,gainers,losers,status_errors:statusErrors});
  }catch(e){console.error(e);return res.status(500).json({error:e.message||'AUTO feed failed'})}
}
