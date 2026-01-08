import ccxt
import pandas as pd
import time

def calculate_indicators(df):
    # SMA 20
    df['sma_20'] = df['close'].rolling(window=20).mean()
    
    # RSI 14 (EMA based, matching main.py)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
    
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    return df

def run_backtest():
    print("--- Starting Backtest ---")
    
    # 1. Load Data from CSV
    try:
        print("Loading data from btc_1h_data.csv...")
        df = pd.read_csv('btc_1h_data.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except Exception as e:
        print(f"Error loading data: {e}. Make sure btc_1h_data.csv exists.")
        return
    
    # 2. Add Indicators
    df = calculate_indicators(df)
    
    # 3. Simulation Loop
    initial_balance = 10000
    usdt_balance = initial_balance
    btc_balance = 0
    in_position = False
    
    print(f"Testing Period: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    print(f"Initial Balance: ${initial_balance:,.2f}")
    
    trade_count = 0
    
    STOP_LOSS_PCT = 0.02
    TAKE_PROFIT_PCT = 0.04
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        price = row['close']
        sma = row['sma_20']
        rsi = row['rsi_14']
        
        # Logic matches main.py
        
        if in_position:
            # 1. RISK MANAGEMENT CHECK (Priority)
            pct_change = (price - entry_price) / entry_price
            
            # Stop Loss
            if pct_change <= -STOP_LOSS_PCT:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trade_count += 1
                # print(f"🛑 STOP LOSS at ${price:,.2f} | Time: {row['timestamp']}")
                continue # Skip remaining logic for this candle
                
            # Take Profit
            elif pct_change >= TAKE_PROFIT_PCT:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trade_count += 1
                # print(f"🥂 TAKE PROFIT at ${price:,.2f} | Time: {row['timestamp']}")
                continue # Skip remaining logic

            # 2. STRATEGY SELL Logic
            # Price < SMA OR RSI > 80
            if price < sma or rsi > 80:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trade_count += 1
                # print(f"SELL at ${price:,.2f} | Time: {row['timestamp']}")

        # BUY Logic: Price > SMA and RSI < 70 (and not in position)
        elif not in_position:
            if price > sma and rsi < 70:
                btc_balance = usdt_balance / price
                usdt_balance = 0
                in_position = True
                entry_price = price # Track entry for risk calcs
                trade_count += 1
                # print(f"BUY at ${price:,.2f} | Time: {row['timestamp']}")

    # Final Calculation - Bot
    final_price = df.iloc[-1]['close']
    bot_equity = usdt_balance + (btc_balance * final_price)
    bot_roi = ((bot_equity - initial_balance) / initial_balance) * 100
    
    # Final Calculation - Buy and Hold
    initial_price = df.iloc[0]['close']
    bh_btc_amount = initial_balance / initial_price
    bh_equity = bh_btc_amount * final_price
    bh_roi = ((bh_equity - initial_balance) / initial_balance) * 100
    
    print("-" * 30)
    print(f"Bot Final Balance: ${bot_equity:,.2f} (ROI: {bot_roi:.2f}%)")
    print(f"Buy & Hold Balance: ${bh_equity:,.2f} (ROI: {bh_roi:.2f}%)")
    print(f"Total Trades: {trade_count}")
    print("-" * 30)
    
    if bot_equity > bh_equity:
        print("✅ STRATEGY OUTPERFORMED MARKET")
    else:
        print("❌ STRATEGY UNDERPERFORMED MARKET")

if __name__ == "__main__":
    run_backtest()
