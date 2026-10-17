© 2024 Alexandru Chiric & Horia Zamfir. All rights reserved.

# Black-Scholes-Vanilla-Options

A C++ pricer for vanilla European options - price, Greeks and implied volatility under Black-Scholes(-Merton) -
with a Python/Shiny front end that loads real option chains, shows the implied-volatility smile and surface, and
values individual contracts.

* **C++ core** (`cdf.h`, `eu_option.h`, `greeks.h`, `vol_surface.h`): exact normal CDF, closed-form Greeks, a
  bracketed Newton implied-volatility solver that cannot diverge, optional continuous dividend yield.
* **Batch engine** (`bs_engine.cpp`): reads a CSV of options on stdin, writes results on stdout - one process call for a
  whole option chain.
* **Python layer** (`pricing_engine.py`, `option_data.py`, `data_pipeline.py`, `vol_surface_plot.py`) and a
  **Shiny app** (`app_main.py`) with four views: Option Table, Option Calculator, Vol Smile, Vol Surface.
* **Tests**: ~19,000 C++ checks and 21 Python tests, plus `docs/METHODOLOGY_LOG.md`, a step-by-step record of the
  methodology (formulas, assumptions, verification).

# 1. Install

You need Python 3.9+ and a C++17 compiler (on macOS: `xcode-select --install`).

```bash
# macOS, if you do not have Python yet
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python

cd path/to/Black-Scholes-Vanilla-Options
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

# 2. Build and test

```bash
make            # builds build/bs_engine (the Python layer also builds it automatically when needed)
make test       # C++ core tests + Python tests
make demo       # small command-line example (src: main.cpp)
```

# 3. Run the app

```bash
python -m shiny run app_main.py --port 8000
```

Open http://localhost:8000, pick a data source (**Synthetic demo** works offline; **Yahoo Finance** needs internet),
click *Load option chain*, then switch between the views.

# 4. Use it from Python

```python
from pricing_engine import price_and_greeks, implied_vol

price_and_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="put")
# {'price_model': 5.5735, 'delta': -0.3632, 'gamma': 0.01876, 'vega': 37.52, 'theta': -1.658, 'rho': -41.89}

implied_vol(S=230.76, K=230, T=2/365, r=0.05, price=2.20, option_type="call")
# (0.2584, 'ok')
```

For many options at once use `pricing_engine.run_engine(df)` (one engine call per DataFrame) and
`data_pipeline.vol_smile_pipeline(chain, spot, r, q)` for a full smile/surface.

# 5. Conventions

| Quantity | Convention |
|---|---|
| `T` | years, ACT/365, measured to 16:00 New York time on the expiry date (taken from the OCC contract symbol) |
| `r`, `q` | continuously compounded risk-free rate and dividend yield (defaults: 5% and 0) |
| Market price | bid/ask mid |
| Engine Greeks (raw) | delta per 1.00 of spot; vega per 1.00 of vol; theta per **year** as `-dV/dT`; rho per 1.00 of rate |
| UI / `add_display_greeks` | vega per 1 vol point, theta per calendar day, rho per 1% |
| Smile / surface | out-of-the-money options only (puts below the forward, calls at or above), liquidity filter on bid-ask spread |

Implied-vol failures are explicit, never silent numbers: `below_intrinsic`, `above_upper_bound`, `no_time_value`,
`vol_too_high`, `bad_input`, `no_convergence`.

## Engine CSV protocol

```
type,S,K,T,r,q,sigma,price          <- header, any column order; required: type,S,K,T,r
call,230.76,230,0.005479,0.05,0,,2.20
```

Output columns: `row_status, iv, iv_status, sigma_used, price_model, delta, gamma, vega, theta, rho, iterations`
(one row per input row, `nan` for missing values). If `sigma` is empty and `price` is given, price and Greeks are
evaluated at the implied vol. Full reference: header comment of `bs_engine.cpp`.

# 6. Known limitations

* Listed US equity options are **American-style**; Black-Scholes prices **European** options. The model price is a
  lower bound for puts and for calls on dividend payers (the OTM-only smile convention reduces, not removes, this).
* Dividends are a continuous yield `q` that you enter - no discrete-dividend schedule, and no automatic yield lookup.
* The risk-free rate is one flat number (sidebar), not a curve.
* The live Yahoo Finance path depends on yfinance and Yahoo's data quality (stale or crossed quotes are filtered by the
  spread filter and reported through `iv_status`).

# 7. Project layout

| Path | Purpose |
|---|---|
| `cdf.h`, `eu_option.h`, `greeks.h`, `vol_surface.h` | pricing core (header-only) |
| `bs_engine.cpp`, `Makefile` | batch engine and build |
| `main.cpp` | command-line demo |
| `pricing_engine.py`, `option_data.py`, `data_pipeline.py`, `vol_surface_plot.py` | Python layer |
| `app_main.py` | Shiny app |
| `tests/` | `test_core.cpp` (C++), `test_engine.py` (Python) |
| `docs/METHODOLOGY_LOG.md` | methodology record |
| `legacy/` | superseded code, safe to delete |
