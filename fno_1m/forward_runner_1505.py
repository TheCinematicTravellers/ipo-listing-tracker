"""15:05 live forward test using locally collected 15:04 candle."""
from __future__ import annotations
import json, os, time as time_mod
from datetime import datetime, time
from zoneinfo import ZoneInfo
os.environ["FORWARD_TEST_ENABLE_ENTRIES"]="true"
os.environ["FORWARD_TEST_ONLY"]="true"
import forward_runner as runner
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
IST=ZoneInfo("Asia/Kolkata")
SETUP_START=time(15,3); ACTIVATION=time(15,5)
class MinuteCandleCollector:
    def __init__(self, minute): self.minute=minute; self._bars={}
    def on_ltp(self, token, ltp, when):
        if when.astimezone(IST).strftime("%H:%M") == self.minute:
            self._bars.setdefault(str(token),[]).append(float(ltp))
    def candle(self, token):
        v=self._bars.get(str(token),[])
        return (v[0],max(v),min(v),v[-1]) if v else None
def wait_until_setup():
    while datetime.now(IST).time()<SETUP_START:
        now=datetime.now(IST); target=datetime.combine(now.date(),SETUP_START,tzinfo=IST)
        print(f"[WAIT] Live setup collection starts 15:03 IST | current={now:%H:%M:%S} | remaining={max(0,int((target-now).total_seconds()))}s")
        time_mod.sleep(min(10,max(1,(target-now).total_seconds())))
def collect(api,feed_token,master,symbols):
    token_map=runner.nse_tokens(master,symbols); c=MinuteCandleCollector("15:03")
    sws=SmartWebSocketV2(api.access_token,runner.API_KEY,runner.CLIENT_ID,feed_token)
    def on_open(ws):
        tokens=list(token_map.values())
        for i in range(0,len(tokens),50): sws.subscribe(f"setup_1505_{i//50}",runner.LTP,[{"exchangeType":runner.NSE,"tokens":tokens[i:i+50]}])
        print(f"[LIVE FEED] Subscribed {len(tokens)} NSE stocks for 15:03 candle")
    def on_data(ws,msg):
        try:
            d=json.loads(msg) if isinstance(msg,str) else msg; tok=str(d.get("token","")); raw=d.get("last_traded_price")
            if tok and raw is not None: c.on_ltp(tok,float(raw)/100,datetime.now(IST))
        except Exception as e: print(f"[SETUP FEED ERROR] {e}")
    sws.on_open=on_open; sws.on_data=on_data; sws.on_error=lambda ws,e: print(f"[SETUP FEED ERROR] {e}"); sws.on_close=lambda ws: None; sws.connect()
    while datetime.now(IST).time()<ACTIVATION: time_mod.sleep(.25)
    try:sws.close_connection()
    except Exception:pass
    print(f"[LOCAL CANDLE] 15:03 complete | stocks with ticks={len(c._bars)}")
    return c
def main():
    if not os.getenv("ALGO_TEST_WEBHOOK_URL","").strip(): raise RuntimeError("Safety stop: ALGO_TEST_WEBHOOK_URL is not configured")
    wait_until_setup(); api,feed=runner.login(); master=runner.load_master(); symbols=runner.load_symbols()
    print(f"[OK] Real F&O universe: {len(runner.nse_tokens(master,symbols))}"); print("[TEST] Setup=15:03-15:04 | Activation=15:05 | Candle source=LIVE WEBSOCKET | Historical candle API=DISABLED"); print("[OK] AlgoTest forward-only webhook configured")
    collector=collect(api,feed,master,symbols)
    def local_candle(_api,token,_day):
        v=collector.candle(token)
        if v is None: raise RuntimeError(f"No live 15:03 candle collected for token {token}")
        return v
    runner.candle_0915=local_candle; runner.run_historical_catchup=lambda *_a,**_k: print("[FORWARD 15:05] Historical catch-up disabled")
    runner.ENTRY_TIME=ACTIVATION
    print(f"[LOCK] Activation reached: {datetime.now(IST):%H:%M:%S} IST"); runner.main()
if __name__=="__main__": main()
