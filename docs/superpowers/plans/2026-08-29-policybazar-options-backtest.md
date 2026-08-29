# POLICYBZR Options Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible historical-options pipeline that converts the finalized POLICYBZR S1 stock signals into monthly-expiry ATM option trades and evaluates both stock-driven and option-driven exits by expiry week.

**Architecture:** Keep the finalized stock S1 signal engine as the source of truth. Add a contract resolver that maps each signal date/time and stock breakout price to the applicable monthly expiry and nearest ATM strike, then download only the required CE/PE contracts through Angel One Historical API and cache raw 5-minute OHLC locally. A separate backtest layer joins stock signals to option candles and produces two exit models without changing the source option data.

**Tech Stack:** Python 3.14, pandas, SmartAPI/Angel One Historical API, local CSV/JSON cache, pytest.

**Spec:** POLICYBZR S1 final rules: Tuesday-Wednesday-Thursday only; 09:15 first 5-minute ORB; first break of ORB high = LONG, first break of ORB low = SHORT; breakout must occur before 10:00 IST; stock target = 1R using original 09:15 high-low range; stock SL = opposite ORB side; unresolved stock trade exits at 15:05 IST close; final stock baseline quantity = 100 shares. Options: BUY ATM CE for LONG and BUY ATM PE for SHORT, monthly expiry applicable to the signal date, ATM selected from the actual Angel strike ladder at signal time. Produce both stock-driven and option-driven exit analyses and split results by week-of-expiry.

## Global Constraints

- Never select an option strike by guessing a strike interval; use only strikes present in Angel's instrument master.
- Never use future information to choose expiry or ATM strike.
- Preserve the raw downloaded option candles and a manifest mapping every signal to its contract.
- Use Asia/Kolkata timestamps consistently.
- Angel Historical API requests must respect its documented 5-minute maximum request window and rate limit; current official documentation states 5-minute data supports up to 100 days/request and the historical endpoint is limited to 3 requests/second. 
- Do not alter the finalized POLICYBZR stock S1 rules while building the option layer.
- Do not silently fill missing option candles. Missing data must be reported and the affected trade marked unavailable.
- Option-driven SL/target must be an explicit configuration, not silently inferred from stock risk. The first implementation supports a parameterized option stop percentage and option 1R target; no default is declared as a final trading rule.

---

### Task 1: Lock the option research specification

**Files:**
- Create: `fno_1m/policybazar_options_spec.py`
- Test: `fno_1m/test_policybazar_options_spec.py`

**Interfaces:**
- Produces immutable constants/functions for session dates, monthly expiry selection, ATM selection and expiry-week classification.

- [ ] **Step 1: Write failing tests**

Test that Tue/Wed/Thu are accepted, Monday/Friday rejected, monthly expiry means the nearest listed monthly expiry on or after the signal date, ATM is the nearest actual paired strike to stock price, and expiry week is computed from calendar trading days remaining to expiry.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest fno_1m/test_policybazar_options_spec.py -v`

Expected: FAIL because the module does not yet exist.

- [ ] **Step 3: Implement minimal pure functions**

Implement `is_policybazar_s1_day(date)`, `select_monthly_expiry(expiries, signal_date)`, `select_atm_strike(paired_strikes, stock_price)`, and `expiry_week(signal_date, expiry_date, trading_dates)`.

- [ ] **Step 4: Run tests and confirm pass**

Run: `pytest fno_1m/test_policybazar_options_spec.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: define POLICYBZR option research spec`

### Task 2: Build signal-to-contract manifest

**Files:**
- Create: `fno_1m/build_policybazar_option_manifest.py`
- Create: `fno_1m/test_policybazar_option_manifest.py`

**Interfaces:**
- Consumes the finalized POLICYBZR 5-minute CSV plus Angel OpenAPIScripMaster JSON.
- Produces `data/policybazar_options/manifest.csv` with one row per eligible stock S1 signal and fields for signal date/time, side, stock breakout, stock SL, stock 1R, expiry, ATM strike, CE/PE symbol/token, lot size, and expiry week.

- [ ] **Step 1: Write tests**

Test a synthetic stock signal where a LONG at stock price 1287 maps to the nearest paired monthly strike 1290, while a SHORT maps to PE; test that an unpaired strike is skipped and that an expiry before the signal date is never selected.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest fno_1m/test_policybazar_option_manifest.py -v`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement manifest builder**

Reuse the existing `option_feed.py` master normalization logic where possible, but make the historical resolver date-aware and explicitly choose the nearest monthly expiry. Do not reuse the live runner's current-nearest-expiry shortcut if it could select a weekly contract.

- [ ] **Step 4: Run tests**

Run: `pytest fno_1m/test_policybazar_option_manifest.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: map POLICYBZR S1 signals to monthly ATM contracts`

### Task 3: Build targeted Angel option downloader

**Files:**
- Create: `fno_1m/download_policybazar_options.py`
- Create: `fno_1m/test_policybazar_option_downloader.py`

**Interfaces:**
- Consumes `manifest.csv` and Angel credentials/environment.
- Produces raw cached 5-minute CSVs under `data/policybazar_options/raw/<token>/<date>.csv` and a download log.

- [ ] **Step 1: Write tests**

Test request-window splitting into at most 100 calendar days for FIVE_MINUTE, correct timestamp formatting, deduplication of overlapping rows, and that HTTP/API failures are logged without creating fabricated candles.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest fno_1m/test_policybazar_option_downloader.py -v`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement downloader**

Authenticate with the existing SmartAPI pattern, call `getCandleData` with exchange `NFO`, the historical option token, interval `FIVE_MINUTE`, and bounded date windows. Cache every response before proceeding to the next contract. Add a conservative delay between requests and resume from already-cached files. The official Angel documentation supports NFO historical candles and lists FIVE_MINUTE with a maximum 100-day request window. urlAngel One SmartAPI Historical API documentationhttps://smartapi.angelone.in/docs/Portfolio

- [ ] **Step 4: Run tests**

Run: `pytest fno_1m/test_policybazar_option_downloader.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: download targeted POLICYBZR option history`

### Task 4: Build dual option backtest engine

**Files:**
- Create: `fno_1m/backtest_policybazar_options.py`
- Create: `fno_1m/test_policybazar_options_backtest.py`

**Interfaces:**
- Consumes finalized stock signals, manifest, and raw option candles.
- Produces one row per option trade containing stock signal data, option contract, expiry week, option entry, stock exit event, stock-driven option exit, option-driven exit, and P&L.

- [ ] **Step 1: Write tests**

Test that a LONG stock signal buys CE and SHORT buys PE; option entry is the first available option candle at/after the stock breakout time; stock-driven exit occurs at the exact stock target/SL/15:05 event; option-driven target/SL are calculated solely from configured option entry and stop parameters; same-candle target/SL ambiguity is marked `AMBIGUOUS` rather than guessed.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest fno_1m/test_policybazar_options_backtest.py -v`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement backtest engine**

Stock-driven model:
- Entry = first available option price at/after stock breakout timestamp.
- Exit when the stock hits its 1R target, stock SL, or 15:05 close.
- Option P&L = option exit minus option entry for bought CE/PE.

Option-driven model:
- Entry = same option entry.
- Stop percentage is a CLI/config parameter.
- Option target = entry + one option-risk unit.
- Unresolved option trade exits at 15:05 close.
- No default option stop percentage is declared final until the user selects it after seeing the raw distribution.

- [ ] **Step 4: Run tests**

Run: `pytest fno_1m/test_policybazar_options_backtest.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add dual POLICYBZR option backtests`

### Task 5: Build reporting and expiry-week analysis

**Files:**
- Create: `fno_1m/report_policybazar_options.py`
- Create: `fno_1m/test_policybazar_option_report.py`

**Interfaces:**
- Consumes backtest CSV.
- Produces CSV summaries and a human-readable report split by expiry week, LONG/SHORT, CE/PE, monthly expiry, and month.

- [ ] **Step 1: Write tests**

Test aggregation for Week 1/2/3/Expiry Week, correct P&L sums, trade counts, win rates, PF, average option return, and missing-data counts.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest fno_1m/test_policybazar_option_report.py -v`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement report**

Produce:
- `policybazar_option_trades.csv`
- `policybazar_option_weekly_summary.csv`
- `policybazar_option_monthly_summary.csv`
- `policybazar_option_data_quality.csv`

- [ ] **Step 4: Run tests**

Run: `pytest fno_1m/test_policybazar_option_report.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: report POLICYBZR option expiry-week performance`

### Task 6: End-to-end dry run and documentation

**Files:**
- Create: `fno_1m/run_policybazar_options.py`
- Modify: `fno_1m/README.md`
- Create: `fno_1m/test_policybazar_options_e2e.py`

**Interfaces:**
- CLI orchestrates manifest → download → backtest → report, with separate `--manifest-only`, `--download`, `--backtest`, `--report`, and `--all` modes.

- [ ] **Step 1: Write E2E test using fixture data**

Use a tiny synthetic stock/options fixture so `--all` completes without Angel network access and produces the expected manifest and report files.

- [ ] **Step 2: Run E2E test and confirm failure**

Run: `pytest fno_1m/test_policybazar_options_e2e.py -v`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement CLI orchestration and documentation**

Document environment variables, output folders, how to resume interrupted downloads, and the exact finalized stock S1 rules. Link the official Angel instrument-master documentation for the source of contract metadata. urlAngel One SmartAPI Instruments documentationhttps://smartapi.angelone.in/docs

- [ ] **Step 4: Run full test suite**

Run: `pytest fno_1m -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: complete POLICYBZR options research pipeline`

---

## Self-review checklist

- The finalized POLICYBZR stock S1 logic remains unchanged.
- Monthly expiry is resolved from actual listed contracts, never guessed.
- ATM is selected from actual paired strikes using the stock price at signal time.
- Raw option data is cached and auditable.
- Missing option history cannot silently become a zero-P&L trade.
- Both stock-driven and option-driven exit models are preserved from the same raw data.
- Expiry-week segmentation is generated from actual expiry dates and trading calendars.
- The eventual result can be regenerated without relying on this conversation for hidden assumptions.
