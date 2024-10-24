from shiny.express import input,render,ui
from shiny import reactive
from shinyswatch import theme
from shinywidgets import render_plotly
import pandas as pd
from option_data import get_option_chain, get_last_price

ui.page_opts(title="Black Scholes Vanilla Options",theme=theme.darkly, fillable=True)

with ui.sidebar():
    ui.input_selectize(
        "view_type", "Select view type",
        ["Option Table", "Option Calculator", "view_3", "view_4"]
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
    ui.input_slider("implied_volatility", "Implied Volatility", min=0, max=1,value=[0,1])

with ui.card(fill=False):
    with ui.div():
        ui.input_text("symbols_unique_identifier", "Enter your unique symbol identifier", "AAPL000000000000000")
        ui.input_action_button("search_symbol", "Search",style="background-color: #1560BD; color: white;")

with ui.card(full_screen=True,style="max-height: 75vh; overflow-y: auto;"):
    @render.table
    def option_table():
        symbol = input.symbols()
        # ui_card_view = input.view()
        ui_card_view = ui_card_view_global()
        if ui_card_view != "Option Table" and ui_card_view != "Option Calculator" :
            return pd.DataFrame({"Message": ["Select 'Option Table' to view the option data."]})
        
        """
        Option Table View
        """
        if ui_card_view == "Option Table":
            try:
                options_df = get_option_chain(symbol)

                if options_df.empty:
                    return pd.DataFrame({"Error": [f"No option data found for symbol {symbol}."]})

                # Display the entire options DataFrame
                head_size = int(input.items_per_page())
                ui_call_option = input.call_option()
                if input.implied_volatility() ==[0,1]:
                    return input.implied_volatility()
                if input.strike_price() != None :
                    strike_value = float(input.strike_price())
                    options_df = options_df[options_df['strike'] >= strike_value]
                if ui_call_option == "All":
                    call_options_df = options_df.head(head_size)
                if ui_call_option == "Call":
                    call_options_df = options_df[options_df['CALL'] == True]
                if ui_call_option == "Put":
                    call_options_df = options_df[options_df['CALL'] == False]

                return call_options_df 

            except Exception as e:
                return pd.DataFrame({"Error": [f"An error occurred: {e}"]})
            

        """
        Option Calculator
        """
        if ui_card_view == "Option Calculator":
            return pd.DataFrame({"Message": ["No given Symbol for Option Calculator"]})

        """
        view_3
        """
        # Code view_3

        """
        view_4
        """
        # Code view_4

ui_card_view_global = reactive.value("Option Table")
temp_view_type= reactive.value("Option Table")
@reactive.effect
@reactive.event(input.search_symbol)
def search_symbol_option_calculator():
    ui_card_view_global.set("Option Calculator")
    ui.update_selectize("view_type",selected="Option Calculator")

@reactive.effect
@reactive.event(input.view_type)
def search_symbol_option_calculator():
    if input.view_type() == "Option Calculator" and temp_view_type!="Option Calculator":
        ui_card_view_global.set("Option Calculator")
        temp_view_type.set("Option Calculator")
        ui.update_selectize("view_type",selected="Option Calculator")
    if input.view_type() == "Option Table" and temp_view_type!="Option Table":
        ui_card_view_global.set("Option Table")
        temp_view_type.set("Option Table")
        ui.update_selectize("view_type",selected="Option Table")
    if input.view_type() == "view_3" and temp_view_type!="view_3":
        ui_card_view_global.set("view_3")
        temp_view_type.set("view_3")
        ui.update_selectize("view_type",selected="view_3")
    if input.view_type() == "view_4" and temp_view_type!="view_4":
        ui_card_view_global.set("view_4")
        temp_view_type.set("view_4")
        ui.update_selectize("view_type",selected="view_4")