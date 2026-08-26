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
export default async function handler(req,res){
  if(req.method!=='GET')return res.status(405).json({error:'GET only'});
  const supplied=String(req.headers.authorization||'').replace(/^Bearer\s+/i,'');
  if(!process.env.MONITOR_SECRET||supplied!==process.env.MONITOR_SECRET)return res.status(401).json({error:'Unauthorized'});
  const p=nowParts(),mins=minutes(p);
  if(mins<MONITOR_START_MIN||mins>MONITOR_END_MIN)return res.status(200).json({ok:true,monitoring:false,reason:'Outside market monitoring window',time_ist:`${p.hour}:${p.minute}`});
  try{
    const base=process.env.SCANNER_BASE_URL||'https://our-screener.vercel.app';
    const r=await fetch(`${base}/api/fno-movers`,{cache:'no-store'});if(!r.ok)throw Error(`Scanner HTTP ${r.status}`);
    const data=await r.json(),rows=[...(data.gainers||[]),...(data.losers||[])],alerts=[];
    for(const row of rows){
      const status=row.status,date=p.year+p.month+p.day,key=keyFor(date,row.symbol),previous=await getState(key);
      await setState(key,status);
      if((previous!==null&&previous!=='⏳ Pending')||status==='⏳ Pending')continue;
      let title='ORB ALERT';if(status==='🎯 Target')title='ORB TARGET';else if(status==='❌ SL')title='ORB SL';else if(status==='⚠️ Invalidated level')title='ORB INVALIDATED';else if(status==='✅ Trade Active')title='ORB TRADE ACTIVE';
      const text=`*${esc(title)}*\n*${esc(row.symbol)}*\nStatus: ${esc(status)}\nChange: ${esc(row.change_pct+'%')}\nTime: ${esc(`${p.hour}:${p.minute} IST`)}`;
      await telegram(text);alerts.push({symbol:row.symbol,status});
    }
    return res.status(200).json({ok:true,monitoring:true,checked:rows.length,alerts});
  }catch(e){console.error(e);return res.status(500).json({ok:false,error:e.message||'Monitor failed'})}
}
