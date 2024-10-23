from shiny.express import input,render,ui
from shinywidgets import render_plotly
import pandas as pd
from option_data import get_option_chain, get_last_price

ui.page_opts(title="Black-Scholes-Vanilla-Options", fillable=True)

with ui.sidebar():
    ui.input_selectize(
        "view", "Select view type",
        ["Option Table", "view_2", "view_3", "view_4"]
    )
    ui.input_text("symbols", "Stock Symbol", "AAPL")  
    ui.input_selectize(
        "items_per_page", "Items per Page",
        [100, 200, 300]
    ) 
    ui.input_select(
        "call_option", "Call Option",
        ["All", "Call", "Put"]
    )
    ui.input_numeric("strike_price", "Strike Price", "None")

with ui.card(full_screen=True):
    @render.table
    def option_table():
        symbol = input.symbols()
        ui_card_view = input.view()
        if ui_card_view != "Option Table":
            return pd.DataFrame({"Message": ["Select 'Option Table' to view the option data."]})
        
        """
        Option Table View
        """
        if ui_card_view == "Option Table":
            try:
                options_df = get_option_chain(symbol)  # Only expect one value (the DataFrame)

                if options_df.empty:
                    return pd.DataFrame({"Error": [f"No option data found for symbol {symbol}."]})

                # Display the entire options DataFrame
                head_size = int(input.items_per_page())
                match input.call_option():
                    case "All":
                        return options_df.head(head_size)
                    case "Call":
                        call_options_df = options_df[options_df['CALL'] == True]
                    case "Put":
                        call_options_df = options_df[options_df['CALL'] == False]
                return call_options_df
            
            except Exception as e:
                return pd.DataFrame({"Error": [f"An error occurred: {e}"]})
            

        """
        view_2
        """
        # Code view_4

        """
        view_3
        """
        # Code view_3

        """
        view_4
        """
        # Code view_4
        