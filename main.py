import ccxt
import time
import requests
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_balance(exchange):
    try:
        balance = exchange.fetch_balance()
        print("\n--- Testnet Balance ---")
        if 'total' in balance:
            # Print USDT and BTC balances specifically as they are relevant to the pair
            usdt = balance['total'].get('USDT', 0)
            btc = balance['total'].get('BTC', 0)
            print(f"USDT: {usdt}")
            print(f"BTC:  {btc}")
    except Exception as e:
        print(f"Error fetching balance: {e}")

def send_discord_alert(message):
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("Discord Webhook URL not set. Skipping alert.")
        return

    try:
        response = requests.post(
            webhook_url, 
            json={"content": message}, 
            timeout=5
        )
        response.raise_for_status()
        print("Discord alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")
def execute_trade(exchange, symbol, signal, price):
    """
    Executes trade based on signal and balance availability.
    Returns True if trade was executed, False otherwise.
    """
    try:
        # Fetch Balance First
        balance = exchange.fetch_balance()
        usdt_free = balance['total'].get('USDT', 0)
        btc_free = balance['total'].get('BTC', 0)
        
        amount = 0.001
        
        if signal == 'BUY':
            if usdt_free > 10:
                print(f"Signal: BUY (Price > SMA) | USDT Free: {usdt_free:.2f}")
                order = exchange.create_market_buy_order(symbol, amount)
                print(f"BUY Execution: {order['id']} | Fill Price: {order.get('price', 'Market')}")
                return True
            else:
                print(f"Signal is BUY, but already fully invested (No USD). Balance: {usdt_free:.2f} USDT")
                return False
                
        elif signal == 'SELL':
            if btc_free > 0.0005:
                print(f"Signal: SELL (Price < SMA) | BTC Free: {btc_free:.5f}")
                order = exchange.create_market_sell_order(symbol, amount)
                print(f"SELL Execution: {order['id']} | Fill Price: {order.get('price', 'Market')}")
                return True
            else:
                print(f"Signal is SELL, but already sold (No BTC). Balance: {btc_free:.5f} BTC")
                return False
                
        else:
            print("Signal: HOLD (Price == SMA)")
            return False
            
    except Exception as e:
        print(f"Error executing trade: {e}")
        return False

def run_bot(exchange, last_action, symbol='BTC/USDT'):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fetching data for {symbol}...")
    
    try:
        # 1. Fetch History
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # 2. Calculate SMA-20
        df['sma_20'] = df['close'].rolling(window=20).mean()
        
        last_close = df['close'].iloc[-1]
        last_sma = df['sma_20'].iloc[-1]
        
        # Determine Trend
        trend = "BULLISH" if last_close > last_sma else "BEARISH"
        
        print(f"Price: {last_close:.2f} | SMA-20: {last_sma:.2f} | Trend: {trend}")
        
        # 3. Decision Logic
        signal = 'HOLD'
        if last_close > last_sma:
            signal = 'BUY'
        elif last_close < last_sma:
            signal = 'SELL'
            
        # 4. State Machine Check
        if signal == last_action:
            print(f"Signal {signal} ignored: Already in position.")
            print_balance(exchange)
            return last_action
            
        # 5. Execute Trade with Balance Checks
        if signal != 'HOLD':
            executed = execute_trade(exchange, symbol, signal, last_close)
            if executed:
                # Update last_action only if trade succeeded
                # Also Show updated balance
                print_balance(exchange)
                
                # Send Discord Alert
                alert_msg = f"TRADE EXECUTED: {signal} {symbol} at {last_close:.2f}"
                send_discord_alert(alert_msg)
                
                return signal
        
        # If HOLD or Trade Failed, keep state
        print_balance(exchange)
        return last_action

    except Exception as e:
        print(f"An error occurred: {e}")
        return last_action

def main():
    print("Starting Crypto Bot in [TESTNET] mode...")
    
    api_key = os.getenv('BINANCE_TESTNET_KEY')
    secret_key = os.getenv('BINANCE_TESTNET_SECRET')

    if not api_key or not secret_key:
        print("Error: BINANCE_TESTNET_KEY or BINANCE_TESTNET_SECRET not found in .env")
        return

    # Initialize Binance Testnet
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret_key,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
        }
    })
    
    # CRITICAL: Enable Sandbox Mode
    exchange.set_sandbox_mode(True)
    print("--- Binance Sandbox Mode Enabled ---")
    
    # Verify connection
    try:
        exchange.load_markets()
        print("Connected to Binance Testnet successfully!")
        send_discord_alert("Bot started and connected to Binance Testnet successfully!")
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    # --- Initial State Detection ---
    print("Detecting initial state...")
    try:
        balance = exchange.fetch_balance()
        usdt_total = balance['total'].get('USDT', 0)
        btc_total = balance['total'].get('BTC', 0)
        
        # Get current price for valuation
        ticker = exchange.fetch_ticker('BTC/USDT')
        current_price = ticker['last']
        
        btc_value_in_usdt = btc_total * current_price
        
        last_action = 'SELL' # Default to SELL (Cash position)
        if btc_value_in_usdt > usdt_total:
            last_action = 'BUY' # Invested position
            
        print(f"Initial State detected as: {last_action} (BTC Value: ${btc_value_in_usdt:.2f} vs USDT: ${usdt_total:.2f})")
        
    except Exception as e:
        print(f"Error detecting initial state: {e}")
        last_action = None

    print("Starting Trading Loop (Interval: 10s)... Press Ctrl+C to stop.")
    
    while True:
        last_action = run_bot(exchange, last_action)
        time.sleep(10)

if __name__ == "__main__":
    main()
