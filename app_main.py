"""Black Scholes Vanilla Options - Shiny Express app.

Run:   python -m shiny run app_main.py --port 8000
Views: Option Table | Option Calculator | Vol Smile | Vol Surface
Data:  Yahoo Finance (live, needs `pip install yfinance` and internet) or a built-in synthetic chain.

All pricing, Greeks and implied volatilities come from the C++ engine (see pricing_engine.py).
"""
import numpy as np
import pandas as pd
from shiny import reactive
from shiny.express import input, render, ui
from shinyswatch import theme
from shinywidgets import render_plotly

from data_pipeline import valuation_pipeline, vol_smile_pipeline
from option_data import get_last_price, get_option_chain, synthetic_chain
from pricing_engine import add_display_greeks, run_engine
from vol_surface_plot import empty_figure, smile_figure, surface_figure

VIEWS = ["Option Table", "Option Calculator", "Vol Smile", "Vol Surface"]
ALL_EXPIRIES = "All expiries"
IV_STATUS_HELP = {
    "ok": "",
    "no_price": "No market price available, so no implied volatility.",
    "below_intrinsic": "The quoted price is below intrinsic value (no-arbitrage violation) - stale or crossed quote.",
    "above_upper_bound": "The quoted price is above the no-arbitrage upper bound - bad quote.",
    "no_time_value": "The price equals intrinsic value, so the volatility cannot be identified (deep in the money / worthless).",
    "vol_too_high": "The implied volatility would exceed 1000%.",
    "no_convergence": "The solver did not converge.",
    "bad_input": "Invalid inputs (check spot, strike, expiry).",
}

ui.page_opts(title="Black Scholes Vanilla Options", theme=theme.darkly, fillable=True)

# ------------------------------------------------------------------------------------ state
chain = reactive.value(None)      # cleaned option chain (DataFrame) or None
spot = reactive.value(None)       # underlying price
status = reactive.value("Choose a data source and click 'Load option chain'.")


def risk_free() -> float:
    value = input.rate()
    return (0.0 if value is None else float(value)) / 100.0


def div_yield() -> float:
    value = input.div_yield()
    return (0.0 if value is None else float(value)) / 100.0


def message(text: str) -> pd.DataFrame:
    return pd.DataFrame({"Message": [text]})


# ---------------------------------------------------------------------------------- sidebar
with ui.sidebar(width=330):
    ui.input_selectize("view_type", "Select view type", VIEWS)
    ui.input_select("data_source", "Data source", ["Yahoo Finance (live)", "Synthetic demo"])
    ui.input_text("symbols", "Stock Symbol", "AAPL")
    ui.input_action_button("load", "Load option chain", class_="btn-primary")
    ui.input_numeric("rate", "Risk-free rate (%)", 5.0, min=-5, max=50, step=0.05)
    ui.input_numeric("div_yield", "Dividend yield (%)", 0.0, min=0, max=50, step=0.05)

    @render.text
    def status_text():
        return status.get()

    with ui.panel_conditional("input.view_type === 'Option Table'"):
        ui.input_selectize("items_per_page", "Items per Page", ["100", "200", "300"])
        ui.input_select("call_option", "Call / Put", ["All", "Call", "Put"])
        ui.input_numeric("strike_price", "Minimum strike (0 = no filter)", 0, min=0)
        ui.input_slider("iv_range", "Implied volatility (%)", min=0, max=300, value=[0, 300])

    with ui.panel_conditional("input.view_type === 'Vol Smile' || input.view_type === 'Vol Surface'"):
        ui.input_slider("max_spread", "Max bid-ask spread (% of mid)", min=5, max=200, value=50)

    with ui.panel_conditional("input.view_type === 'Vol Smile'"):
        ui.input_select("smile_expiry", "Expiry", [ALL_EXPIRIES])
        ui.input_select("smile_x", "X axis", {"strike": "Strike", "moneyness": "Log-moneyness ln(K/F)"})
        ui.input_checkbox("show_yahoo", "Overlay Yahoo Finance IV", False)


# ---------------------------------------------------------------------------- loading data
@reactive.effect
@reactive.event(input.load)
def _load_chain():
    try:
        if input.data_source() == "Synthetic demo":
            last = 100.0
            df = synthetic_chain(S=last, r=risk_free(), q=div_yield())
            label = "synthetic demo chain"
        else:
            symbol = (input.symbols() or "").strip().upper()
            if not symbol:
                raise ValueError("Enter a stock symbol")
            df = get_option_chain(symbol)
            last = get_last_price(symbol)
            label = symbol
        chain.set(df)
        spot.set(last)
        expiries = sorted(df["expirationDate"].dt.strftime("%Y-%m-%d").unique())
        ui.update_select("smile_expiry", choices=[ALL_EXPIRIES] + expiries)
        status.set(f"Loaded {len(df)} contracts for {label}; spot {last:.2f}.")
    except Exception as exc:  # network errors, unknown symbols, missing yfinance ...
        chain.set(None)
        spot.set(None)
        status.set(f"Could not load data: {exc}")


@reactive.calc
def chain_with_iv():
    """The loaded chain plus our own implied vol (from the bid/ask mid) for every contract."""
    df, last = chain.get(), spot.get()
    if df is None:
        return None
    frame = pd.DataFrame({"type": df["CALL"], "S": last, "K": df["strike"], "T": df["T"],
                          "r": risk_free(), "q": div_yield(), "price": df["mid"]}, index=df.index)
    res = run_engine(frame)
    out = df.copy()
    out["iv"] = res["iv"]
    out["iv_status"] = res["iv_status"]
    return out


@reactive.calc
def surface_data():
    """Smile points for every expiry (one engine call); the smile view filters this by expiry."""
    df, last = chain.get(), spot.get()
    if df is None:
        return None
    return vol_smile_pipeline(df, last, risk_free(), div_yield(), max_rel_spread=input.max_spread() / 100.0)


# ------------------------------------------------------------------------------ Option Table
with ui.panel_conditional("input.view_type === 'Option Table'"):
    with ui.card(full_screen=True, style="max-height: 75vh; overflow-y: auto;"):
        ui.card_header("Option chain")

        @render.table
        def option_table():
            df = chain_with_iv()
            if df is None:
                return message("No data loaded. Click 'Load option chain'.")
            try:
                if input.call_option() == "Call":
                    df = df[df["CALL"]]
                elif input.call_option() == "Put":
                    df = df[~df["CALL"]]
                min_strike = input.strike_price()
                if min_strike:
                    df = df[df["strike"] >= float(min_strike)]
                lo, hi = input.iv_range()
                if (lo, hi) != (0, 300):
                    df = df[(df["iv"] * 100 >= lo) & (df["iv"] * 100 <= hi)]
                if df.empty:
                    return message("No options match the current filters.")
                show = pd.DataFrame({
                    "Contract": df["contractSymbol"], "Type": np.where(df["CALL"], "call", "put"),
                    "Expiry": df["expirationDate"].dt.strftime("%Y-%m-%d"), "Days": df["dte"].round(1),
                    "Strike": df["strike"], "Bid": df["bid"], "Ask": df["ask"], "Mid": df["mid"].round(4),
                    "Volume": df.get("volume"), "Open int.": df.get("openInterest"),
                    "Yahoo IV (%)": (df["impliedVolatility"] * 100).round(2) if "impliedVolatility" in df else np.nan,
                    "IV from mid (%)": (df["iv"] * 100).round(2), "IV status": df["iv_status"],
                })
                return show.head(int(input.items_per_page()))
            except Exception as exc:
                return message(f"An error occurred: {exc}")


# ------------------------------------------------------------------------ Option Calculator
with ui.panel_conditional("input.view_type === 'Option Calculator'"):
    with ui.layout_columns(col_widths=[6, 6]):
        with ui.card(full_screen=True):
            ui.card_header("Value a listed contract (uses the loaded chain)")
            ui.input_text("contract_symbol", "Contract symbol (OCC)", placeholder="e.g. AAPL241115C00230000")
            ui.input_select("vol_source", "Volatility for price and Greeks",
                            {"mid_iv": "Implied from the bid/ask mid", "yahoo_iv": "Yahoo Finance implied vol"})
            ui.input_action_button("value_contract", "Value contract", style="background-color: #1560BD; color: white;")

            @render.table
            @reactive.event(input.value_contract)
            def contract_valuation():
                df, last = chain.get(), spot.get()
                if df is None:
                    return message("Load an option chain first.")
                symbol = (input.contract_symbol() or "").strip().upper()
                try:
                    val = valuation_pipeline(df, symbol, last, risk_free(), div_yield(), input.vol_source())
                except ValueError as exc:
                    return message(str(exc))
                row = val.iloc[0]
                shown = add_display_greeks(val.rename(columns={"Vega": "vega", "Theta": "theta", "Rho": "rho"}))
                out = pd.DataFrame({
                    "Price": [row["Price"]], "Delta": [row["Delta"]], "Gamma": [row["Gamma"]],
                    "Vega (per vol pt)": shown["vega_1pct"], "Theta (per day)": shown["theta_day"],
                    "Rho (per 1%)": shown["rho_1pct"], "Vol used (%)": [row["Sigma"] * 100],
                    "IV from mid (%)": [row["IV"] * 100], "IV status": [row["IV_status"]],
                }).round(5)
                note = IV_STATUS_HELP.get(row["IV_status"], "")
                if note:
                    out["Note"] = note
                return out

        with ui.card(full_screen=True):
            ui.card_header("Manual Black-Scholes calculator")
            with ui.layout_columns(col_widths=[6, 6]):
                ui.input_numeric("calc_spot", "Spot S", 100, min=0.0001)
                ui.input_numeric("calc_strike", "Strike K", 100, min=0.0001)
                ui.input_numeric("calc_days", "Days to expiry", 30, min=0.01)
                ui.input_numeric("calc_vol", "Volatility (%)", 25, min=0.01)
                ui.input_select("calc_type", "Option type", ["call", "put"])
                ui.input_numeric("calc_price", "Market price (0 = none)", 0, min=0)

            @render.table
            def manual_result():
                try:
                    price = input.calc_price()
                    row = {"type": input.calc_type(), "S": input.calc_spot(), "K": input.calc_strike(),
                           "T": (input.calc_days() or 0) / 365.0, "r": risk_free(), "q": div_yield(),
                           "sigma": (input.calc_vol() or 0) / 100.0, "price": price if price else np.nan}
                    res = add_display_greeks(run_engine(pd.DataFrame([row])))
                except Exception as exc:
                    return message(f"An error occurred: {exc}")
                r0 = res.iloc[0]
                if r0["row_status"] != "ok":
                    return message("Invalid inputs: spot, strike, days and volatility must be positive.")
                out = pd.DataFrame({
                    "Price": [r0["price_model"]], "Delta": [r0["delta"]], "Gamma": [r0["gamma"]],
                    "Vega (per vol pt)": [r0["vega_1pct"]], "Theta (per day)": [r0["theta_day"]],
                    "Rho (per 1%)": [r0["rho_1pct"]],
                })
                if price:
                    out["Implied vol (%)"] = r0["iv"] * 100
                    out["IV status"] = r0["iv_status"]
                return out.round(5)


# ------------------------------------------------------------------------------ Vol Smile
with ui.panel_conditional("input.view_type === 'Vol Smile'"):
    with ui.card(full_screen=True):
        ui.card_header("Implied volatility smile (out-of-the-money options, bid/ask mid)")

        @render_plotly
        def smile_plot():
            data = surface_data()
            if data is None:
                return empty_figure("No data loaded. Click 'Load option chain'.")
            selected = input.smile_expiry()
            if selected and selected != ALL_EXPIRIES:
                data = data[data["expirationDate"] == pd.Timestamp(selected)]
            return smile_figure(data, title=f"Implied volatility smile - {selected or ALL_EXPIRIES}",
                                x=input.smile_x(), show_yahoo=input.show_yahoo())


# ---------------------------------------------------------------------------- Vol Surface
with ui.panel_conditional("input.view_type === 'Vol Surface'"):
    with ui.card(full_screen=True):
        ui.card_header("Implied volatility surface")

        @render_plotly
        def surface_plot():
            data = surface_data()
            if data is None:
                return empty_figure("No data loaded. Click 'Load option chain'.")
            return surface_figure(data)
