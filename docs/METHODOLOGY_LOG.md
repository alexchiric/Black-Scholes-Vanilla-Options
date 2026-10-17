# Methodology Log

Chronological record of every methodological decision made while finishing the
Black-Scholes Vanilla Options pricer. Each entry states **what** was done, **why**,
the **formula / assumption** involved, and **how it was verified**.

Conventions used throughout (see Step 1 for the reasoning):

| Symbol | Meaning |
|---|---|
| S | spot price of the underlying |
| K | strike |
| T | time to expiry in years (ACT/365, measured to the 16:00 New York close of the expiry date) |
| r | continuously-compounded risk-free rate |
| q | continuous dividend yield (default 0) |
| sigma | annualised volatility (0.20 = 20%) |

---

## Step 0 - Audit of the existing code (2026-10-17)

**What:** compiled every C++ entry point and compared the pricing core against an
independent closed-form implementation (Python, `statistics.NormalDist`), using a scratch
copy so the repository was not modified.

**Findings (all reproduced numerically):**

| # | Finding | Evidence |
|---|---|---|
| 1 | Nothing compiled: `vol_smile()` in `vol_surface.h` was an empty `return`. | `g++` error "expected primary-expression before '}'" in all three entry points |
| 2 | Puts were priced as calls: `option_type == "call" \|\| "Call"` is always true (a string literal is a non-null pointer). | S=K=100, r=5%, T=1, sigma=20%: put returned 10.4506, true value 5.5735 |
| 3 | d1 was mis-parenthesised: `(r + 0.5*sigma^2*t)` instead of `(r + 0.5*sigma^2)*t`. Invisible at T=1, which is why it went unnoticed. | T=0.25: call 4.356 vs 4.615 (-5.6%); 2-day AAPL example from `main.cpp`: 1.168 vs 2.905 |
| 4 | Implied vol: Newton on a `float`, price tolerance 1e-3, no iteration cap, no bounds. | Code inspection: infinite loop / divergence possible when vega ~ 0 |
| 5 | Greeks via forward finite differences; gamma divides by 1e-8. | Code inspection |
| 6 | Normal CDF via a 1964 polynomial (~1e-7 abs. error). | Code inspection |
| 7 | Python<->C++ link through a shared `temp.bin` in the cwd, recompiling on every call, reading inputs by column position, r hard-coded to 5%. | Code inspection |
| 8 | `dte` = calendar days / 252 (inconsistent day-count); a network call at import time in `data_pipeline.py`; empty `vol_smile_workflow.cpp`, `vol_surface_plot.py`. | Code inspection |
| 9 | UI: placeholder views; `temp_view_type != ...` compares the reactive object itself (always true); leftover debug `return`. | Code inspection |

**Decision:** keep the C++ core as the single source of truth and replace the `temp.bin`
hand-off with a batch CLI engine (CSV over stdin/stdout). Alternatives considered:
patch-in-place (keeps the race and recompile), pybind11 (cleanest, but build dependency
could not be verified on the target Mac), Python-first (drops the C++ identity).

---

## Step 1 - Pricing core: correctness fixes, exact CDF, closed-form Greeks (2026-10-17)

**Files:** `cdf.h`, `eu_option.h`, `greeks.h`, `tests/test_core.cpp`

**What and why**

1. **Model.** Black-Scholes-Merton for European options with a continuous dividend yield `q`
   (`q = 0` is plain Black-Scholes, so the original behaviour is the default):
   `d1 = [ln(S/K) + (r - q + sigma^2/2) T] / (sigma sqrt(T))`, `d2 = d1 - sigma sqrt(T)`;
   `Call = S e^{-qT} N(d1) - K e^{-rT} N(d2)`, `Put = K e^{-rT} N(-d2) - S e^{-qT} N(-d1)`.
2. **Bug 2 fix (puts priced as calls).** The `string == "call" || "Call"` test was replaced by an
   `enum class OptionType { Call, Put }` plus a case-insensitive `parse_option_type()`. A typo can no
   longer silently fall through to the call branch - invalid input throws.
3. **Bug 3 fix (d1).** `(r - q + sigma^2/2) * T` is now correctly grouped.
4. **Exact normal CDF.** `N(x) = 0.5 * erfc(-x / sqrt(2))` replaces the 1964 polynomial
   (abs. error ~7.5e-8 -> machine precision). `phi(x)` is added for the Greeks.
5. **Closed-form Greeks** replace forward finite differences (noisy; gamma divided by 1e-8).
   Raw analytic units are documented in `greeks.h`: delta per 1.00 of spot, gamma, vega per 1.00 of
   vol, theta per year as `-dV/dT`, rho per 1.00 of rate. `bs_all()` returns price and all Greeks from
   one evaluation of d1/d2.
6. **Input validation.** `S, K, T, sigma` must be positive and finite, otherwise
   `std::invalid_argument` (the original produced NaN/inf silently).
7. **Header hygiene.** Functions are `inline` so headers can be included from several translation units.

**Verification (`make test-core`)**

| Check | Result |
|---|---|
| Textbook values (Hull: 42/40, r=10%, sigma=20%, T=0.5 -> 4.76 / 0.81; ATM 1y -> 10.4506 / 5.5735) | pass |
| Regression pins for bugs 2 and 3 (T=0.25 and the 2-day AAPL-like case), values from an independent Python closed form | pass |
| Put-call parity `C - P = S e^{-qT} - K e^{-rT}` on 2,000 random parameter sets | pass (1e-9) |
| Dividend identity `BSM(S, q) = BS(S e^{-qT}, q=0)` | pass |
| No-arbitrage bounds and monotonicity of price in sigma | pass |
| Analytic delta/gamma/vega/theta/rho vs central finite differences on a 216-point grid (call and put x spot x expiry x vol x rate x yield) | pass |
| Input validation / option-type parsing | pass |

A first run flagged 43 delta/gamma mismatches. Cause: the test's finite-difference step (1e-3 * S)
had a truncation error larger than the tolerance for sharp short-dated cases. This was a test
artefact (the analytic values already matched the independent reference to 1e-9); the step was
reduced to 1e-4 * S and the grid then passed.

---

## Step 2 - Robust implied-volatility solver (2026-10-17)

**File:** `vol_surface.h` (tests in `tests/test_core.cpp`)

**What and why**

1. **Method: safeguarded Newton.** The model price is strictly increasing in sigma (vega > 0), so
   `f(sigma) = BS(sigma) - market_price` has exactly one root in a bracket. Newton's method gives
   fast convergence; whenever a Newton step leaves the current bracket (or vega ~ 0) the solver
   bisects instead. The old code (Newton on a `float`, no bounds, no iteration cap) could diverge or
   loop forever on short-dated / deep ITM-OTM options, i.e. exactly the 2-day options in `main.cpp`.
2. **No-arbitrage pre-check.** `max(S e^{-qT} - K e^{-rT}, 0) <= C <= S e^{-qT}` (calls) and
   `max(K e^{-rT} - S e^{-qT}, 0) <= P <= K e^{-rT}` (puts). Outside the bounds there is no implied
   vol, so the solver returns an explicit `IVStatus` instead of a meaningless number:
   `ok, bad_input, below_intrinsic, above_upper_bound, no_time_value, vol_too_high, no_convergence`.
3. **Bracket** `[1e-6, 10]` (0.0001% to 1000%), double precision, price tolerance `1e-12 * max(1, S)`,
   iteration cap 100. The starting point (Brenner-Subrahmanyam ATM approximation) affects speed only.
4. **`vol_smile()` completed** (it was an empty `return`): implied vols of a strike/price vector for
   one expiry, one status per point.

**Verification**

| Check | Result |
|---|---|
| 5,000 random round trips price -> IV -> price (S, K, T, sigma, r, q, call/put) | 4,947 solved; every solved IV reprices to 1e-9*S and equals the true sigma to 1e-6 where vega > 0.01 |
| The 53 unsolved cases | all `no_time_value` (price equals intrinsic to numerical precision, sigma is not identifiable) - no other failure status occurred |
| Edge cases: below intrinsic, exactly intrinsic, zero price, above upper bound, t = 0, NaN, negative price, vol 1% and 500% | pass |
| Original `main.cpp` example (2-day call, market price 2.20) | solves, IV = 21.27%, reprices to 2.20 within 1e-9 |
| Vol-smile vector on a synthetic skewed smile | recovered to 1e-7 |

Final state of the C++ suite: **19,289 checks, 0 failures**; clean under `-Wall -Wextra -pedantic`.

---

## Step 3 - Batch engine `bs_engine` replaces the `temp.bin` hand-off (2026-10-17)

**Files:** `bs_engine.cpp`, `Makefile`, `main.cpp` (rewritten demo); old `calculation_workflow.cpp`,
`vol_smile_workflow.cpp` moved to `legacy/`.

**What and why**

1. **Interface.** CSV on stdin -> CSV on stdout, one output row per input row, in order. Python sends a
   whole option chain in a single process call, so a full vol smile is one call instead of one
   subprocess (and one `clang++` compile) per contract. No shared file means no race between two
   browser sessions.
2. **Columns are looked up by header name**, not position (the old code read `data[5]`, `data[0]`, ...
   and would silently price the wrong thing if yfinance reordered its columns). Required:
   `type, S, K, T, r`. Optional: `q`, `sigma` (-> price and Greeks), `price` (-> implied vol). When
   `sigma` is empty but `price` is given, price and Greeks are evaluated at the implied vol.
3. **Failure handling.** A bad row never aborts the batch: it yields `row_status=bad_input` and NaNs,
   and implied-vol failures carry the `iv_status` reason from Step 2. A malformed header exits with
   code 2 and a message on stderr.
4. **Build.** `make` builds `build/bs_engine` with `-std=c++17 -O2 -Wall -Wextra -pedantic`
   (`make test` runs the C++ and Python suites). The Python layer builds the engine on demand.

**Verification**

| Check | Result |
|---|---|
| Rows with: sigma only, price only, both empty, put in capitals, below-intrinsic price, T=0, unknown option type, non-numeric S, blank line | every case produced the intended `row_status` / `iv_status` (blank lines are skipped) |
| Reordered columns and CRLF line endings | parsed correctly, IV 0.2000000007 for the price of a 20%-vol option |
| Empty input / wrong header | exit code 2 with message |
| Throughput: 100,000 random rows | 0.24 s |
| Original `main.cpp` example (call, S=230.76, K=230, T=0.007937, market 2.20) through the engine | IV = 21.27%, price reproduced as 2.2 |

Correction recorded while verifying: the first draft of the Step 2 test comment guessed the IV of this
example at "about 16%". The engine gives 21.27% (the test only asserted a 10-30% range, so it
passed either way); the log and comment were corrected.

---

## Step 4 - Python layer: engine wrapper, data cleaning, pipelines, smile/surface plots (2026-10-17)

**Files:** `pricing_engine.py`, `option_data.py`, `data_pipeline.py`, `vol_surface_plot.py`,
`tests/test_engine.py`

**What and why**

1. **Engine wrapper (`pricing_engine.run_engine`).** One subprocess call per table, results aligned to
   the input index. The binary is built with `make` the first time it is needed and rebuilt when a C++
   source is newer; `BS_ENGINE=<path>` overrides this. A missing compiler yields an actionable error.
2. **Time to expiry.** `T = (expiry at 16:00 New York time - now) / 365 days` (ACT/365). The original
   used `calendar days / 252` - a calendar-day count divided by a trading-day year, which overstates T
   by 365/252 = 1.45x (about +45%) and therefore biases every implied vol low by roughly 1/sqrt(1.45),
   i.e. about 17%. (A 252-day year is only consistent when the numerator counts business days.) Here
   rates and vols are per calendar year, and 16:00 ET is when US equity options stop trading. The expiry date
   comes from the **OCC contract symbol** (`AAPL241115C00230000` -> AAPL, 2024-11-15, call, 230.000)
   instead of the "+1 day" hack on yfinance's date list, and the same parse replaces
   `"C" in contractSymbol[4:]` for call/put detection (which breaks for some roots).
3. **Dividend yield and rate are explicit parameters** (default `r = 5%`, `q = 0`, as in the original).
   `get_risk_free_rate()` can read the 13-week T-bill (^IRX) and falls back to 5%.
4. **Market price = bid/ask mid.** Implied vol is solved from the mid with the Step 2 solver; Yahoo's
   own `impliedVolatility` is kept next to it for comparison (`valuation_pipeline(vol_source=...)`
   can use either).
5. **Vol smile / surface method (`vol_smile_pipeline`).**
   a. Liquidity filter: `bid > 0`, `ask >= bid`, relative spread `(ask-bid)/mid <= 50%`, `>= 1` calendar day to expiry.
   b. **OTM convention:** puts for `K < F`, calls for `K >= F`, with forward `F = S e^{(r-q)T}`. OTM options are
      the liquid ones, and they are the least contaminated by the early-exercise premium of American-style listed options.
   c. Implied vol per option through the engine; failed solves are dropped (or kept with `keep_failed=True`).
   d. Log-moneyness `ln(K/F)` is reported next to the strike. Plots: lines per expiry (IV vs strike or
      moneyness) and a Delaunay-triangulated 3-D surface over (moneyness, days to expiry).
6. **Import has no side effects** (the original `data_pipeline.py` downloaded AAPL data at import).
7. **Offline testability.** `synthetic_chain()` builds a chain with the real schema from a known smile
   `sigma(K,T) = atm + slope*sqrt(T) + skew*ln(K/S) + curvature*ln(K/S)^2`, so the whole pipeline can be
   tested without network access. `yfinance` is imported lazily, only by the three live functions.

**Verification (`make test-py`, 21 tests)**

| Check | Result |
|---|---|
| Engine vs independent closed form (500 random options, call/put, with dividends): price and all five Greeks | match to rtol 1e-9 |
| Regression for bugs 2 and 3 through the Python path | pass |
| IV round trip for vols 8% - 300%, calls and puts; each failure status reproduced | pass |
| Bad rows (T = 0, missing spot) do not abort a batch; index preserved; empty input; missing column; unknown type | pass |
| OCC parsing (incl. 5-letter root, fractional strike, invalid month/suffix) and round trip | pass |
| Time convention: exactly 1/365 the day before the close in both EST and EDT; negative after the close | pass |
| Cleaning drops expired contracts and unparsable symbols | pass |
| Smile recovered from a synthetic chain: |IV - true vol| = 1.8e-11 on all 76 retained points; puts below / calls above the forward; negative skew visible | pass |
| Build-on-demand and stale-binary detection (run in a scratch copy) | pass |
| Plot functions: 4 expiry lines, 3-D mesh of 76 points, graceful message when there is nothing to draw | pass |

Two tests failed on the first run; both were **errors in the test expectations, not in the code**, found by
inspecting exactly which options had been dropped: (a) the test demanded more than 100 smile points although
at most 100 exist (one OTM option per strike per expiry) and 24 deep-OTM quotes worth under 2 cents are
rightly rejected by the 50% spread filter - the assertion now computes the exact expected count from the chain;
(b) the skew test used the 7-day expiry whose wings have no liquid quotes - it now uses the longest expiry.

**Known limitation recorded here (applies to the whole project):** listed US equity options are
American-style; Black-Scholes prices European options. For calls on non-dividend payers the two coincide;
for puts and dividend payers the early-exercise premium makes the model price a lower bound. The OTM
convention reduces but does not remove this effect. A binomial / Bjerksund-Stensland extension would be
the next step if exact American pricing matters.

---

## Step 5 - Shiny app: real Option Calculator, Vol Smile and Vol Surface views (2026-10-17)

**Files:** `app_main.py` (rewritten); `legacy/app.py` (the earlier, superseded app)

**What and why**

1. **State handling simplified.** The original view switching used two reactive values and an effect that
   compared `temp_view_type != "..."` - the reactive *object*, not its value, so the test was always true.
   Panels are now driven directly by `input.view_type` through `panel_conditional`; the dead state machine is gone.
2. **Data is loaded on demand** (button, not on every re-render - the original re-downloaded the whole chain
   whenever any input changed). Sources: Yahoo Finance (live) or the synthetic chain from Step 4.
3. **Option Table:** the chain plus our own implied vol from the mid, next to Yahoo's. Filters: call/put,
   minimum strike (the original `input_numeric(..., "None")` was a string default), IV range (the original
   returned the slider's own tuple as a debug leftover).
4. **Option Calculator:** (a) value a listed contract by OCC symbol using the loaded chain, with a choice of vol
   source (implied from mid / Yahoo IV) and a plain-language reason whenever the IV cannot be solved;
   (b) a manual calculator (spot, strike, days, vol, type, optional market price -> price, Greeks, implied vol).
5. **Vol Smile / Vol Surface:** the plots from Step 4, driven by one engine call per chain; controls for expiry,
   x-axis (strike or log-moneyness), Yahoo-IV overlay and the maximum bid-ask spread.
6. **Display units.** Greeks are shown as vega per 1 vol point, theta per calendar day, rho per 1% (the engine's
   raw units are divided by 100 / 365 / 100).
7. **Rate and dividend yield** are sidebar inputs (the original hard-coded 5%).

**Verification** (a real Shiny server was started and driven over its websocket protocol, emulating a browser's
action-button and output-visibility messages; 20 value checks against the independent closed form):

| Check | Result |
|---|---|
| Server starts, page served (HTTP 200); every view renders with 0 server-side errors, also before any data is loaded | pass |
| Manual calculator (put, S=K=100, 30 d, vol 25%, r 4.5%, q 1%, price 3.00): price, delta, gamma, vega, theta, rho | match to 5 decimals |
| Manual calculator implied vol (27.53573%) vs independent bisection | match |
| Contract valuation: price equals the chain mid, delta/vega match, IV from mid equals the vol used to generate the chain | pass |
| Unknown contract -> readable message (no exception); Yahoo-IV source uses the chain's column | pass |
| Table filters: puts only, strike >= 100, IV in [10, 60]% (48 rows, all satisfy every filter); no-filter table shows all 200 contracts; items-per-page truncates | pass |

Findings during testing: (a) `render.table` needs `jinja2 >= 3.1.2` (pandas Styler); the original
`requirements.txt` only got jinja2 indirectly through `jupyter` - it is now an explicit requirement.
(b) The first test-harness run sent plain integers for action buttons and no output-visibility flags, so the app
loaded data at start-up and rendered nothing; both were harness errors (a browser sends `load:shiny.action` and
`.clientdata_output_*_hidden`), fixed in the harness, not in the app.

**Not verified:** the live Yahoo Finance path (no market-data access from the build environment) and the visual
appearance in an actual browser (layout, plotly interaction, dark theme). See README "Known limitations".

---

## Step 6 - Documentation and dependency cleanup (2026-10-17)

**Files:** `README.md`, `requirements.txt`, `.gitignore`

1. **README rewritten** (the original copyright line is kept): install, build/test, run, Python usage, conventions
   (units, day-count, Greeks scaling), the engine CSV protocol, known limitations. The Python usage example was
   executed and its output pasted, not typed from memory.
2. **`requirements.txt` corrected.** Added `jinja2>=3.1.2` (needed by `render.table`; found in Step 5) and
   `shinyswatch` (imported by the app but missing from the old file). Removed nine packages that no file in the
   project imports (checked with a search of every `.py` file): `beautifulsoup4`, `html5lib`, `ipython`, `jupyter`,
   `notebook`, `faicons`, `palmerpenguins`, plus the duplicate `shinywidgets` line. Exact pins were relaxed to minimum
   versions. All project files parse with the Python 3.9 grammar, the version the old README asked for.
3. **`.gitignore`** now covers `build/`, `*.dSYM/`, `temp.bin`, `.DS_Store`, `.venv/`.

---

## Final validation (2026-10-17)

| Suite | Result |
|---|---|
| `make test`, run from the repository (build output outside the repo) | C++: **19,289 checks, 0 failures**; Python: **21 tests, OK** |
| Clean-room run from a fresh copy with no overrides (builds `build/bs_engine`, then tests) | identical results |
| Compiler flags `-std=c++17 -O2 -Wall -Wextra -pedantic` | no warnings |
| Live Shiny session (websocket-driven), 20 value checks against an independent closed form | 20 / 20, 0 server-side errors |
| All three original bugs | fixed and pinned by regression tests in both languages |

**Not verified (no way to do so from the build environment):** the live Yahoo Finance path, and the browser rendering of
the app (layout, plotly interaction, dark theme). The C++ was compiled with `g++` on Linux; the Mac build uses `clang++`
through the same Makefile and the same standard flags.

**Housekeeping left for the repository owner (not done automatically; no git commands that write were run):**

* These files are tracked by git but are stale build artefacts - untrack them with
  `git rm -r --cached main calculation_workflow temp.bin .DS_Store output __pycache__`
  (they are now covered by `.gitignore`; delete the files from disk too if wanted).
* `legacy/` holds superseded code that is also in git history; `git rm -r legacy` when no longer needed.
* Never commit a `build/` folder made on another OS: the Python layer rebuilds the engine only when it is *older* than the
  sources, so a foreign-OS binary would not be detected as stale.

Ideas for later (not done): American-exercise pricing (binomial or Bjerksund-Stensland), discrete dividends, a rate curve,
SVI/SABR smile fitting, a pybind11 binding if in-process calls ever matter.
