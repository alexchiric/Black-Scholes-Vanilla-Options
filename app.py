from shiny import App, ui, render, reactive
import yfinance as yf
import pandas as pd
from option_data import get_option_chain, get_last_price

# Define the UI for the app
app_ui = ui.page_fluid(
    # Link the custom CSS file
    ui.tags.link(rel="stylesheet", href="static/css/styles.css"),
    
    ui.h2("Options Calculator", class_="text-center"),
    ui.p("Enter a stock symbol to retrieve the corresponding options chain. Use the stock symbol (e.g., AAPL, TSLA, GOOGL).", class_="text-center"),
    
    ui.input_text("symbol", "Stock Symbol", value="AAPL"),                          # Input field for symbol
    ui.output_text("last_price"),
    ui.input_action_button("fetch", "Get Options", class_="btn btn-primary mt-2"),  # Button to fetch options
    
    ui.output_ui("loading_message"),                                                # Loading message during data fetch
    ui.output_table("options_table", class_="table table-striped mt-3")             # Styled table output
)

# Define the server logic
# Define the server logic
def server(input, output, session):
    # Manage loading states
    is_loading = reactive.Value(False)

    @output
    @render.text
    def loading_message():
        if is_loading.get():
            return "Loading options data, please wait..."
        return ""

    @output
    @render.text
    def last_price():
        symbol = input.symbol()
        try:
            price = get_last_price(symbol)  # Assuming this function retrieves the last price
            return f"Last Price: ${price:.2f}" if price is not None else "Price not available."
        except Exception as e:
            return f"Error fetching price: {e}"

    @output
    @render.table
    def options_table():
        # Fetch the option chain DataFrame for the given symbol
        symbol = input.symbol()
        is_loading.set(True)
        try:
            options_df = get_option_chain(symbol)  # Only expect one value (the DataFrame)

            if options_df.empty:
                return pd.DataFrame({"Error": [f"No option data found for symbol {symbol}."]})

            # Display the entire options DataFrame
            return options_df
        
        except Exception as e:
            return pd.DataFrame({"Error": [f"An error occurred: {e}"]})
        
        finally:
            is_loading.set(False)

# Create the app
app = App(app_ui, server)

# Run the app
if __name__ == "__main__":
    app.run()