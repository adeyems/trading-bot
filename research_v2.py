import pandas as pd
import numpy as np

def calculate_advanced_indicators(df):
    # --- Z-Score (Statistical) ---
    df['mean_20'] = df['close'].rolling(window=20).mean()
    df['std_20'] = df['close'].rolling(window=20).std()
    df['z_score'] = (df['close'] - df['mean_20']) / df['std_20']

    # --- ATR (Volatility) ---
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()

    # --- KAMA (Adaptive Moving Average) ---
    # ER = Change / Volatility
    # Change = abs(Price - Price[n])
    # Volatility = sum(abs(Price[i] - Price[i-1]))
    n = 10
    df['change'] = abs(df['close'] - df['close'].shift(n))
    df['volatility'] = df['close'].diff().abs().rolling(window=n).sum()
    df['er'] = df['change'] / df['volatility']
    
    # SC = [ER * (2/(2+1) - 2/(30+1)) + 2/(30+1)] ^ 2
    fast_sc = 2/(2+1)
    slow_sc = 2/(30+1)
    df['sc'] = (df['er'] * (fast_sc - slow_sc) + slow_sc) ** 2
    
    # KAMA Calculation loop
    kama = [df['close'].iloc[0]] * len(df)
    for i in range(n, len(df)):
        kama[i] = kama[i-1] + df['sc'].iloc[i] * (df['close'].iloc[i] - kama[i-1])
    df['kama'] = kama
    
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
    z_scores = df['z_score'].values
    atrs = df['atr'].values
    kamas = df['kama'].values
    
    stop_loss = 0.10 # Standardization
    
    for i in range(50, len(df)):
        price = closes[i]
        
        # --- STRATEGY LOGIC ---
        buy_signal = False
        sell_signal = False
        
        if strategy_name == "Z-Score (Statistical)":
            # Buy Extreme Deviation (-2 Sigma)
            if z_scores[i] < -2.0:
                 buy_signal = True
            # Sell Mean Reversion (+1 Sigma or +2)
            if z_scores[i] > 2.0:
                 sell_signal = True
                 
        elif strategy_name == "ATR Breakout":
            # Comparison to previous close
            prev_close = closes[i-1]
            atr = atrs[i-1]
            
            # Massive Volatility Upside
            if price > prev_close + (2 * atr):
                buy_signal = True
            # Stop / Reversal
            if price < prev_close - (1 * atr):
                sell_signal = True
                
        elif strategy_name == "KAMA (Adaptive)":
            # Trend Check
            if price > kamas[i] and closes[i-1] <= kamas[i-1]:
                buy_signal = True
            if price < kamas[i]:
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
                if usdt_balance > (entry_price * (initial_balance/entry_price)):
                     wins += 1
                     
        elif not in_position and buy_signal:
            btc_balance = usdt_balance / price
            usdt_balance = 0
            in_position = True
            entry_price = price
            trades += 1
            
    # Final Value
    final_equity = usdt_balance + (btc_balance * closes[-1])
    roi = ((final_equity - initial_balance) / initial_balance) * 100
    win_rate = (wins / (trades/2)) * 100 if trades > 0 else 0
    
    return roi, int(trades/2), win_rate

def research():
    try:
        df = pd.read_csv('btc_4h_2024.csv') # Use 2024 data
        df = calculate_advanced_indicators(df)
    except:
        print("Error: 2024 Data not found.")
        return

    strategies = ["Z-Score (Statistical)", "ATR Breakout", "KAMA (Adaptive)"]
    
    print(f"--- Advanced Strategy Analysis (2024 Data) ---")
    print(f"{'Strategy':<25} | {'ROI':<10} | {'Trades':<8} | {'Win Rate':<8}")
    print("-" * 60)
    
    for strat in strategies:
        roi, trades, wr = run_simulation(df, strat)
        print(f"{strat:<25} | {roi:>8.2f}% | {trades:>8} | {wr:>7.1f}%")

if __name__ == "__main__":
    research()
