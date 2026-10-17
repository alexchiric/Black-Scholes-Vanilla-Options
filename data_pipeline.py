"""Pipelines that turn a cleaned option chain into valuations and volatility smiles.

All numerical work is done by the C++ engine through ``pricing_engine.run_engine`` - one call
per chain.  Importing this module has no side effects (the original ran a network request at
import time).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from option_data import DEFAULT_RISK_FREE_RATE
from pricing_engine import run_engine

SMILE_COLUMNS = ["expirationDate", "dte", "T", "strike", "optionType", "mid", "moneyness", "iv", "iv_status", "yahooIV"]


def _engine_frame(options: pd.DataFrame, last: float, r: float, q: float) -> pd.DataFrame:
    """Map a cleaned chain to the engine's input columns (market price = bid/ask mid)."""
    return pd.DataFrame({
        "type": np.where(options["CALL"], "call", "put"),
        "S": float(last),
        "K": options["strike"],
        "T": options["T"],
        "r": float(r),
        "q": float(q),
        "price": options["mid"],
    }, index=options.index)


def valuation_pipeline(options_data: pd.DataFrame, contract_symbol: str, last: float,
                       r: float = DEFAULT_RISK_FREE_RATE, q: float = 0.0,
                       vol_source: str = "mid_iv") -> pd.DataFrame:
    """Price and Greeks of one contract.

    ``vol_source``:
      * ``"mid_iv"``   (default) - volatility implied by the bid/ask mid, solved by the engine;
      * ``"yahoo_iv"`` - the ``impliedVolatility`` column supplied by Yahoo Finance.

    Returns a one-row DataFrame: Price, Delta, Gamma, Vega, Theta, Rho (raw analytic units, see
    greeks.h) plus IV, IV_status and Sigma (the volatility the valuation used).
    """
    contract = options_data[options_data["contractSymbol"] == contract_symbol]
    if contract.empty:
        raise ValueError(f"Contract symbol not found in the option data: {contract_symbol!r}")

    frame = _engine_frame(contract, last, r, q)
    if vol_source == "yahoo_iv":
        frame["sigma"] = pd.to_numeric(contract["impliedVolatility"], errors="coerce")
    elif vol_source != "mid_iv":
        raise ValueError("vol_source must be 'mid_iv' or 'yahoo_iv'")

    res = run_engine(frame)
    return pd.DataFrame({
        "Price": res["price_model"], "Delta": res["delta"], "Gamma": res["gamma"], "Vega": res["vega"],
        "Theta": res["theta"], "Rho": res["rho"], "IV": res["iv"], "IV_status": res["iv_status"],
        "Sigma": res["sigma_used"],
    }).reset_index(drop=True)


def vol_smile_pipeline(options_data: pd.DataFrame, last: float, r: float = DEFAULT_RISK_FREE_RATE,
                       q: float = 0.0, expiry=None, otm_only: bool = True, max_rel_spread: float = 0.5,
                       min_bid: float = 0.0, min_days: float = 1.0, keep_failed: bool = False) -> pd.DataFrame:
    """Implied-volatility smile (one expiry) or surface (``expiry=None`` -> all expiries).

    Method (see docs/METHODOLOGY_LOG.md):
      1. Liquidity filter: bid > ``min_bid``, ask >= bid, relative spread <= ``max_rel_spread``,
         at least ``min_days`` calendar days to expiry.
      2. Out-of-the-money convention (``otm_only``): use the put when K < F and the call when
         K >= F, where F = S*exp((r-q)T) is the forward.  OTM options are the liquid ones and are
         the least affected by the early-exercise premium of American-style listed options.
      3. Implied vol from the bid/ask mid by the engine; failures are dropped unless ``keep_failed``.

    Returns one row per option with ``moneyness = ln(K/F)`` and Yahoo's own IV for comparison.
    """
    df = options_data.copy()
    if expiry is not None:
        df = df[df["expirationDate"] == pd.Timestamp(expiry)]

    df = df[(df["bid"] > min_bid) & (df["ask"] >= df["bid"]) & (df["relSpread"] <= max_rel_spread)
            & (df["dte"] >= min_days)]
    forward = float(last) * np.exp((r - q) * df["T"])
    if otm_only:
        df = df[np.where(df["CALL"], df["strike"] >= forward, df["strike"] < forward)]
        forward = float(last) * np.exp((r - q) * df["T"])

    if df.empty:
        return pd.DataFrame(columns=SMILE_COLUMNS)

    res = run_engine(_engine_frame(df, last, r, q))
    out = pd.DataFrame({
        "expirationDate": df["expirationDate"], "dte": df["dte"], "T": df["T"], "strike": df["strike"],
        "optionType": np.where(df["CALL"], "call", "put"), "mid": df["mid"],
        "moneyness": np.log(df["strike"] / forward), "iv": res["iv"], "iv_status": res["iv_status"],
        "yahooIV": pd.to_numeric(df["impliedVolatility"], errors="coerce") if "impliedVolatility" in df else np.nan,
    })
    if not keep_failed:
        out = out[out["iv_status"] == "ok"]
    return out.sort_values(["expirationDate", "strike"]).reset_index(drop=True)[SMILE_COLUMNS]
