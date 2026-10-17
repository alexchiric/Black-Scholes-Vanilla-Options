"""Python interface to the C++ batch engine (``bs_engine``).

The pricing maths lives in C++ (cdf.h, eu_option.h, greeks.h, vol_surface.h).  This module
sends a whole table of options to the engine in ONE process call (CSV over stdin) and gets one
result row per input row back (CSV over stdout) - no temporary files, no per-call compilation.

The engine binary is built on demand with ``make`` the first time it is needed (and rebuilt when
a C++ source file is newer than the binary).  Set the environment variable ``BS_ENGINE`` to use a
pre-built binary at a specific path instead.
"""
from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_ENGINE = ROOT / "build" / "bs_engine"
_ENGINE_SOURCES = ["bs_engine.cpp", "cdf.h", "eu_option.h", "greeks.h", "vol_surface.h"]

INPUT_COLUMNS = ["type", "S", "K", "T", "r", "q", "sigma", "price"]
OUTPUT_COLUMNS = ["row_status", "iv", "iv_status", "sigma_used", "price_model",
                  "delta", "gamma", "vega", "theta", "rho", "iterations"]
_REQUIRED = ("type", "S", "K", "T", "r")


class EngineError(RuntimeError):
    """The C++ engine could not be built or run."""


def _is_stale(binary: Path) -> bool:
    if not binary.exists():
        return True
    built = binary.stat().st_mtime
    return any((ROOT / s).exists() and (ROOT / s).stat().st_mtime > built for s in _ENGINE_SOURCES)


def ensure_engine() -> Path:
    """Return the path of an up-to-date engine binary, building it if necessary."""
    override = os.environ.get("BS_ENGINE")
    if override:
        path = Path(override)
        if not path.exists():
            raise EngineError(f"BS_ENGINE points to a file that does not exist: {path}")
        return path

    if _is_stale(DEFAULT_ENGINE):
        try:
            proc = subprocess.run(["make", "-C", str(ROOT), "build/bs_engine"],
                                  capture_output=True, text=True, timeout=300)
        except FileNotFoundError as exc:
            raise EngineError(
                "`make` was not found, so the C++ engine could not be built. On macOS run "
                "`xcode-select --install`, or build it by hand:\n"
                "  c++ -std=c++17 -O2 -o build/bs_engine bs_engine.cpp") from exc
        if proc.returncode != 0:
            raise EngineError("Building the C++ engine failed:\n" + proc.stderr)
    return DEFAULT_ENGINE


def normalise_option_type(value) -> str:
    """Map bool / 1 / 0 / 'C' / 'Put' / ... to the strings the engine expects."""
    if isinstance(value, (bool, np.bool_)):
        return "call" if value else "put"
    s = str(value).strip().lower()
    if s in {"call", "c", "1", "1.0", "true"}:
        return "call"
    if s in {"put", "p", "0", "0.0", "false"}:
        return "put"
    raise ValueError(f"Unknown option type: {value!r} (use 'call' or 'put')")


def run_engine(df: pd.DataFrame, timeout: float = 120.0) -> pd.DataFrame:
    """Price / compute Greeks / solve implied vol for every row of ``df``.

    Required columns: ``type`` (call/put or bool, True = call), ``S`` spot, ``K`` strike,
    ``T`` years to expiry, ``r`` risk-free rate.
    Optional columns: ``q`` dividend yield (default 0), ``sigma`` (-> price and Greeks at that vol),
    ``price`` (market price -> implied vol; if ``sigma`` is empty the Greeks use the implied vol).

    Returns a DataFrame with the same index and the columns in ``OUTPUT_COLUMNS``.  Rows that
    cannot be processed come back with ``row_status == 'bad_input'`` and NaNs; they never abort
    the batch.  Greeks are in raw analytic units (see greeks.h); use ``add_display_greeks`` for
    per-day / per-1% scaling.
    """
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"run_engine: missing required column(s): {missing}")
    if len(df) == 0:
        return pd.DataFrame(columns=OUTPUT_COLUMNS, index=df.index)

    work = pd.DataFrame(index=df.index)
    work["type"] = df["type"].map(normalise_option_type)
    for col in ("S", "K", "T", "r"):
        work[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("q", "sigma", "price"):
        work[col] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else np.nan

    csv_in = work[INPUT_COLUMNS].to_csv(index=False, float_format="%.17g", na_rep="nan")
    binary = ensure_engine()
    try:
        proc = subprocess.run([str(binary)], input=csv_in, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"The engine did not finish within {timeout} s") from exc
    if proc.returncode != 0:
        raise EngineError(proc.stderr.strip() or f"engine exited with status {proc.returncode}")

    out = pd.read_csv(io.StringIO(proc.stdout))
    if len(out) != len(work):
        raise EngineError(f"Engine returned {len(out)} rows for {len(work)} input rows")
    out.index = df.index
    return out


def add_display_greeks(result: pd.DataFrame) -> pd.DataFrame:
    """Add conventional trader units: vega per 1 vol point, theta per calendar day, rho per 1%."""
    out = result.copy()
    out["vega_1pct"] = out["vega"] / 100.0
    out["theta_day"] = out["theta"] / 365.0
    out["rho_1pct"] = out["rho"] / 100.0
    return out


def price_and_greeks(S, K, T, r, sigma, option_type, q: float = 0.0) -> dict:
    """Single-option convenience wrapper: price and Greeks at a given volatility."""
    res = run_engine(pd.DataFrame([{"type": option_type, "S": S, "K": K, "T": T, "r": r, "q": q, "sigma": sigma}]))
    row = res.iloc[0]
    if row["row_status"] != "ok":
        raise ValueError("Invalid inputs: S, K, T and sigma must be positive numbers")
    return {k: float(row[k]) for k in ("price_model", "delta", "gamma", "vega", "theta", "rho")}


def implied_vol(S, K, T, r, price, option_type, q: float = 0.0):
    """Single-option implied volatility. Returns ``(iv, status)``; ``iv`` is NaN unless status == 'ok'."""
    res = run_engine(pd.DataFrame([{"type": option_type, "S": S, "K": K, "T": T, "r": r, "q": q, "price": price}]))
    row = res.iloc[0]
    return float(row["iv"]), str(row["iv_status"])
