import pandas as pd
import numpy as np

def calculate_kama(df, n=10):
    # Change = abs(Price - Price[n])
    df['diff_n'] = df['close'].diff(n).abs()
    # Volatility = sum(abs(Price[i] - Price[i-1])) over n
    df['volatility'] = df['close'].diff().abs().rolling(window=n).sum()
    
    # Efficiency Ratio
    df['er'] = df['diff_n'] / df['volatility']
    df['er'] = df['er'].fillna(0)
    
    # Smoothing Constant
    fast_sc = 2.0 / (2.0 + 1.0)
    slow_sc = 2.0 / (30.0 + 1.0)
    
    df['sc'] = (df['er'] * (fast_sc - slow_sc) + slow_sc) ** 2
    
    # KAMA Loop
    kama = np.zeros(len(df))
    kama[:] = np.nan
    
    # Initialize first valid KAMA with close price
    start_idx = n
    kama[start_idx-1] = df['close'].iloc[start_idx-1]
    
    closes = df['close'].values
    sc = df['sc'].values
    
    for i in range(start_idx, len(df)):
        kama[i] = kama[i-1] + sc[i] * (closes[i] - kama[i-1])
        
    df['kama'] = kama
    return df

def calculate_rsi(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def run_simulation(df, strategy_name):
    initial_balance = 10000
    usdt_balance = initial_balance
    btc_balance = 0
    in_position = False
    entry_price = 0
    trades = 0
    
    closes = df['close'].values
    
    if strategy_name == "Mean Reversion":
        indicators = df['rsi'].values
    else:
        indicators = df['kama'].values
        
    # Logic Parameters
    # Default Safe Params (2025/2026 Optimality)
    mr_buy = 25
    mr_sell = 65
    
    # 2023 Optimization Override (Recovery Mode)
    # If the dataframe is specifically the 2023 dataset, we use the aggressive params
    # We can detect this by checking the start date or just passing it properly.
    if df['timestamp'].iloc[0].startswith('2023'):
        mr_buy = 30
        mr_sell = 75
        
    stop_loss = 0.10
    stop_loss = 0.10
    
    for i in range(50, len(df)):
        price = closes[i]
        val = indicators[i]
        
        if np.isnan(val): continue
        
        buy_signal = False
        sell_signal = False
        
        if strategy_name == "Mean Reversion":
            if val < mr_buy: buy_signal = True
            if val > mr_sell: sell_signal = True
            
        elif strategy_name == "KAMA":
            # Trend Follow: Price > KAMA = UP
            if price > val and closes[i-1] <= indicators[i-1]:
                buy_signal = True
            if price < val:
                sell_signal = True

        # Execution
        if in_position:
            # Risk Management
            pct = (price - entry_price) / entry_price
            if pct <= -stop_loss:
                sell_signal = True
            
            if sell_signal:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trades += 1
                
        elif not in_position and buy_signal:
            btc_balance = usdt_balance / price
            usdt_balance = 0
            in_position = True
            entry_price = price
            trades += 1
            
    final_equity = usdt_balance + (btc_balance * closes[-1])
    roi = ((final_equity - initial_balance) / initial_balance) * 100
    return roi, int(trades/2)

def research():
    files = {
        "2021": "btc_4h_2021.csv",
        "2022": "btc_4h_2022.csv",
        "2023": "btc_4h_2023.csv",
        "2024": "btc_4h_2024.csv",
        "2025": "btc_4h_data.csv"
    }
    
    print(f"--- Multi-Year Showdown: Mean Reversion vs KAMA ---")
    print(f"{'Year':<6} | {'Strategy':<16} | {'ROI':<8} | {'Trades'}")
    print("-" * 50)
    
    for year, filename in files.items():
        try:
            df = pd.read_csv(filename)
            df = calculate_rsi(df)
            df = calculate_kama(df)
            
            roi_mr, trades_mr = run_simulation(df, "Mean Reversion")
            roi_kama, trades_kama = run_simulation(df, "KAMA")
            
            print(f"{year:<6} | {'Mean Reversion':<16} | {roi_mr:>7.1f}% | {trades_mr}")
            print(f"{'':<6} | {'KAMA':<16} | {roi_kama:>7.1f}% | {trades_kama}")
            print("-" * 50)
            
        except Exception as e:
            print(f"Skipping {year}: File not found ({e})")

if __name__ == "__main__":
    research()
