import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import datetime

def get_option_chain(symbol):

    #get ticker data
    try:
        x = yf.Ticker(symbol)
    except:
        raise ValueError(f"Invalid symbol: {symbol}")

    #get expiry dates
    expiry_dates = x.options

    if not expiry_dates:
        raise ValueError(f"No expiry dates found for {symbol}")

    options = pd.DataFrame()

    for date in expiry_dates:
        opt = x.option_chain(date)
        opt_df = pd.concat([pd.DataFrame(opt.calls), pd.DataFrame(opt.puts)])
        opt_df['expirationDate'] = date
        options = pd.concat([options, opt_df], ignore_index=True)

    # There's an error in yahoo finance resulting in a wrong expiration date, we need to add 1 day to fix it
    options['expirationDate'] = pd.to_datetime(options['expirationDate']) + datetime.timedelta(days=1)
    options['dte'] = (options['expirationDate'] - datetime.datetime.today()).dt.days / 252  # considering 252 business days in a year

    # Identifying call options through a boolean column
    options['CALL'] = options['contractSymbol'].str[4:].apply(lambda x: "C" in x)

    options[['bid', 'ask', 'strike']] = options[['bid', 'ask', 'strike']].apply(pd.to_numeric)  # converting to numeric
    options['mid'] = (options['bid'] + options['ask']) / 2  # Calculate the midpoint (between bid and ask)

    # Removing unnecessary columns
    options = options.drop(columns=['contractSize', 'currency', 'change', 'percentChange', 'lastTradeDate', 'lastPrice'])

    return options

