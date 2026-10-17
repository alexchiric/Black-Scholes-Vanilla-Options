"""Python-level tests: engine vs an independent closed form, pipelines, symbols and time handling.

Run with:  make test-py   (or: python3 -m unittest discover -s tests -v)
"""
import math
import os
import random
import sys
import unittest
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline import valuation_pipeline, vol_smile_pipeline          # noqa: E402
from option_data import (clean_option_chain, make_occ_symbol, parse_occ_symbol, synthetic_chain,   # noqa: E402
                         year_fraction)
from pricing_engine import (EngineError, implied_vol, normalise_option_type, price_and_greeks,      # noqa: E402
                            run_engine)

_N = NormalDist()


def reference(S, K, T, r, sigma, is_call, q=0.0):
    """Independent closed-form Black-Scholes-Merton: price, delta, gamma, vega, theta, rho."""
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    pdf = _N.pdf(d1)
    decay = -S * dq * pdf * sigma / (2 * math.sqrt(T))
    if is_call:
        return (S * dq * _N.cdf(d1) - K * dr * _N.cdf(d2), dq * _N.cdf(d1), dq * pdf / (S * sq),
                S * dq * pdf * math.sqrt(T), decay - r * K * dr * _N.cdf(d2) + q * S * dq * _N.cdf(d1),
                K * T * dr * _N.cdf(d2))
    return (K * dr * _N.cdf(-d2) - S * dq * _N.cdf(-d1), -dq * _N.cdf(-d1), dq * pdf / (S * sq),
            S * dq * pdf * math.sqrt(T), decay + r * K * dr * _N.cdf(-d2) - q * S * dq * _N.cdf(-d1),
            -K * T * dr * _N.cdf(-d2))


class EngineVsReference(unittest.TestCase):
    def test_random_grid_matches_closed_form(self):
        rng = random.Random(7)
        rows, refs = [], []
        for _ in range(500):
            S, K = rng.uniform(20, 400), None
            K = S * math.exp(rng.uniform(-0.5, 0.5))
            T, sigma = rng.uniform(0.01, 3), rng.uniform(0.05, 1.2)
            r, q, call = rng.uniform(0, 0.08), rng.uniform(0, 0.04), rng.random() < 0.5
            rows.append({"type": call, "S": S, "K": K, "T": T, "r": r, "q": q, "sigma": sigma})
            refs.append(reference(S, K, T, r, sigma, call, q))
        out = run_engine(pd.DataFrame(rows))
        self.assertTrue((out["row_status"] == "ok").all())
        got = out[["price_model", "delta", "gamma", "vega", "theta", "rho"]].to_numpy()
        np.testing.assert_allclose(got, np.array(refs), rtol=1e-9, atol=1e-10)

    def test_put_is_not_priced_as_call(self):          # regression: original code priced every put as a call
        call = price_and_greeks(100, 100, 1.0, 0.05, 0.2, "call")["price_model"]
        put = price_and_greeks(100, 100, 1.0, 0.05, 0.2, "put")["price_model"]
        self.assertAlmostEqual(call, 10.4505835722, places=7)
        self.assertAlmostEqual(put, 5.5735260223, places=7)

    def test_short_expiry_regression(self):            # regression: original d1 grouping error
        out = price_and_greeks(230.76, 230, 0.007937, 0.05, 0.30, "call")
        self.assertAlmostEqual(out["price_model"], 2.904938818, places=6)

    def test_implied_vol_round_trip(self):
        for is_call in (True, False):
            for sigma in (0.08, 0.25, 0.9, 3.0):
                price = reference(100, 95, 0.5, 0.03, sigma, is_call, 0.01)[0]
                iv, status = implied_vol(100, 95, 0.5, 0.03, price, is_call, q=0.01)
                self.assertEqual(status, "ok")
                self.assertAlmostEqual(iv, sigma, places=6)

    def test_implied_vol_failure_reasons(self):
        self.assertEqual(implied_vol(100, 50, 1.0, 0.0, 40.0, "call")[1], "below_intrinsic")
        self.assertEqual(implied_vol(100, 50, 1.0, 0.0, 100.5, "call")[1], "above_upper_bound")
        self.assertEqual(implied_vol(100, 150, 1.0, 0.0, 0.0, "call")[1], "no_time_value")
        self.assertTrue(math.isnan(implied_vol(100, 50, 1.0, 0.0, 40.0, "call")[0]))


class EngineRobustness(unittest.TestCase):
    def test_bad_rows_do_not_abort_the_batch(self):
        df = pd.DataFrame([
            {"type": "call", "S": 100, "K": 100, "T": 1.0, "r": 0.05, "sigma": 0.2},
            {"type": "call", "S": 100, "K": 100, "T": 0.0, "r": 0.05, "sigma": 0.2},     # expired
            {"type": "put", "S": np.nan, "K": 100, "T": 1.0, "r": 0.05, "sigma": 0.2},   # missing spot
            {"type": "put", "S": 100, "K": 100, "T": 1.0, "r": 0.05, "sigma": 0.2},
        ])
        out = run_engine(df)
        self.assertEqual(list(out["row_status"]), ["ok", "bad_input", "bad_input", "ok"])
        self.assertTrue(out.loc[[1, 2], "price_model"].isna().all())

    def test_index_preserved_and_empty_input(self):
        df = pd.DataFrame({"type": ["call"], "S": [100], "K": [100], "T": [1.0], "r": [0.05], "sigma": [0.2]}, index=[42])
        self.assertEqual(list(run_engine(df).index), [42])
        self.assertEqual(len(run_engine(df.iloc[0:0])), 0)

    def test_missing_required_column(self):
        with self.assertRaises(ValueError):
            run_engine(pd.DataFrame({"type": ["call"], "S": [100]}))

    def test_option_type_normalisation(self):
        for v in (True, "call", "Call", "C", 1, "1"):
            self.assertEqual(normalise_option_type(v), "call")
        for v in (False, "put", "PUT", "p", 0, "0"):
            self.assertEqual(normalise_option_type(v), "put")
        with self.assertRaises(ValueError):
            normalise_option_type("straddle")

    def test_missing_engine_override(self):
        old = os.environ.get("BS_ENGINE")
        os.environ["BS_ENGINE"] = "/nonexistent/bs_engine"
        try:
            with self.assertRaises(EngineError):
                run_engine(pd.DataFrame({"type": ["call"], "S": [1], "K": [1], "T": [1], "r": [0]}))
        finally:
            if old is None:
                del os.environ["BS_ENGINE"]
            else:
                os.environ["BS_ENGINE"] = old


class SymbolsAndTime(unittest.TestCase):
    def test_parse_occ_symbol(self):
        p = parse_occ_symbol("AAPL241115C00230000")
        self.assertEqual((p["root"], p["expiry"], p["is_call"], p["strike"]), ("AAPL", date(2024, 11, 15), True, 230.0))
        p = parse_occ_symbol("GOOGL250117P01742500")
        self.assertEqual((p["root"], p["expiry"], p["is_call"], p["strike"]), ("GOOGL", date(2025, 1, 17), False, 1742.5))
        for bad in ("AAPL", "AAPL241315C00230000", "", "AAPL241115X00230000"):
            with self.assertRaises(ValueError):
                parse_occ_symbol(bad)

    def test_occ_round_trip(self):
        sym = make_occ_symbol("MSFT", date(2026, 3, 20), False, 412.5)
        self.assertEqual(sym, "MSFT260320P00412500")
        self.assertEqual(parse_occ_symbol(sym)["strike"], 412.5)

    def test_year_fraction_uses_new_york_close_and_act365(self):
        # Nov: EST (UTC-5) -> expiry 16:00 NY = 21:00 UTC.  Exactly 1 day before -> 1/365
        self.assertAlmostEqual(year_fraction(date(2024, 11, 15), "2024-11-14T21:00:00Z"), 1 / 365, places=12)
        # Jul: EDT (UTC-4) -> expiry 16:00 NY = 20:00 UTC
        self.assertAlmostEqual(year_fraction(date(2024, 7, 19), "2024-07-18T20:00:00Z"), 1 / 365, places=12)
        # after the close on expiry day the fraction is negative (option expired)
        self.assertLess(year_fraction(date(2024, 11, 15), "2024-11-15T22:00:00Z"), 0)

    def test_clean_option_chain_drops_expired_and_bad_symbols(self):
        raw = pd.DataFrame({
            "contractSymbol": ["AAPL241115C00230000", "AAPL241115P00230000", "AAPL240101C00100000", "garbage"],
            "strike": [230, 230, 100, 1], "bid": [2.0, 1.0, 5.0, 1.0], "ask": [2.2, 1.2, 5.5, 1.1],
            "impliedVolatility": [0.3, 0.3, 0.3, 0.3], "lastPrice": [2, 1, 5, 1], "contractSize": ["REGULAR"] * 4})
        out = clean_option_chain(raw, now="2024-11-13T15:00:00Z")
        self.assertEqual(list(out["contractSymbol"]), ["AAPL241115C00230000", "AAPL241115P00230000"])
        self.assertEqual(list(out["CALL"]), [True, False])
        self.assertNotIn("lastPrice", out.columns)
        self.assertAlmostEqual(out.loc[0, "mid"], 2.1)
        self.assertTrue((out["T"] > 0).all())


class Pipelines(unittest.TestCase):
    NOW = "2026-10-16T15:00:00Z"

    @classmethod
    def setUpClass(cls):
        cls.S, cls.r, cls.q = 100.0, 0.045, 0.01
        cls.chain = synthetic_chain(S=cls.S, r=cls.r, q=cls.q, now=cls.NOW)

    def test_smile_recovers_the_true_volatility(self):
        smile = vol_smile_pipeline(self.chain, self.S, self.r, self.q)
        # One OTM option per (strike, expiry); deep-OTM quotes worth only a cent or two have a relative
        # spread above 50% and must be removed by the liquidity filter - nothing else may be removed.
        fwd = self.S * np.exp((self.r - self.q) * self.chain["T"])
        otm = np.where(self.chain["CALL"], self.chain["strike"] >= fwd, self.chain["strike"] < fwd)
        expected = int((otm & (self.chain["relSpread"] <= 0.5)).sum())
        self.assertGreater(expected, 50)
        self.assertEqual(len(smile), expected)
        self.assertTrue((smile["iv_status"] == "ok").all())
        np.testing.assert_allclose(smile["iv"], smile["yahooIV"], atol=1e-6)      # synthetic IV column = truth
        self.assertEqual(smile["expirationDate"].nunique(), 4)

    def test_otm_convention_uses_puts_below_and_calls_above_the_forward(self):
        smile = vol_smile_pipeline(self.chain, self.S, self.r, self.q)
        fwd = self.S * np.exp((self.r - self.q) * smile["T"])
        self.assertTrue(((smile["optionType"] == "call") == (smile["strike"] >= fwd)).all())
        self.assertTrue(((smile["moneyness"] >= 0) == (smile["optionType"] == "call")).all())

    def test_smile_shows_the_skew_that_was_put_in(self):
        # longest expiry: the wings still have liquid quotes (short-dated deep-OTM options are worth ~0)
        one = vol_smile_pipeline(self.chain, self.S, self.r, self.q, expiry=self.chain["expirationDate"].max())
        low, high = one[one["strike"] <= 80]["iv"].mean(), one[one["strike"] >= 120]["iv"].mean()
        self.assertGreater(low, high)                      # negative skew: downside vols above upside vols

    def test_liquidity_filter_removes_wide_markets(self):
        wide = self.chain.copy()
        wide.loc[wide.index[::2], "ask"] = wide.loc[wide.index[::2], "bid"] * 5      # blow out half the spreads
        wide["mid"] = (wide["bid"] + wide["ask"]) / 2
        wide["relSpread"] = (wide["ask"] - wide["bid"]) / wide["mid"]
        self.assertLess(len(vol_smile_pipeline(wide, self.S, self.r, self.q)),
                        len(vol_smile_pipeline(self.chain, self.S, self.r, self.q)))

    def test_empty_selection_returns_empty_frame_with_columns(self):
        out = vol_smile_pipeline(self.chain, self.S, self.r, self.q, expiry="1999-01-01")
        self.assertEqual(len(out), 0)
        self.assertIn("iv", out.columns)

    def test_valuation_pipeline_matches_closed_form_at_the_recovered_vol(self):
        row = self.chain[(self.chain["CALL"]) & (self.chain["strike"] == 100.0)].iloc[0]
        val = valuation_pipeline(self.chain, row["contractSymbol"], self.S, self.r, self.q)
        self.assertEqual(val.loc[0, "IV_status"], "ok")
        ref = reference(self.S, 100.0, row["T"], self.r, row["impliedVolatility"], True, self.q)
        self.assertAlmostEqual(val.loc[0, "Price"], ref[0], places=6)
        self.assertAlmostEqual(val.loc[0, "Delta"], ref[1], places=6)
        self.assertAlmostEqual(val.loc[0, "Vega"], ref[3], places=4)

    def test_valuation_pipeline_unknown_contract_and_source(self):
        with self.assertRaises(ValueError):
            valuation_pipeline(self.chain, "NOPE", self.S)
        with self.assertRaises(ValueError):
            valuation_pipeline(self.chain, self.chain["contractSymbol"].iloc[0], self.S, vol_source="bogus")


if __name__ == "__main__":
    unittest.main()
