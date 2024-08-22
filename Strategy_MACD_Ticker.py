import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from alpaca_trade_api.rest import REST, TimeFrame
from pytz import timezone

# Alpaca and Polygon API keys
ALPACA_API_KEY = 'your_alpaca_api_key'
ALPACA_API_SECRET = 'your_alpaca_api_secret'
POLYGON_API_KEY = 'your_polygon_api_key'
option_size = 100
Stock_Name = 'your_stock_name'
Expiration_Date = 'your_expiration_date'  # Your desired option expiration date for example: '2024-08-23'
Strike_Price_Gap = 'your_strike_price_gap'  # Your desired strike price for the option contract - stock price = Strike_Price_Gap. This should be a positive number

# Initialize Alpaca API
alpaca = REST(ALPACA_API_KEY, ALPACA_API_SECRET, base_url='https://paper-api.alpaca.markets')

# Trading and Logging variables
balance = 1000  # Starting balance
option_holding = False
call_option_holding = False
put_option_holding = False
transaction_log = []

# Fetch the real-time stock price
def fetch_stock_price(ticker):
    url = f"https://api.polygon.io/v2/last/nbbo/{ticker}?apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()
    return response['results']['P']

# Fetch the MACD values
def fetch_macd_data(ticker):
    url = f"https://api.polygon.io/v1/indicators/macd/{Stock_Name}?timespan=minute&adjusted=true&short_window=12&long_window=26&signal_window=9&apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()
    return response['results']['values']

# Fetch the option price from Alpaca API
def fetch_option_price(option_ticker, type):
    url = f"https://data.alpaca.markets/v1beta1/options/quotes/latest?symbols={option_ticker}&feed=indicative"
    response = requests.get(url, headers={
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_API_SECRET
    })
    if response.status_code == 200:
        # if it is a sell option, return the bid price
        if type == 'sell':
            return response.json()['quotes'][option_ticker]['bp']
        return response.json()['quotes'][option_ticker]['ap']
    else:
        print(f"Failed to fetch option price for {option_ticker}. Status code: {response.status_code}")
        return None

# Determine the best option strike price based on stock price and strategy
def select_option_contract(stock_price, option_type):
    strike_price = round(stock_price + Strike_Price_Gap) if option_type == 'call' else round(stock_price - Strike_Price_Gap)
    url = f"https://paper-api.alpaca.markets/v2/options/contracts?underlying_symbols={Stock_Name}&strike_price_gte={strike_price}&expiration_date={Expiration_Date}&type={option_type}"
    response = requests.get(url, headers={
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_API_SECRET
    })
    if response.status_code == 200:
        return response.json()['option_contracts'][0]['symbol']
    else:
        print(f"Failed to fetch option contract. Status code: {response.status_code}")
        return None

# Convert timezone-aware datetime objects to naive datetime objects
def make_datetime_naive(dt):
    return dt.replace(tzinfo=None)

# Trading strategy logic
def trade_strategy(ticker):
    global balance, option_holding, transaction_log, call_option_holding, put_option_holding
    pacific = timezone('America/Los_Angeles')
    eastern = timezone('America/New_York')

    while True:
        # Get current time in Eastern Time (market hours), If you live in a different timezone, you should change the timezone!!!
        now = datetime.now(pacific).astimezone(eastern)
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        if market_open <= now <= market_close:
            # Fetch current stock price
            current_stock_price = fetch_stock_price(ticker)
            print(f"Current stock price: {current_stock_price}")

            # Fetch MACD values
            macd_data = fetch_macd_data(ticker)
            hist_values = [data['histogram'] for data in macd_data]

            # Trading decision logic based on MACD strategy
            if option_holding:
                # Sell logic for call/put option
                if len(hist_values) >= 9:
                    first = (hist_values[0] + hist_values[1] + hist_values[2]) / 3
                    second = (hist_values[3] + hist_values[4] + hist_values[5]) / 3
                    third = (hist_values[6] + hist_values[7] + hist_values[8]) / 3
                    if first < second and second < third and call_option_holding:  # 3 minute interval decrease
                        print("Selling option based on 3-minute interval decrease.")
                        # Fetch current option price and sell
                        current_option_price = fetch_option_price(current_option_ticker, 'sell')
                        if current_option_price:
                            balance += current_option_price * option_size  # Adjust balance
                            transaction_log.append({
                                'timestamp': make_datetime_naive(now),  # Make datetime naive
                                'action': 'sell',
                                'option_type': 'call',
                                'option_ticker': current_option_ticker,
                                'option_price': current_option_price,
                                'stock_price': current_stock_price
                            })
                            print(f"Sold Call Option at {current_option_price}. Balance: {balance}. Timestamp: ", now)
                            option_holding = False
                            call_option_holding = False
                            current_option_ticker = None

                    elif first > second and second > third and put_option_holding:
                        print("Selling option based on 3-minute interval increase.")
                        # Fetch current option price and sell
                        current_option_price = fetch_option_price(current_option_ticker, 'sell')
                        if current_option_price:
                            balance += current_option_price * option_size
                            transaction_log.append({
                                'timestamp': make_datetime_naive(now),  # Make datetime naive
                                'action': 'sell',
                                'option_type': 'put',
                                'option_ticker': current_option_ticker,
                                'option_price': current_option_price,
                                'stock_price': current_stock_price
                            })
                            print(f"Sold Put Option at {current_option_price}. Balance: {balance}. Timestamp: ", now)
                            option_holding = False
                            put_option_holding = False
                            current_option_ticker = None
            else:
                # Buy call option
                print(f"MACD Histogram values: {hist_values}")
                if len(hist_values) >= 9:
                    firstMinute = (hist_values[0] + hist_values[1] + hist_values[2]) / 3
                    secondMinute = (hist_values[3] + hist_values[4] + hist_values[5]) / 3 
                    thirdMinute = (hist_values[6] + hist_values[7] + hist_values[8]) / 3
                    if firstMinute > secondMinute and secondMinute > thirdMinute and firstMinute - thirdMinute >= 0.05:  # Buy logic
                        print("Buying option based on MACD strategy.")
                        # Select option contract
                        option_ticker = select_option_contract(current_stock_price, 'call')
                        if option_ticker:
                            current_option_price = fetch_option_price(option_ticker, 'buy')
                            if current_option_price and current_option_price * option_size <= balance:
                                balance -= current_option_price * option_size  # Adjust balance
                                current_option_ticker = option_ticker
                                transaction_log.append({
                                    'timestamp': make_datetime_naive(now),  # Make datetime naive
                                    'action': 'buy',
                                    'option_type': 'call',
                                    'option_ticker': current_option_ticker,
                                    'option_price': current_option_price,
                                    'stock_price': current_stock_price
                                })
                                print(f"Bought Call option at {current_option_price}. Strike price around {current_stock_price + 10}. Balance: {balance}. Timestamp: ", now)
                                option_holding = True
                                call_option_holding = True
                    else:
                      # buy put option
                      if firstMinute < secondMinute and secondMinute < thirdMinute and thirdMinute - firstMinute >= 0.05:  # Sell logic
                        # Select option contract
                        option_ticker = select_option_contract(current_stock_price, 'put')
                        if option_ticker:
                          current_option_price = fetch_option_price(option_ticker, 'buy')
                          if current_option_price and current_option_price * option_size <= balance:
                            balance -= current_option_price * option_size  # Adjust balance
                            current_option_ticker = option_ticker
                            transaction_log.append({
                              'timestamp': make_datetime_naive(now),  # Make datetime naive
                              'action': 'buy',
                              'option_type': 'put',
                              'option_ticker': current_option_ticker,
                              'option_price': current_option_price,
                              'stock_price': current_stock_price
                            })
                            print(f"Bought Put option at {current_option_price}. Strike price around {current_stock_price - 10}. Balance: {balance}. Timestamp: ", now)
                            option_holding = True
                            put_option_holding = True

            # Check for stop loss logic every minute
            if option_holding:
                stop_loss_threshold = current_option_price * 0.8
                current_option_price = fetch_option_price(current_option_ticker, 'sell')
                if current_option_price and current_option_price < stop_loss_threshold:
                    print("Stop loss triggered. Selling option. Timestamp: ", now)
                    balance += current_option_price * option_size  # Adjust balance
                    transaction_log.append({
                        'timestamp': make_datetime_naive(now),  # Make datetime naive
                        'action': 'stop_loss',
                        'option_type': 'call/put',
                        'option_ticker': current_option_ticker,
                        'option_price': current_option_price,
                        'stock_price': current_stock_price
                    })
                    option_holding = False
                    call_option_holding = False
                    put_option_holding = False

            # Check for market close and log the data
            if now >= market_close - timedelta(minutes=32):
                if option_holding:
                    current_option_price = fetch_option_price(current_option_ticker, 'sell')
                    if current_option_price:
                        balance += current_option_price * option_size  # Adjust balance
                        transaction_log.append({
                            'timestamp': make_datetime_naive(now),  # Make datetime naive
                            'action': 'sell_at_close',
                            'option_type': 'call/put',
                            'option_ticker': current_option_ticker,
                            'option_price': current_option_price,
                            'stock_price': current_stock_price
                        })
                        print(f"Closed position at market close. Sold at {current_option_price}. Balance: {balance}")
                        option_holding = False

                # Log transactions to Excel file at the end of the day
                df_log = pd.DataFrame(transaction_log)
                df_log.to_excel("trading_log_TSLA.xlsx", index=False)
                print("Market closed. Trading log saved to 'trading_log.xlsx'.")
                break  # End the trading loop since the market is closed

        else:
            print("Market is not open yet, waiting...")
            time.sleep(60)  # Wait a minute before checking again

        # Sleep for 0.5 minute before the next price check
        time.sleep(30)

# Main function to start the trading simulation
def run_simulation(ticker):
    print(f"Starting trading simulation for {ticker}...")
    try:
        trade_strategy(ticker)
    except Exception as e:
        print(f"An error occurred: {e}")

# Run the simulation for TSLA
run_simulation(Stock_Name)