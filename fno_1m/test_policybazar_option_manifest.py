from datetime import date
import json

import pandas as pd

from build_policybazar_option_manifest import build


def test_manifest_maps_policybzar_to_monthly_atm(tmp_path):
    stock=tmp_path/"stock.csv"
    pd.DataFrame([
        ["2026-08-25 09:15",100,103,99,102,1000],
        ["2026-08-25 09:20",103,104,102,103,1000],
        ["2026-08-25 09:25",103,103,101,102,1000],
    ],columns=["datetime","open","high","low","close","volume"]).to_csv(stock,index=False)
    master=tmp_path/"master.json"
    rows=[]
    for strike in (1000,1020,1040):
        for cp in ("CE","PE"):
            rows.append({"exch_seg":"NFO","instrumenttype":"OPTSTK","name":"POLICYBZR",
                         "expiry":"24SEP2026","strike":strike*100,"symbol":f"POLICYBZR24SEP26{strike}{cp}","token":f"{strike}{cp}","lotsize":125})
    master.write_text(json.dumps(rows),encoding="utf-8")
    out=tmp_path/"manifest.csv"
    assert build(stock,master,out)==1
    m=pd.read_csv(out).iloc[0]
    assert m.atm_strike==1040
    assert m.ce_symbol.startswith("POLICYBZR")
    assert m.pe_symbol.startswith("POLICYBZR")
