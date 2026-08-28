import os
from datetime import date
from algotest import AlgoTestForward
from option_feed import find_atm_contracts
import forward_runner as runner

def algotest_ticker(angel_symbol: str) -> str:
    # AlgoTest Trade Signals option format: UNDERLYING + YYMMDD + C/P + STRIKE
    text = angel_symbol.upper()
    # Angel example: RELIANCE29SEP261280CE
    import re
    m = re.fullmatch(r"([A-Z0-9]+)(\d{2})([A-Z]{3})(\d{2})(\d+(?:\.\d+)?)(CE|PE)", text)
    if not m:
        raise ValueError(f"Cannot convert Angel option symbol: {angel_symbol}")
    underlying, dd, mon, yy, strike, opt = m.groups()
    months = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06","JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
    return f"{underlying}{yy}{months[mon]}{dd}{'C' if opt == 'CE' else 'P'}{strike.rstrip('0').rstrip('.') if '.' in strike else strike}"

def main():
    api, _ = runner.login()
    master = runner.load_master()
    nse = runner.nse_tokens(master, ['RELIANCE'])
    q = runner.market_quote(api, [nse['RELIANCE']])
    stock_ltp = float(q[0]['ltp']) / 100 if float(q[0]['ltp']) > 10000 else float(q[0]['ltp'])
    contracts = find_atm_contracts(master, 'RELIANCE', stock_ltp, date.today())
    symbol = contracts['ce']['symbol']
    nq = runner.market_quote(api, [contracts['ce']['token']])
    option_ltp = float(nq[0]['ltp']) / 100 if float(nq[0]['ltp']) > 10000 else float(nq[0]['ltp'])
    ticker = algotest_ticker(symbol)
    qty = contracts['ce']['lot_size']
    print(f"[RELIANCE] stock LTP={stock_ltp:.2f}")
    print(f"[OPTION] Angel={symbol} LTP={option_ltp:.2f} AlgoTest={ticker} qty={qty}")
    print(f"[ALGOTEST] ONE FORWARD BUY: {ticker} buy {qty}")
    result = AlgoTestForward().send_entry(ticker, 'LONG', qty)
    print(f"[ALGOTEST] SENT {result}")

if __name__ == '__main__':
    main()
