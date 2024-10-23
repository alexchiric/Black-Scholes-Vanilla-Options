from shiny import App, ui, render
import yfinance as yf
import pandas as pd
from option_data import get_option_chain, get_last_price

# Define the UI for the app
app_ui = ui.page_fluid(
    ui.h2("Options Calculator"),
    ui.input_text("symbol", "Stock Symbol", value="AAPL"),  # Input field for symbol
    ui.output_text("last_price"),
    ui.output_table("options_table")  # Table output to display the options chain
)

# Define the server logic
def server(input, output, session):

    @output   
    @render.text(inline=True)
    def last_price():
        symbol = input.symbol()
        try:
            last_price = get_last_price(symbol)
            return f'The last price for {symbol} is {last_price:.2f}'

        except Exception as e:
            return pd.DataFrame({"Error": [f"An error occurred: {e}"]})


    @render.table
    def options_table():
        # Fetch the option chain DataFrame for the given symbol
        symbol = input.symbol()
        try:
            options_df = get_option_chain(symbol)  # Only expect one value (the DataFrame)

            if options_df.empty:
                return pd.DataFrame({"Error": [f"No option data found for symbol {symbol}."]})

            # Display the entire options DataFrame
            return options_df
        
        except Exception as e:
            return pd.DataFrame({"Error": [f"An error occurred: {e}"]})

# Create the app
app = App(app_ui, server)

# Run the app
if __name__ == "__main__":
    app.run()