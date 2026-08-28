"""NFO contract resolution for the 1-minute forward test.

No broker orders are placed here.  The module only resolves the current
nearest-expiry ATM CE/PE and exposes the token/lot size needed by the live
market-data layer.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable


def _expiry_value(value: object) -> date | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _strike(row: dict) -> float | None:
    raw = row.get("strike")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # Angel's NFO master commonly stores strikes scaled by 100.
    return value / 100.0 if value >= 100000 else value


def find_atm_contracts(
    master: Iterable[dict],
    underlying: str,
    ltp: float,
    today: date | None = None,
) -> dict:
    """Resolve nearest-expiry ATM CE + PE for an underlying.

    Returns symbol, token, strike and lot size for both legs.  Raises a
    RuntimeError instead of silently selecting a wrong contract.
    """
    if ltp <= 0:
        raise ValueError("ltp must be positive")
    name = str(underlying).upper().removesuffix("-EQ")
    today = today or date.today()
    candidates: list[tuple[date, float, str, dict]] = []

    for row in master:
        if str(row.get("exch_seg", "")).upper() != "NFO":
            continue
        instrument = str(row.get("instrumenttype", "")).upper()
        if instrument not in {"OPTSTK", "OPTIDX"}:
            continue
        row_name = str(row.get("name", "")).upper()
        symbol = str(row.get("symbol", "")).upper()
        if row_name != name and not symbol.startswith(name):
            continue
        expiry = _expiry_value(row.get("expiry"))
        strike = _strike(row)
        option_type = str(row.get("symbol", "")).upper()[-2:]
        if expiry is None or expiry < today or strike is None or option_type not in {"CE", "PE"}:
            continue
        if not row.get("token"):
            continue
        candidates.append((expiry, strike, option_type, row))

    if not candidates:
        raise RuntimeError(f"No NFO option contracts found for {name}")

    expiry = min(x[0] for x in candidates)
    same_expiry = [x for x in candidates if x[0] == expiry]
    strikes = sorted({x[1] for x in same_expiry})
    if not strikes:
        raise RuntimeError(f"No strikes found for {name} expiry {expiry}")
    atm = min(strikes, key=lambda s: abs(s - ltp))

    out: dict[str, object] = {
        "underlying": name,
        "expiry": expiry.strftime("%d%b%Y"),
        "strike": atm,
    }
    for option_type in ("CE", "PE"):
        matches = [x[3] for x in same_expiry if x[1] == atm and x[2] == option_type]
        if not matches:
            raise RuntimeError(f"Missing ATM {option_type} for {name} {expiry} {atm}")
        row = matches[0]
        out[option_type.lower()] = {
            "symbol": str(row.get("symbol")),
            "token": str(row.get("token")),
            "lot_size": int(float(row.get("lotsize") or 0)),
        }
        if not out[option_type.lower()]["lot_size"]:
            raise RuntimeError(f"Missing lot size for {row.get('symbol')}")
    return out
