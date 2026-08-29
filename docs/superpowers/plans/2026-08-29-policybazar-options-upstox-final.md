# Policybazaar Upstox Options Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Angel-only historical option pipeline with a reproducible Upstox Plus pipeline that resolves historical POLICYBZR monthly contracts, downloads 5-minute candles, computes stock-driven option P&L, and produces weekly/monthly reports for the frozen 90 S1 trades.

**Architecture:** Keep the existing S1 manifest/backtest/report separation, but add an Upstox-specific historical-contract resolver and candle downloader. The resolver calls the expired option-contract API for each required monthly expiry, maps the nearest paired ATM strike, and writes an immutable manifest; the downloader caches expired 5-minute candles by historical instrument key; the backtest consumes only the manifest and cache and preserves the existing stock-driven primary exit plus the optional configurable option-driven sensitivity.

**Tech Stack:** Python 3.14, pandas, requests, pytest, Upstox REST APIs, existing CSV pipeline.

**Spec:** `docs/superpowers/specs/2026-08-29-policybazar-options-backtest-design.md`

## Global Constraints

- Frozen stock input is exactly the authoritative 90-trade `POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv`.
- Only Tuesday/Wednesday/Thursday signals before 10:00 IST with body >20% are valid.
- Historical contracts must come from Upstox expired-instrument APIs; never substitute current contracts.
- LONG maps to CE and SHORT maps to PE at the nearest paired ATM strike to stock entry.
- Option entry is the first option 5-minute candle strictly after the stock signal timestamp, using that candle OPEN.
- Primary P&L is stock-driven using the frozen stock exit; option-driven sensitivity is explicitly secondary and configurable.
- Cache all downloaded candles and preserve data-quality failures.

---

### Task 1: Add pure historical-expiry and contract-selection helpers

**Files:**
- Modify: `fno_1m/policybazar_options_spec.py`
- Test: `fno_1m/test_policybazar_options_spec.py`

**Interfaces:**
- `historical_monthly_expiry_for_signal(signal_date, trading_dates) -> date`
- `select_atm_strike(paired_strikes, stock_price) -> float`
- `expiry_week_label(signal_date, expiry_date, trading_dates) -> str`

- [ ] **Step 1: Write failing tests**

```python
from datetime import date
import pytest
from policybazar_options_spec import historical_monthly_expiry_for_signal, select_atm_strike


def test_august_2026_signal_uses_last_tuesday():
    dates = [date(2026, 8, d) for d in range(1, 19) if date(2026, 8, d).weekday() < 5]
    assert historical_monthly_expiry_for_signal(date(2026, 8, 12), dates) == date(2026, 8, 18)


def test_atm_strike_uses_nearest_paired_strike():
    assert select_atm_strike([1700, 1720, 1740], 1733) == 1740


def test_atm_tie_prefers_lower_strike():
    assert select_atm_strike([1700, 1760], 1730) == 1700


def test_no_expiry_after_signal_raises():
    with pytest.raises(ValueError):
        historical_monthly_expiry_for_signal(date(2026, 9, 1), [date(2026, 8, 25)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest fno_1m/test_policybazar_options_spec.py -q`
Expected: FAIL because the current helper uses a month candidate list that does not support a signal whose calendar-month expiry is not in the supplied truncated trading calendar.

- [ ] **Step 3: Implement minimal helper behavior**

Keep the existing Tuesday-after-August-2025 rule and require the calendar to contain the resolved expiry. Preserve the existing nearest-strike tie-breaker.

- [ ] **Step 4: Run the focused test**

Run: `pytest fno_1m/test_policybazar_options_spec.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fno_1m/policybazar_options_spec.py fno_1m/test_policybazar_options_spec.py
git commit -m "test: cover historical Policybazaar expiry selection"
```

---

### Task 2: Build Upstox historical contract manifest

**Files:**
- Create: `fno_1m/build_policybazar_upstox_manifest.py`
- Create: `fno_1m/test_build_policybazar_upstox_manifest.py`
- Modify: `fno_1m/run_policybazar_options.py`

**Interfaces:**
- `fetch_expired_contracts(session, underlying_key, expiry_date) -> list[dict]`
- `resolve_manifest(signals, trading_dates, contract_provider) -> list[dict]`
- CLI `build_policybazar_upstox_manifest.py --stock-csv --calendar-csv --output`

- [ ] **Step 1: Write failing tests for API response parsing and manifest mapping**

```python
from datetime import date
from build_policybazar_upstox_manifest import choose_contract_pair, resolve_manifest


def test_choose_contract_pair_selects_nearest_paired_strike():
    contracts = [
        {"strike_price": 1700, "instrument_type": "CE", "instrument_key": "ce1700", "lot_size": 350},
        {"strike_price": 1700, "instrument_type": "PE", "instrument_key": "pe1700", "lot_size": 350},
        {"strike_price": 1740, "instrument_type": "CE", "instrument_key": "ce1740", "lot_size": 350},
        {"strike_price": 1740, "instrument_type": "PE", "instrument_key": "pe1740", "lot_size": 350},
    ]
    pair = choose_contract_pair(contracts, 1733)
    assert pair["strike"] == 1740
    assert pair["ce"]["instrument_key"] == "ce1740"
    assert pair["pe"]["instrument_key"] == "pe1740"


def test_resolve_manifest_maps_long_to_ce_and_short_to_pe():
    signals = [{"date": "2026-08-12", "side": "LONG", "stock_entry": 1733, "stock_breakout_time": "09:35", "weekday": "Wednesday", "body_pct": 0.4, "stock_sl": 1700, "stock_target_1r": 1766, "stock_range_1r": 33}]
    calendar = [date(2026, 8, d) for d in range(3, 19) if date(2026, 8, d).weekday() < 5]
    def provider(expiry):
        assert expiry == date(2026, 8, 18)
        return [
            {"strike_price": 1740, "instrument_type": "CE", "instrument_key": "ce", "trading_symbol": "POLICYBZR 1740 CE 18 AUG 26", "lot_size": 350, "exchange_token": "1"},
            {"strike_price": 1740, "instrument_type": "PE", "instrument_key": "pe", "trading_symbol": "POLICYBZR 1740 PE 18 AUG 26", "lot_size": 350, "exchange_token": "2"},
        ]
    out = resolve_manifest(signals, calendar, provider)
    assert out[0]["option_instrument_key"] == "ce"
    assert out[0]["option_type"] == "CE"
    assert out[0]["expiry"] == "2026-08-18"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest fno_1m/test_build_policybazar_upstox_manifest.py -q`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the Upstox resolver**

Read `UPSTOX_ACCESS_TOKEN` from the environment. Call `GET https://api.upstox.com/v2/expired-instruments/option/contract` with `instrument_key=NSE_EQ|INE417T01026` and `expiry_date=YYYY-MM-DD`. Reject non-200 responses, especially `UDAPI1149`, with a clear message. Cache each expiry response under the manifest data directory. Build one row per stock signal with expiry, expiry-week, ATM strike, option type, expired instrument key, symbol, lot size, and exchange token. Do not fall back to the current instrument master.

- [ ] **Step 4: Run focused tests**

Run: `pytest fno_1m/test_build_policybazar_upstox_manifest.py -q`
Expected: PASS.

- [ ] **Step 5: Run manifest against the real 90-trade CSV**

```powershell
python build_policybazar_upstox_manifest.py `
  --stock-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv" `
  --calendar-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv" `
  --output "data\policybazar_options\upstox_manifest.csv"
```

Expected: 90 manifest rows and no current-contract substitution.

- [ ] **Step 6: Commit**

```bash
git add fno_1m/build_policybazar_upstox_manifest.py fno_1m/test_build_policybazar_upstox_manifest.py fno_1m/run_policybazar_options.py
git commit -m "feat: resolve historical Policybazaar option contracts via Upstox"
```

---

### Task 3: Download and cache expired 5-minute option candles

**Files:**
- Create: `fno_1m/download_policybazar_upstox.py`
- Create: `fno_1m/test_download_policybazar_upstox.py`
- Modify: `fno_1m/run_policybazar_options.py`

**Interfaces:**
- `fetch_expired_candles(session, expired_instrument_key, start_date, end_date) -> DataFrame`
- `cache_option_candles(manifest, raw_root) -> int`

- [ ] **Step 1: Write failing tests**

```python
import pandas as pd
from download_policybazar_upstox import parse_candles, cache_path


def test_parse_candles_preserves_ist_and_ohlcv():
    payload = {"status": "success", "data": {"candles": [["2026-08-12T09:40:00+05:30", 10, 12, 9, 11, 350, 7000]]}}
    out = parse_candles(payload)
    assert list(out.columns) == ["datetime", "open", "high", "low", "close", "volume", "open_interest"]
    assert str(out.iloc[0]["datetime"].tz) == "Asia/Kolkata"
    assert out.iloc[0]["open"] == 10


def test_cache_path_uses_expired_instrument_key(tmp_path):
    assert cache_path(tmp_path, "NSE_FO|139523|25-08-2026") == tmp_path / "NSE_FO|139523|25-08-2026" / "candles.csv"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest fno_1m/test_download_policybazar_upstox.py -q`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the downloader**

Call `GET https://api.upstox.com/v2/expired-instruments/historical-candle/{expired_instrument_key}/5minute/{to_date}/{from_date}`. URL-encode the expired key. Cache one CSV per historical instrument key. Query only the signal-date range needed by the manifest, with a small same-day buffer through 15:35 IST. Never overwrite an existing non-empty cache file.

- [ ] **Step 4: Run focused tests**

Run: `pytest fno_1m/test_download_policybazar_upstox.py -q`
Expected: PASS.

- [ ] **Step 5: Download the 90-trade option candle set**

```powershell
python run_policybazar_options.py `
  --stock-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv" `
  --calendar-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv" `
  --mode download
```

Expected: only the historical contracts appearing in the 90-trade manifest are downloaded; rerunning uses `[CACHE]` and does not redownload them.

- [ ] **Step 6: Commit**

```bash
git add fno_1m/download_policybazar_upstox.py fno_1m/test_download_policybazar_upstox.py fno_1m/run_policybazar_options.py
git commit -m "feat: cache historical Policybazaar option candles"
```

---

### Task 4: Make the option backtest primary stock-driven and data-quality strict

**Files:**
- Modify: `fno_1m/backtest_policybazar_options.py`
- Create: `fno_1m/test_backtest_policybazar_options.py`

**Interfaces:**
- `first_option_entry(...) -> tuple[Timestamp, float] | None`
- `stock_exit(...) -> tuple[Timestamp, float, str]`
- `option_close_at(...) -> tuple[Timestamp, float] | None`
- `run(...) -> int`

- [ ] **Step 1: Write failing tests**

```python
import pandas as pd
from backtest_policybazar_options import first_option_entry, option_close_at


def test_option_entry_uses_first_candle_strictly_after_signal():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime(["2026-08-12 09:35:00+05:30", "2026-08-12 09:40:00+05:30"]),
        "open": [10, 12], "high": [11, 13], "low": [9, 11], "close": [10.5, 12.5]
    })
    dt, px = first_option_entry(opt, pd.Timestamp("2026-08-12 09:35:00+05:30"))
    assert str(dt) == "2026-08-12 09:40:00+05:30"
    assert px == 12


def test_option_close_at_uses_last_available_candle_before_stock_exit():
    opt = pd.DataFrame({
        "datetime": pd.to_datetime(["2026-08-12 09:40:00+05:30", "2026-08-12 09:45:00+05:30"]),
        "open": [10, 11], "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5]
    })
    dt, px = option_close_at(opt, pd.Timestamp("2026-08-12 09:47:00+05:30"))
    assert str(dt) == "2026-08-12 09:45:00+05:30"
    assert px == 11.5
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest fno_1m/test_backtest_policybazar_options.py -q`
Expected: FAIL if the existing implementation does not match the exact boundary assertions.

- [ ] **Step 3: Implement minimal strict behavior**

Keep the stock exit logic unchanged. For each manifest row, use the selected CE/PE historical instrument key, enter on the first option candle strictly after the stock signal, and calculate the primary option P&L from the option close at the stock exit timestamp. Preserve the secondary option-driven scenario behind `--option-stop-pct`.

- [ ] **Step 4: Run focused and existing tests**

Run: `pytest fno_1m/test_backtest_policybazar_options.py -q`
Run: `pytest fno_1m -q`
Expected: all relevant tests PASS.

- [ ] **Step 5: Run the real backtest**

```powershell
python run_policybazar_options.py `
  --stock-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv" `
  --calendar-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv" `
  --mode backtest
```

Expected: 90 output rows with explicit `OK` or data-quality status; no silent drops.

- [ ] **Step 6: Commit**

```bash
git add fno_1m/backtest_policybazar_options.py fno_1m/test_backtest_policybazar_options.py
git commit -m "feat: backtest option translation of frozen S1 signals"
```

---

### Task 5: Expand reporting and produce reproducibility artifacts

**Files:**
- Modify: `fno_1m/report_policybazar_options.py`
- Create: `fno_1m/test_report_policybazar_options.py`
- Modify: `fno_1m/run_policybazar_options.py`

**Interfaces:**
- `summarize(df, pnl_col) -> DataFrame`
- `max_drawdown(pnl_series) -> float`

- [ ] **Step 1: Write failing tests**

```python
import pandas as pd
from report_policybazar_options import max_drawdown, summarize


def test_max_drawdown_is_peak_to_trough():
    assert max_drawdown(pd.Series([100, -50, 25, -200, 50])) == 200


def test_summary_separates_week_and_side():
    df = pd.DataFrame({
        "status": ["OK", "OK"], "expiry_week": ["WEEK_1", "WEEK_1"], "side": ["LONG", "SHORT"],
        "option_driven_option_pnl": [100, -50], "date": ["2026-08-05", "2026-08-06"]
    })
    out = summarize(df, "option_driven_option_pnl")
    assert set(out["side"]) == {"LONG", "SHORT"}
    assert set(out["expiry_week"]) == {"WEEK_1"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest fno_1m/test_report_policybazar_options.py -q`
Expected: FAIL because `max_drawdown` does not yet exist or summary lacks drawdown metrics.

- [ ] **Step 3: Implement reporting**

Produce: `weekly_summary_stock_driven.csv`, `weekly_summary_option_driven.csv`, `monthly_summary_stock_driven.csv`, `monthly_summary_option_driven.csv`, `long_short_summary.csv`, `data_quality.csv`, and `final_summary.csv`. Include trades, wins, losses, win %, gross profit, gross loss, net P&L, average P&L, profit factor, and max drawdown. Keep stock-driven and option-driven results visibly separate.

- [ ] **Step 4: Run focused and full tests**

Run: `pytest fno_1m/test_report_policybazar_options.py -q`
Run: `pytest fno_1m -q`
Expected: PASS.

- [ ] **Step 5: Run the full pipeline**

```powershell
python run_policybazar_options.py `
  --stock-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_S1_FINAL_BODY_GT20_QTY100_90TRADES.csv" `
  --calendar-csv "C:\Users\megha\nse_fno_orb\historical_5m\POLICYBZR_5m.csv" `
  --mode all
```

Expected: manifest, raw cache, trades, and summaries are all produced.

- [ ] **Step 6: Commit**

```bash
git add fno_1m/report_policybazar_options.py fno_1m/test_report_policybazar_options.py fno_1m/run_policybazar_options.py
 git commit -m "feat: report Policybazaar option backtest by expiry week"
```

---

### Task 6: Verify the implementation and prepare handoff

**Files:**
- Modify: `fno_1m/README.md` if present, otherwise create `fno_1m/POLICYBAZAR_OPTIONS_README.md`
- Create: `fno_1m/data/policybazar_options/README.md`

- [ ] **Step 1: Run the complete test suite**

Run: `pytest fno_1m -q`
Expected: PASS with zero failures.

- [ ] **Step 2: Verify the manifest**

Run a Python assertion that `upstox_manifest.csv` contains exactly 90 rows, every row has a historical expired instrument key, both CE and PE keys, an expiry, an ATM strike, and an expiry-week label.

- [ ] **Step 3: Verify cache completeness**

Run a Python assertion that every `option_instrument_key` in the manifest has a non-empty `candles.csv` cache unless its trade is explicitly marked as a data-quality failure.

- [ ] **Step 4: Verify no current-contract fallback**

Search the Upstox implementation for `option/contract` and ensure current-contract API calls are not used to resolve historical signal contracts. The historical resolver must use `/expired-instruments/option/contract` only.

- [ ] **Step 5: Document exact run commands and data provenance**

Record the two source CSV paths, Upstox underlying key, API endpoints, entry timing rule, exit rules, expiry-week definition, cache location, and output filenames in the data README.

- [ ] **Step 6: Commit**

```bash
git add fno_1m/POLICYBAZAR_OPTIONS_README.md fno_1m/data/policybazar_options/README.md
git commit -m "docs: document Policybazaar options backtest provenance"
```
