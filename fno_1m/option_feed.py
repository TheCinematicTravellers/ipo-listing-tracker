"""NFO contract resolution for the 1-minute forward test.

No broker orders are placed here. The module resolves option contracts from
Angel One's NFO master. Strike selection is always taken from the actual
Angel strike ladder; we never invent a strike interval.
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
    """Return strike in rupees from Angel's master value.

    Angel NFO masters commonly store strikes scaled by 100, including values
    such as 43000 for a Rs 430 strike and 130000 for Rs 1300.  We normalize
    that representation, but the strike itself must always come from a row in
    the Angel master, never from a guessed interval.
    """
    raw = row.get("strike")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value / 100.0


def find_atm_contracts(
    master: Iterable[dict],
    underlying: str,
    ltp: float,
    today: date | None = None,
) -> dict:
    """Resolve Angel's nearest-expiry ATM and ATM-1 CE/PE contracts.

    ATM is the closest strike in Angel's actual strike ladder. ATM-1 is the
    immediately lower strike in that same Angel-provided ladder. No fixed
    strike step is assumed. Both CE and PE must exist for the selected strike.
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
        option_type = symbol[-2:]
        if expiry is None or expiry < today or strike is None or option_type not in {"CE", "PE"}:
            continue
        if not row.get("token"):
            continue
        candidates.append((expiry, strike, option_type, row))

    if not candidates:
        raise RuntimeError(f"No NFO option contracts found for {name}")

    expiry = min(x[0] for x in candidates)
    same_expiry = [x for x in candidates if x[0] == expiry]

    # Only use strikes for which Angel provides both CE and PE. This prevents
    # selecting a one-sided strike that cannot be traded as the paired setup.
    by_strike_type: dict[float, dict[str, dict]] = {}
    for _, strike, option_type, row in same_expiry:
        by_strike_type.setdefault(strike, {})[option_type] = row
    paired_strikes = sorted(
        strike for strike, legs in by_strike_type.items()
        if "CE" in legs and "PE" in legs
    )
    if not paired_strikes:
        raise RuntimeError(f"No paired CE/PE strikes found for {name} expiry {expiry}")

    atm_index = min(range(len(paired_strikes)), key=lambda i: abs(paired_strikes[i] - ltp))
    atm = paired_strikes[atm_index]
    if atm_index == 0:
        raise RuntimeError(f"No lower Angel-provided strike exists below ATM {atm} for {name}")
    atm_minus_1 = paired_strikes[atm_index - 1]

    out: dict[str, object] = {
        "underlying": name,
        "expiry": expiry.strftime("%d%b%Y").upper(),
        "atm": atm,
        "strike": atm_minus_1,
        "atm_minus_1": atm_minus_1,
        "available_strikes": paired_strikes,
    }
    for option_type in ("CE", "PE"):
        row = by_strike_type[atm_minus_1][option_type]
        out[option_type.lower()] = {
            "symbol": str(row.get("symbol")),
            "token": str(row.get("token")),
            "strike": atm_minus_1,
            "lot_size": int(float(row.get("lotsize") or 0)),
        }
        if not out[option_type.lower()]["lot_size"]:
            raise RuntimeError(f"Missing lot size for {row.get('symbol')}")
    return out
