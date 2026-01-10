import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta

def download_year(year):
    exchange = ccxt.binance()
    symbol = 'BTC/USDT'
    timeframe = '4h'
    
    start_time = datetime(year, 1, 1)
    end_time = datetime(year, 12, 31)
    since = int(start_time.timestamp() * 1000)
    
    print(f"--- Downloading Data for {symbol} ({year}) ---")
    
    all_candles = []
    
    while True:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles: break
                
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            
            if candles[-1][0] >= int(end_time.timestamp() * 1000):
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"Error: {e}")
            break
            
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset=['timestamp']).sort_values(by='timestamp')
    
    filename = f'btc_4h_{year}.csv'
    df.to_csv(filename, index=False)
    print(f"Saved {filename}")

if __name__ == "__main__":
    download_year(2021)
    download_year(2022)
