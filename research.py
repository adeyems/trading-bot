import pandas as pd
import numpy as np

def calculate_indicators(df):
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    k = df['close'].ewm(span=12, adjust=False, min_periods=12).mean()
    d = df['close'].ewm(span=26, adjust=False, min_periods=26).mean()
    df['macd'] = k - d
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False, min_periods=9).mean()

    # Bollinger Bands (20, 2)
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_mid'] + (2 * df['bb_std'])
    df['bb_lower'] = df['bb_mid'] - (2 * df['bb_std'])
    
    return df

def run_simulation(df, strategy_name):
    initial_balance = 10000
    usdt_balance = initial_balance
    btc_balance = 0
    in_position = False
    entry_price = 0
    trades = 0
    wins = 0
    
    closes = df['close'].values
    rsis = df['rsi'].values
    macds = df['macd'].values
    signals = df['macd_signal'].values
    uppers = df['bb_upper'].values
    lowers = df['bb_lower'].values
    mids = df['bb_mid'].values
    
    stop_loss = 0.10 # 10% Hard Stop for fairness
    
    for i in range(50, len(df)):
        price = closes[i]
        
        # --- STRATEGY LOGIC ---
        buy_signal = False
        sell_signal = False
        
        if strategy_name == "Mean Reversion":
            if rsis[i] < 25: buy_signal = True
            if rsis[i] > 65: sell_signal = True
            
        elif strategy_name == "MACD Trend":
            # Buy: MACD crosses above Signal
            if macds[i] > signals[i] and macds[i-1] <= signals[i-1]:
                buy_signal = True
            # Sell: MACD crosses below Signal
            if macds[i] < signals[i] and macds[i-1] >= signals[i-1]:
                sell_signal = True
                
        elif strategy_name == "Bollinger Breakout":
            # Buy: Price breaks above Upper Band
            if price > uppers[i]:
                buy_signal = True
            # Sell: Price falls below Mid Band (Trend Weakness)
            if price < mids[i]:
                sell_signal = True

        # --- EXECUTION ---
        if in_position:
            # check stop loss
            pct = (price - entry_price) / entry_price
            if pct <= -stop_loss:
                sell_signal = True
            
            if sell_signal:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trades += 1
                if usdt_balance > (entry_price * (initial_balance/entry_price)): # Crude win check
                     wins += 1
                     
        elif not in_position and buy_signal:
            btc_balance = usdt_balance / price
            usdt_balance = 0
            in_position = True
            entry_price = price
            trades += 1 # Count entry as trade activity
            
    # Final Value
    final_equity = usdt_balance + (btc_balance * closes[-1])
    roi = ((final_equity - initial_balance) / initial_balance) * 100
    win_rate = (wins / (trades/2)) * 100 if trades > 0 else 0
    
    return roi, int(trades/2), win_rate

def research():
    try:
        df = pd.read_csv('btc_4h_2024.csv') # Use 2024 data
        df = calculate_indicators(df)
    except:
        print("Error: 2024 Data not found.")
        return

    strategies = ["Mean Reversion", "MACD Trend", "Bollinger Breakout"]
    
    print(f"--- Strategy Analysis (2024 Data) ---")
    print(f"{'Strategy':<20} | {'ROI':<10} | {'Trades':<8} | {'Win Rate':<8}")
    print("-" * 55)
    
    for strat in strategies:
        roi, trades, wr = run_simulation(df, strat)
        print(f"{strat:<20} | {roi:>8.2f}% | {trades:>8} | {wr:>7.1f}%")

if __name__ == "__main__":
    research()
