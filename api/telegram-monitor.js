const IST='Asia/Kolkata';
const MONITOR_START_MIN=9*60+30;
const MONITOR_END_MIN=15*60+30;
function nowParts(d=new Date()){const p=new Intl.DateTimeFormat('en-CA',{timeZone:IST,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),o={};for(const x of p)o[x.type]=x.value;return o}
function keyFor(date,symbol){return `orb:${date}:${symbol}`}
function minutes(p){return Number(p.hour)*60+Number(p.minute)}
function esc(s){return String(s).replace(/[_*\[\]()~`>#+\-=|{}.!]/g,'\\$&')}
async function redisCommand(command){const base=process.env.UPSTASH_REDIS_REST_URL,token=process.env.UPSTASH_REDIS_REST_TOKEN;if(!base||!token)throw Error('Missing Upstash Redis environment variables');const r=await fetch(base,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify(command)});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||`Redis HTTP ${r.status}`);return d.result}
async function getState(key){return redisCommand(['GET',key])}
async function setState(key,value){return redisCommand(['SET',key,value,'EX','86400'])}
async function telegram(text){const token=process.env.TELEGRAM_BOT_TOKEN,chat=process.env.TELEGRAM_CHAT_ID;if(!token||!chat)throw Error('Missing Telegram environment variables');const r=await fetch(`https://api.telegram.org/bot${token}/sendMessage`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:chat,text,parse_mode:'MarkdownV2',disable_web_page_preview:true})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.description||`Telegram HTTP ${r.status}`);return d}
function counts(rows){const out={target:0,active:0,sl:0,pending:0,invalidated:0};for(const row of rows){const s=String(row.status||'');if(s==='🎯 Target')out.target++;else if(s==='✅ Trade Active')out.active++;else if(s==='❌ SL')out.sl++;else if(s==='⚠️ Invalidated level')out.invalidated++;else out.pending++;}return out}
export function summaryMessage(c){return `*📊 ORB DAILY SUMMARY*\n\n🎯 Target: ${c.target}\n✅ Trade Active: ${c.active}\n❌ SL: ${c.sl}\n⏳ Pending: ${c.pending}\n⚠️ Invalidated: ${c.invalidated}`}
async function fetchScanner(){const base=process.env.SCANNER_BASE_URL||'https://our-screener.vercel.app';const r=await fetch(`${base}/api/fno-movers`,{cache:'no-store'});if(!r.ok)throw Error(`Scanner HTTP ${r.status}`);return r.json()}
export default async function handler(req,res){
  if(req.method!=='GET')return res.status(405).json({error:'GET only'});
  const supplied=String(req.headers.authorization||'').replace(/^Bearer\s+/i,'');
  if(!process.env.MONITOR_SECRET||supplied!==process.env.MONITOR_SECRET)return res.status(401).json({error:'Unauthorized'});
  const p=nowParts(),mins=minutes(p),summary=req.url?.includes('summary=1');
  if(!summary&&(mins<MONITOR_START_MIN||mins>MONITOR_END_MIN))return res.status(200).json({ok:true,monitoring:false,reason:'Outside market monitoring window',time_ist:`${p.hour}:${p.minute}`});
  try{
    const data=await fetchScanner(),rows=[...(data.gainers||[]),...(data.losers||[])];
    if(summary){const c=counts(rows);await telegram(summaryMessage(c));return res.status(200).json({ok:true,summary:true,counts:c,rows:rows.length,time_ist:`${p.hour}:${p.minute}`})}
    const alerts=[];
    for(const row of rows){
      const status=row.status,date=p.year+p.month+p.day,key=keyFor(date,row.symbol),previous=await getState(key);
      if(previous===null){await setState(key,status);continue}
      if(previous===status)continue;
      await setState(key,status);
      if(previous!=='⏳ Pending'||status==='⏳ Pending')continue;
      let title='ORB ALERT';if(status==='🎯 Target')title='ORB TARGET';else if(status==='❌ SL')title='ORB SL';else if(status==='⚠️ Invalidated level')title='ORB INVALIDATED';else if(status==='✅ Trade Active')title='ORB TRADE ACTIVE';
      const text=`*${esc(title)}*\n*${esc(row.symbol)}*\nStatus: ${esc(status)}\nChange: ${esc(row.change_pct+'%')}\nTime: ${esc(`${p.hour}:${p.minute} IST`)}`;
      await telegram(text);alerts.push({symbol:row.symbol,status});
    }
    return res.status(200).json({ok:true,monitoring:true,checked:rows.length,alerts});
  }catch(e){console.error(e);return res.status(500).json({ok:false,error:e.message||'Monitor failed'})}
}
