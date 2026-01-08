import pandas as pd

def calculate_indicators(df):
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # SMAs
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['sma_100'] = df['close'].rolling(window=100).mean()
    
    return df

def run_simulation(df, buy_rsi, sell_rsi, sl_pct):
    usdt_balance = 10000
    btc_balance = 0
    in_position = False
    entry_price = 0
    trade_count = 0
    
    # Pre-calculate values
    closes = df['close'].values
    rsis = df['rsi_14'].values
    
    for i in range(20, len(df)):
        price = closes[i]
        rsi = rsis[i]
        
        if in_position:
            # Risk Check
            pct_change = (price - entry_price) / entry_price
            
            # SL or Strategy Exit (RSI Overbought)
            if pct_change <= -sl_pct or rsi > sell_rsi:
                usdt_balance = btc_balance * price
                btc_balance = 0
                in_position = False
                trade_count += 1
                
        elif not in_position:
            # Buy Entry (RSI Oversold)
            if rsi < buy_rsi:
                btc_balance = usdt_balance / price
                usdt_balance = 0
                in_position = True
                entry_price = price
                trade_count += 1

    # Final Value
    if in_position:
        final_equity = btc_balance * df.iloc[-1]['close']
    else:
        final_equity = usdt_balance
        
    roi = ((final_equity - 10000) / 10000) * 100
    return roi, trade_count

def optimize():
    print("--- Loading Data ---")
    try:
        df = pd.read_csv('btc_4h_2023.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except:
        print("Error: btc_4h_2023.csv not found.")
        return
        
    print("--- Calculating Indicators ---")
    df = calculate_indicators(df)
    
    # Parameter Grids (Mean Reversion)
    buy_rsis = [25, 30, 35]
    sell_rsis = [65, 70, 75]
    stop_losses = [0.05, 0.10, 100.0] # Added 100.0 as "No Stop" option just in case
    
    best_roi = -9999
    best_params = {}
    
    print("--- Starting Mean Reversion Grid Search ---")
    
    for buy_r in buy_rsis:
        for sell_r in sell_rsis:
            for sl in stop_losses:
                roi, trades = run_simulation(df, buy_r, sell_r, sl)
                
                # print(f"Tested: Buy RSI {buy_r} | Sell RSI {sell_r} | SL {sl*100}% -> ROI: {roi:.2f}% ({trades} trades)")
                
                if roi > best_roi:
                    best_roi = roi
                    best_params = {
                        "BuyRSI": buy_r,
                        "SellRSI": sell_r,
                        "SL": sl,
                        "Trades": trades
                    }
    
    print("-" * 40)
    print(f"🏆 WINNING PARAMETERS (Mean Reversion):")
    print(f"Buy RSI < {best_params['BuyRSI']}")
    print(f"Sell RSI > {best_params['SellRSI']}")
    print(f"Stop Loss: {best_params['SL']*100:.0f}%")
    print(f"Result: {best_roi:.2f}% ROI (Trades: {best_params['Trades']})")
    print("-" * 40)
    
if __name__ == "__main__":
    optimize()
