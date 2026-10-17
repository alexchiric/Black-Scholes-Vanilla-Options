"""Option-chain access and cleaning.

Network access (yfinance) is isolated in ``get_option_chain`` / ``get_last_price`` /
``get_risk_free_rate``; everything else is pure and testable offline, including
``synthetic_chain`` which builds a chain with the same schema from a known volatility smile.

Time convention: T = (expiry at 16:00 New York time - now) / 365 days  (ACT/365, in years).
The expiry date is taken from the OCC contract symbol (e.g. ``AAPL241115C00230000``), which is
unambiguous, instead of from yfinance's date list.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DAYS_IN_YEAR = 365.0
DEFAULT_RISK_FREE_RATE = 0.05
_NEW_YORK = ZoneInfo("America/New_York")
_OCC_PATTERN = re.compile(
    r"^(?P<root>.+?)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


# --------------------------------------------------------------------------- symbol & time helpers
def parse_occ_symbol(symbol: str) -> dict:
    """Split an OCC option symbol into root, expiry date, call/put flag and strike."""
    m = _OCC_PATTERN.match(str(symbol).strip())
    if not m:
        raise ValueError(f"Not an OCC option symbol: {symbol!r}")
    expiry = date(2000 + int(m["yy"]), int(m["mm"]), int(m["dd"]))   # raises ValueError for e.g. month 13
    return {"root": m["root"], "expiry": expiry, "is_call": m["cp"] == "C", "strike": int(m["strike"]) / 1000.0}


def make_occ_symbol(root: str, expiry: date, is_call: bool, strike: float) -> str:
    return f"{root}{expiry:%y%m%d}{'C' if is_call else 'P'}{int(round(strike * 1000)):08d}"


def year_fraction(expiry: date, now=None) -> float:
    """Years from ``now`` (default: current time) to 16:00 New York time on ``expiry``, ACT/365."""
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    expiry_utc = datetime(expiry.year, expiry.month, expiry.day, 16, 0, tzinfo=_NEW_YORK).astimezone(timezone.utc)
    return (expiry_utc - now_ts.to_pydatetime()).total_seconds() / (DAYS_IN_YEAR * 86400.0)


def _safe_parse(symbol):
    try:
        return parse_occ_symbol(symbol)
    except ValueError:
        return None


# ----------------------------------------------------------------------------------- cleaning
def clean_option_chain(options: pd.DataFrame, now=None) -> pd.DataFrame:
    """Normalise a raw yfinance chain (calls + puts stacked) into the schema the pipelines use.

    Adds: CALL (bool), expirationDate, T (years, ACT/365), dte (calendar days), mid, relSpread.
    Rows with an unparsable contract symbol or already expired are dropped.
    """
    options = options.copy()
    parsed = options["contractSymbol"].map(_safe_parse)
    keep = parsed.notna()
    options, parsed = options.loc[keep].copy(), parsed.loc[keep]

    options["CALL"] = parsed.map(lambda p: p["is_call"]).astype(bool)
    options["expirationDate"] = pd.to_datetime(parsed.map(lambda p: p["expiry"]))
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    options["T"] = options["expirationDate"].map(lambda d: year_fraction(d.date(), now_ts))
    options["dte"] = options["T"] * DAYS_IN_YEAR
    options = options[options["T"] > 0].copy()

    for col in ("bid", "ask", "strike"):
        options[col] = pd.to_numeric(options[col], errors="coerce")
    options["mid"] = (options["bid"] + options["ask"]) / 2.0
    options["relSpread"] = np.where(options["mid"] > 0, (options["ask"] - options["bid"]) / options["mid"], np.nan)

    options = options.drop(columns=["contractSize", "currency", "change", "percentChange",
                                    "lastTradeDate", "lastPrice"], errors="ignore")
    return options.reset_index(drop=True)


# ------------------------------------------------------------------------------ live (network)
def _yf():
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Live data needs yfinance:  pip install yfinance") from exc
    return yf


def get_option_chain(symbol: str, now=None) -> pd.DataFrame:
    """Download the full option chain of ``symbol`` from Yahoo Finance and clean it."""
    ticker = _yf().Ticker(symbol)
    expiry_dates = ticker.options
    if not expiry_dates:
        raise ValueError(f"No expiry dates found for {symbol} (invalid symbol, or no listed options)")

    frames = []
    for d in expiry_dates:
        chain = ticker.option_chain(d)
        frames.append(pd.concat([pd.DataFrame(chain.calls), pd.DataFrame(chain.puts)], ignore_index=True))
    return clean_option_chain(pd.concat(frames, ignore_index=True), now=now)


def get_last_price(symbol: str) -> float:
    """Most recent daily close of ``symbol``."""
    closes = _yf().Ticker(symbol).history(period="5d")["Close"].dropna()
    if closes.empty:
        raise ValueError(f"No price history found for {symbol}")
    return float(closes.iloc[-1])


def get_risk_free_rate(default: float = DEFAULT_RISK_FREE_RATE) -> float:
    """13-week T-bill rate (^IRX, quoted in percent) as a decimal; ``default`` if unavailable."""
    try:
        closes = _yf().Ticker("^IRX").history(period="5d")["Close"].dropna()
        rate = float(closes.iloc[-1]) / 100.0
        return rate if 0.0 <= rate < 0.5 else default
    except Exception:
        return default


# ----------------------------------------------------------------- synthetic (offline / tests)
def synthetic_chain(S: float = 100.0, r: float = 0.045, q: float = 0.0, root: str = "DEMO",
                    days_to_expiry=(7, 30, 90, 180), strikes=None, atm_vol: float = 0.25,
                    term_slope: float = 0.02, skew: float = -0.35, curvature: float = 1.2,
                    half_spread: float = 0.005, now=None) -> pd.DataFrame:
    """Build an option chain (same schema as ``get_option_chain``) from a known smile.

    sigma(K, T) = atm_vol + term_slope*sqrt(T) + skew*ln(K/S) + curvature*ln(K/S)^2   (floored at 5%).
    The true volatility is stored in ``impliedVolatility`` so implied-vol recovery can be checked.
    Used for offline demos and for the test-suite.
    """
    from pricing_engine import run_engine   # local import: keeps the data module light

    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    if strikes is None:
        strikes = np.round(S * np.arange(0.70, 1.3001, 0.025), 2)

    rows = []
    for days in days_to_expiry:
        expiry = (now_ts + timedelta(days=int(days))).date()
        T = year_fraction(expiry, now_ts)
        for K in strikes:
            m = float(np.log(K / S))
            sigma = max(0.05, atm_vol + term_slope * np.sqrt(T) + skew * m + curvature * m * m)
            for is_call in (True, False):
                rows.append({"contractSymbol": make_occ_symbol(root, expiry, is_call, K), "strike": float(K),
                             "CALL": is_call, "expirationDate": pd.Timestamp(expiry), "T": T,
                             "dte": T * DAYS_IN_YEAR, "impliedVolatility": sigma, "volume": 100,
                             "openInterest": 1000})
    chain = pd.DataFrame(rows)

    res = run_engine(pd.DataFrame({"type": chain["CALL"], "S": S, "K": chain["strike"], "T": chain["T"],
                                   "r": r, "q": q, "sigma": chain["impliedVolatility"]}))
    mid = res["price_model"]
    half = np.minimum(half_spread, 0.5 * mid)          # keeps bid > 0 and mid == model price exactly
    chain["bid"] = mid - half
    chain["ask"] = mid + half
    chain["mid"] = (chain["bid"] + chain["ask"]) / 2.0
    chain["relSpread"] = (chain["ask"] - chain["bid"]) / chain["mid"]
    chain["inTheMoney"] = np.where(chain["CALL"], chain["strike"] < S, chain["strike"] > S)
    return chain
