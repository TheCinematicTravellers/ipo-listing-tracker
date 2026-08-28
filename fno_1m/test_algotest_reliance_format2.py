import re
from datetime import date
from algotest import AlgoTestForward
from option_feed import find_atm_contracts
import forward_runner as runner


def algotest_ticker(angel_symbol: str) -> str:
    text = angel_symbol.upper()
    m = re.fullmatch(r"([A-Z0-9]+)(\d{2})([A-Z]{3})(\d{2})(\d+(?:\.\d+)?)(CE|PE)", text)
    if not m:
        raise ValueError(f"Cannot convert Angel option symbol: {angel_symbol}")
    underlying, dd, mon, yy, strike, opt = m.groups()
    months = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06","JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
    return f"{underlying}{yy}{months[mon]}{dd}{'C' if opt == 'CE' else 'P'}{strike.rstrip('0').rstrip('.') if '.' in strike else strike}"


def nfo_quote(api, token):
    response = api.getMarketData("FULL", {"NFO": [str(token)]})
    if not isinstance(response, dict) or not response.get("status", True):
        raise RuntimeError(f"NFO quote failed: {response}")
    rows = response.get("data", {}).get("fetched", [])
    if not rows:
        raise RuntimeError(f"No NFO quote returned for token {token}: {response}")
    return rows[0]


def main():
    api, _ = runner.login()
    master = runner.load_master()
    nse = runner.nse_tokens(master, ['RELIANCE'])
    q = runner.market_quote(api, [nse['RELIANCE']])
    if not q:
        raise RuntimeError(f"No RELIANCE NSE quote returned: {q}")
    stock_raw = float(q[0]['ltp'])
    stock_ltp = stock_raw / 100 if stock_raw > 10000 else stock_raw
    contracts = find_atm_contracts(master, 'RELIANCE', stock_ltp, date.today())
    symbol = contracts['ce']['symbol']
    nq = nfo_quote(api, contracts['ce']['token'])
    option_raw = float(nq['ltp'])
    option_ltp = option_raw / 100 if option_raw > 10000 else option_raw
    ticker = algotest_ticker(symbol)
    qty = contracts['ce']['lot_size']
    print(f"[RELIANCE] stock LTP={stock_ltp:.2f}")
    print(f"[OPTION] Angel={symbol} token={contracts['ce']['token']} LTP={option_ltp:.2f} AlgoTest={ticker} qty={qty}")
    print(f"[ALGOTEST] ONE FORWARD BUY: {ticker} buy {qty}")
    result = AlgoTestForward().send_entry(ticker, 'LONG', qty)
    print(f"[ALGOTEST] SENT {result}")


if __name__ == '__main__':
    main()
