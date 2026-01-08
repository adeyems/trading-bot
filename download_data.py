import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta

def download_data():
    exchange = ccxt.binance()
    symbol = 'BTC/USDT'
    timeframe = '4h'
    
    # Calculate start time (Specific 2023 Range)
    start_time = datetime(2023, 1, 1)
    end_time = datetime(2023, 12, 31)
    since = int(start_time.timestamp() * 1000)
    
    print(f"--- Downloading Data for {symbol} ({timeframe}) ---")
    print(f"Start Date: {start_time}")
    print(f"End Date: {end_time}")
    
    all_candles = []
    chunk_num = 0
    
    while True:
        try:
            chunk_num += 1
            # Fetch batch of candles
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            
            if not candles:
                print("No more data received. Stopping.")
                break
                
            all_candles.extend(candles)
            
            # Update 'since' to the timestamp of the last candle + 1ms to retrieve next batch
            last_timestamp = candles[-1][0]
            since = last_timestamp + 1
            
            print(f"Fetched chunk {chunk_num} (Last Date: {pd.to_datetime(last_timestamp, unit='ms')})")
            
            # Stop if we've reached the current time (allow a small buffer or just check if last candle is recent)
            if last_timestamp >= int(end_time.timestamp() * 1000):
                break
                
            # Respect rate limits
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
            
    # Process Data
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['timestamp'])
    
    # Sort just in case
    df = df.sort_values(by='timestamp')
    
    filename = 'btc_4h_2023.csv'
    df.to_csv(filename, index=False)
    
    print("-" * 30)
    print(f"Successfully saved {len(df)} rows to {filename}")
    print("-" * 30)

if __name__ == "__main__":
    download_data()
