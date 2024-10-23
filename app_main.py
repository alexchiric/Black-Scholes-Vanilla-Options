from shiny.express import input,render,ui
from shinywidgets import render_plotly
import pandas as pd
from option_data import get_option_chain, get_last_price

ui.page_opts(title="Black-Scholes-Vanilla-Options", fillable=True)

with ui.sidebar():
    ui.input_selectize(
        "view", "Select view type",
        ["option_table", "view_2", "view_3", "view_4"]
    )
    ui.input_text("symbols", "Stock Symbol", "AAPL")
    ui.input_selectize(
        "items_per_page", "Items per Page",
        [100, 200, 300]
    )

with ui.card(full_screen=True):
    @render.table
    def option_table():
        import plotly.express as px
        from palmerpenguins import load_penguins
        symbol = input.symbols()
        try:
            options_df = get_option_chain(symbol)  # Only expect one value (the DataFrame)

            if options_df.empty:
                return pd.DataFrame({"Error": [f"No option data found for symbol {symbol}."]})

            # Display the entire options DataFrame
            return options_df.head(int(input.items_per_page()))
        
        except Exception as e:
            return pd.DataFrame({"Error": [f"An error occurred: {e}"]})