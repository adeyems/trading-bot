import ccxt
import time
import requests
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import init_db, log_trade, get_pnl_stats, get_recent_trades
import pandas as pd
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()

# --- Paper Trading Mode ---
PAPER_MODE = True
STOP_LOSS_PCT = 0.10  # 10% (Mean Reversion needs room)
TAKE_PROFIT_PCT = 0.20  # 20%
INITIAL_CAPITAL = 10000 
# Dynamic Strategy Parameters
BUY_RSI_THRESHOLD = 25
SELL_RSI_THRESHOLD = 65

paper_balance = {"USDT": 10000, "BTC": 0}

def print_balance(exchange):
    global paper_balance
    try:
        if PAPER_MODE:
            print("\n--- Paper Balance ---")
            print(f"USDT: {paper_balance['USDT']:.2f}")
            print(f"BTC:  {paper_balance['BTC']:.5f}")
        else:
            balance = exchange.fetch_balance()
            print("\n--- Testnet Balance ---")
            if 'total' in balance:
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
        print(f"Failed to send Discord alert: {e}")

# --- Persistence Helper Functions ---
STATE_FILE = "bot_state.json"
HISTORY_FILE = "trade_history.json"

def save_state(data):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving state: {e}")

def load_state():
    default_state = {"status": "NEUTRAL", "stats": {"wins": 0, "losses": 0, "total_pnl_usdt": 0.0}}
    if not os.path.exists(STATE_FILE):
        return default_state
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            # Ensure stats object exists
            if 'stats' not in data:
                data['stats'] = default_state['stats']
            return data
    except Exception as e:
        print(f"Error loading state: {e}")
        return default_state

def log_trade(entry_price, sell_price, amount):
    try:
        profit = (sell_price - entry_price) * amount
        trade_record = {
            "entry_price": entry_price,
            "sell_price": sell_price,
            "amount": amount,
            "profit_usdt": profit,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                try:
                    history = json.load(f)
                except:
                    history = []
        
        history.append(trade_record)
        
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=4)
            
        print(f"Trade Logged: Profit ${profit:.2f}")
    except Exception as e:
        print(f"Error logging trade: {e}")

def get_dynamic_position_size(usdt_balance, btc_price):
    """
    Calculate dynamic position size based on historical win rate (Kelly Criterion tiers).
    Returns: (btc_amount, tier_name, win_rate_percent)
    """
    try:
        # Logic Update: Fetch stats from state (O(1)) instead of history file
        state = load_state()
        stats = state.get('stats', {"wins": 0, "losses": 0})
        
        wins = stats['wins']
        losses = stats['losses']
        total_trades = wins + losses
        
        if total_trades == 0:
            win_rate = 0.5  # Default
        else:
            win_rate = wins / total_trades
        
        # Determine tier and risk percentage
        if win_rate >= 0.60:
            tier = "Tier 1 (Hot Hand)"
            risk_pct = 0.02  # 2%
        elif win_rate >= 0.50:
            tier = "Tier 2 (Normal)"
            risk_pct = 0.01  # 1%
        else:
            tier = "Tier 3 (Cold)"
            risk_pct = 0.005  # 0.5%
        
        # Calculate position size in USDT
        position_usdt = usdt_balance * risk_pct
        
        # Safety limits
        min_usdt = 10  # Binance minimum
        max_usdt = usdt_balance * 0.05  # 5% cap
        
        position_usdt = max(min_usdt, min(position_usdt, max_usdt))
        
        # Convert to BTC
        btc_amount = position_usdt / btc_price
        
        # Round to appropriate precision (Binance typically uses 5 decimals for BTC)
        btc_amount = round(btc_amount, 5)
        
        win_rate_percent = int(win_rate * 100)
        
        print(f"Calculated Position Size: ${position_usdt:.2f} / {btc_amount:.5f} BTC (Win Rate: {win_rate_percent}% - {tier})")
        
        return btc_amount, tier, win_rate_percent
        
    except Exception as e:
        print(f"Error calculating position size: {e}. Using minimum.")
        return max(10 / btc_price, 0.0001), "Tier 2 (Default)", 50

def execute_trade(exchange, symbol, signal, price, reason=None):
    """
    Executes trade based on signal and balance availability.
    Returns True if trade was executed, False otherwise.
    """
    global paper_balance
    try:
        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        btc_price = ticker['last']
        
        if PAPER_MODE:
            usdt_free = paper_balance['USDT']
            btc_free = paper_balance['BTC']
        else:
            balance = exchange.fetch_balance()
            usdt_free = balance['total'].get('USDT', 0)
            btc_free = balance['total'].get('BTC', 0)
        
        # Dynamic position sizing
        amount, tier, win_rate = get_dynamic_position_size(usdt_free, btc_price)
        
        if signal == 'BUY':
            required_usdt = amount * btc_price
            if usdt_free > required_usdt and usdt_free > 10:
                print(f"Signal: BUY (Price > SMA & RSI < 70) | USDT Free: {usdt_free:.2f}")
                
                if PAPER_MODE:
                    # Simulate trade
                    paper_balance['USDT'] -= required_usdt
                    paper_balance['BTC'] += amount
                    print(f"📝 PAPER TRADE: Bought {amount:.5f} BTC at ${btc_price:,.2f}")
                else:
                    order = exchange.create_market_buy_order(symbol, amount)
                    print(f"BUY Execution: {order['id']} | Fill Price: {order.get('price', 'Market')}")
                
                # Log Trade to DB
                trade_record = {
                    "symbol": symbol,
                    "side": "BUY",
                    "price": btc_price,
                    "amount": amount,
                    "strategy": "Mean_Reversion_4H",
                    "profit": None # Profit is calculated on SELL
                }
                log_trade(trade_record)
                
                # Update State
                current_state = load_state()
                save_state({
                    "status": "IN_POSITION", 
                    "entry_price": btc_price, 
                    "amount": amount, 
                    "stats": current_state.get('stats')
                })
                
                return True
            else:
                print(f"Signal is BUY, but insufficient USDT. Required: ${amount * btc_price:.2f}, Available: ${usdt_free:.2f}")
                return False
                
        elif signal == 'SELL':
            state = load_state()
            if state and state.get('status') == 'IN_POSITION':
                amount = state.get('amount', amount)
                entry_price = state.get('entry_price', btc_price) # Get entry price from state
            else:
                entry_price = btc_price # Fallback if state is missing or not in position
            
            if btc_free >= amount:
                reason_msg = reason if reason else "RSI > 65 or Stop Loss"
                print(f"Signal: SELL ({reason_msg}) | BTC Free: {btc_free:.5f}")
                
                profit = (btc_price - entry_price) * amount # Calculate profit before state reset
                
                if PAPER_MODE:
                    # Simulate trade
                    paper_balance['BTC'] -= amount
                    paper_balance['USDT'] += amount * btc_price
                    print(f"📝 PAPER TRADE: Sold {amount:.5f} BTC at ${btc_price:,.2f}")
                else:
                    order = exchange.create_market_sell_order(symbol, amount)
                    print(f"SELL Execution: {order['id']} | Fill Price: {order.get('price', 'Market')}")
                
                # Log Trade to DB
                trade_record = {
                    "symbol": symbol,
                    "side": "SELL",
                    "price": btc_price,
                    "amount": amount,
                    "strategy": "Mean_Reversion_4H",
                    "profit": profit
                }
                log_trade(trade_record)
                
                # Update State Stats (Keep state stats for quick lookups if needed, but DB is source of truth)
                stats = state.get('stats', {"wins": 0, "losses": 0, "total_pnl_usdt": 0.0})
                stats['total_pnl_usdt'] += profit
                if profit > 0:
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1
                
                # Reset State
                save_state({"status": "NEUTRAL", "stats": stats})
                
                return True
            else:
                print(f"Signal is SELL, but insufficient BTC. Required: {amount:.5f}, Available: {btc_free:.5f}")
                return False
                
        else:
            print("Signal: HOLD (RSI between 25 and 65)")
            return False
            
    except Exception as e:
        print(f"Error executing trade: {e}")
        return False

def check_risk_exits(exchange, symbol, current_price):
    """
    Checks for Stop Loss or Take Profit conditions.
    Forces a SELL if triggered.
    """
    state = load_state()
    if not state or state.get('status') != 'IN_POSITION':
        return None

    entry_price = state.get('entry_price')
    if not entry_price:
        return None

    # Calculate percentage change
    pct_change = (current_price - entry_price) / entry_price
    
    action = None
    log_message = ""
    reason_code = ""

    # Stop Loss Check
    if pct_change <= -STOP_LOSS_PCT:
        log_message = f"🛑 STOP LOSS TRIGGERED: Selling at ${current_price:,.0f} (Loss: {pct_change*100:.1f}%)"
        reason_code = "Stop Loss"
        action = "SELL"
        
    # Take Profit Check
    elif pct_change >= TAKE_PROFIT_PCT:
        log_message = f"🥂 TAKE PROFIT TRIGGERED: Selling at ${current_price:,.0f} (Gain: +{pct_change*100:.1f}%)"
        reason_code = "Take Profit"
        action = "SELL"
        
    if action:
        print(log_message)
        # Force SELL
        executed = execute_trade(exchange, symbol, action, current_price, reason=reason_code)
        if executed:
            print_balance(exchange)
            
            # --- Get Performance Data for Alert ---
            equity, profit, roi = get_performance_metrics(exchange, current_price)
            log_message += f"\n📊 P&L: {'+' if profit >= 0 else ''}${profit:,.2f} ({'+' if roi >= 0 else ''}{roi:.2f}%)"
            
            send_discord_alert(log_message)
            return action
            
    return None

def get_performance_metrics(exchange, current_price=None):
    """
    Returns (equity, profit, roi).
    """
    global paper_balance
    try:
        if current_price is None:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
        
        if PAPER_MODE:
            usdt_bal = paper_balance['USDT']
            btc_bal = paper_balance['BTC']
        else:
            balance = exchange.fetch_balance()
            usdt_bal = balance['total'].get('USDT', 0)
            btc_bal = balance['total'].get('BTC', 0)
            
        equity = usdt_bal + (btc_bal * current_price)
        profit = equity - INITIAL_CAPITAL
        roi = (profit / INITIAL_CAPITAL) * 100
        
        return equity, profit, roi
    except Exception as e:
        print(f"Error calculating metrics: {e}")
        return 0, 0, 0

def log_performance(exchange):
    """
    Calculates and logs the current equity and ROI.
    """
    try:
        equity, profit, roi = get_performance_metrics(exchange)
        print(f"📊 EQUITY: ${equity:,.2f} | P&L: { '+' if profit >= 0 else ''}${profit:,.2f} ({ '+' if roi >= 0 else ''}{roi:.2f}%)")
        
        # Efficiency Check Log (Now using SQL)
        total_pnl, win_rate, total_trades = get_pnl_stats()
        print(f"📊 Efficiency Check: Stats fetched via SQL. Win Rate: {win_rate:.0f}% (Trades: {total_trades}).")
        
    except Exception as e:
        print(f"Error logging performance: {e}")

def run_bot(exchange, last_action, symbol='BTC/USDT'):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fetching data for {symbol} (4h)...")
    
    try:
        # 1. Fetch History
        bars = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # 2. Calculate Indicators
        # RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        last_close = df['close'].iloc[-1]
        last_rsi = df['rsi_14'].iloc[-1]
        
        # --- Risk Management Check ---
        risk_action = check_risk_exits(exchange, symbol, last_close)
        if risk_action:
            return risk_action
        
        # Determine RSI Status
        rsi_status = "Neutral"
        if last_rsi > SELL_RSI_THRESHOLD: rsi_status = "Overbought"
        if last_rsi < BUY_RSI_THRESHOLD: rsi_status = "Oversold"
        
        print(f"Price: {last_close:.2f} | RSI: {last_rsi:.2f} ({rsi_status})")
        
        # 3. Decision Logic (Mean Reversion)
        signal = 'HOLD'
        
        # BUY: Extreme Oversold (Falling Knife)
        if last_rsi < BUY_RSI_THRESHOLD:
            signal = 'BUY'
            
        # SELL: Overbought or Recovered
        elif last_rsi > SELL_RSI_THRESHOLD:
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
                alert_msg = f"💰 {signal} SIGNAL EXECUTED\nPrice: ${last_close:,.2f}\nAmount: 0.001 BTC"
                
                # --- Get Performance Data for Alert ---
                equity, profit, roi = get_performance_metrics(exchange, last_close)
                alert_msg += f"\n📊 P&L: {'+' if profit >= 0 else ''}${profit:,.2f} ({'+' if roi >= 0 else ''}{roi:.2f}%)"
                
                send_discord_alert(alert_msg)
                
                return signal
        
        # If HOLD or Trade Failed, keep state
        print_balance(exchange)
        return last_action

    except Exception as e:
        print(f"An error occurred: {e}")
        send_discord_alert("⚠️ CRITICAL ERROR\nBot is restarting...")
        return last_action

def start_trading_loop():
    global paper_balance
    
    # Initialize Database
    init_db()
    
    if PAPER_MODE:
        print("\n⚠️ RUNNING IN PAPER MODE (Real Data / Fake Money)")
        print(f"Starting Paper Balance: ${paper_balance['USDT']:.2f} USDT")
        
        # Initialize exchange for public data only (no API keys needed)
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        print("--- Using Binance Production API (Public Data Only) ---")
    else:
        print("Starting Crypto Bot in [TESTNET] mode...")
        
        api_key = os.getenv('BINANCE_TESTNET_KEY')
        secret_key = os.getenv('BINANCE_TESTNET_SECRET')

        if not api_key or not secret_key:
            print("Error: BINANCE_TESTNET_KEY or BINANCE_TESTNET_SECRET not found in .env")
            return

        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        exchange.set_sandbox_mode(True)
        print("--- Binance Sandbox Mode Enabled ---")
    
    # Verify connection
    try:
        exchange.load_markets()
        print("Connected to Binance successfully!")
        if not PAPER_MODE:
            send_discord_alert("🚀 Strategy: Mean Reversion (4H) | Buy: RSI < 25 | SL: 10%")
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print("Detecting initial state...")
    try:
        saved_state = load_state()
        last_action = None
        
        if PAPER_MODE:
            usdt_total = paper_balance['USDT']
            btc_total = paper_balance['BTC']
            btc_price = exchange.fetch_ticker('BTC/USDT')['last']
            btc_value_in_usdt = btc_total * btc_price
        else:
            balance = exchange.fetch_balance()
            usdt_total = balance['total'].get('USDT', 0)
            btc_total = balance['total'].get('BTC', 0)
            btc_value_in_usdt = btc_total * exchange.fetch_ticker('BTC/USDT')['last']

        if saved_state and saved_state.get('status') == 'IN_POSITION':
            last_action = 'BUY'
            entry_price = saved_state.get('entry_price', 0)
            saved_amount = saved_state.get('amount', 0)
            
            print(f"🔄 Restored State: Holding BTC (Entry: ${entry_price:,.2f})")
            
            # Hydrate Paper Wallet from saved state
            if PAPER_MODE and saved_amount > 0:
                paper_balance['BTC'] = saved_amount
                paper_balance['USDT'] = 10000 - (entry_price * saved_amount)
                print(f"🔄 Hydrated Paper Wallet: BTC set to {saved_amount:.5f}")
                btc_total = paper_balance['BTC']  # Update for consistency check
            
            # Consistency Check (skip for paper mode since we just hydrated)
            if not PAPER_MODE and btc_total < 0.0005: 
                print("⚠️ CRITICAL WARNING: State says IN_POSITION but Wallet has no BTC!")
                
        else:
            # File says NEUTRAL or doesn't exist. Check Wallet for "Orphans"
            last_action = 'SELL'
            if btc_value_in_usdt > 20: # If we have significant BTC > $20
                print(f"⚠️ State Mismatch: Found orphan BTC (${btc_value_in_usdt:.2f}) in wallet but State File was NEUTRAL/Missing.")
                last_action = 'BUY' # Assume we are invested to be safe
                save_state({
                    "status": "IN_POSITION", 
                    "entry_price": exchange.fetch_ticker('BTC/USDT')['last'], # Best guess
                    "amount": btc_total, 
                    "note": "Recovered from orphan state"
                })
            else:
                 print("State is NEUTRAL. Starting fresh.")
                 save_state({"status": "NEUTRAL"})
        
        print(f"Initial Logic State: {last_action} | Balance: ${usdt_total:.2f} USDT / ${btc_value_in_usdt:.2f} BTC")
        
    except Exception as e:
        print(f"Error detecting initial state: {e}")
        last_action = 'SELL'

    print("Starting Trading Loop (Interval: 10s)... Press Ctrl+C to stop.")
    
    loop_count = 0
    while True:
        loop_count += 1
        last_action = run_bot(exchange, last_action)
        
        # Log performance every 360 loops (approx 1 hour at 10s interval)
        if loop_count % 360 == 0:
            log_performance(exchange)
            
        time.sleep(10)

# --- FastAPI Endpoints ---

@app.get("/")
def read_root():
    return {
        "status": "online",
        "paper_mode": PAPER_MODE,
        "balance": paper_balance if PAPER_MODE else "Testnet (Hidden)"
    }

@app.get("/trades")
def read_trades():
    return get_recent_trades(limit=10)

@app.get("/stats")
def read_stats():
    total_pnl, win_rate, total_trades = get_pnl_stats()
    
    # Get current wallet
    usdt = 0
    btc = 0
    if PAPER_MODE:
        usdt = paper_balance['USDT']
        btc = paper_balance['BTC']
        
    return {
        "status": "running",
        "total_pnl": total_pnl,
        "win_rate": f"{win_rate:.2f}%",
        "total_trades": total_trades,
        "usdt_balance": usdt,
        "btc_balance": btc,
        "config": {
            "buy_rsi": BUY_RSI_THRESHOLD,
            "sell_rsi": SELL_RSI_THRESHOLD
        }
    }

class ConfigUpdate(BaseModel):
    buy_rsi: int
    sell_rsi: int

@app.post("/config")
def update_config(config: ConfigUpdate):
    global BUY_RSI_THRESHOLD, SELL_RSI_THRESHOLD
    BUY_RSI_THRESHOLD = config.buy_rsi
    SELL_RSI_THRESHOLD = config.sell_rsi
    return {"message": "Configuration updated", "config": config}

@app.post("/trade/{action}")
def manual_trade(action: str):
    action = action.upper()
    if action not in ['BUY', 'SELL']:
        raise HTTPException(status_code=400, detail="Invalid action. Use BUY or SELL.")
        
    # We need to fetch current price to execute
    try:
        if PAPER_MODE:
             # Just init a public exchange instance for price check if using production api
             # But main() initializes 'exchange' locally. We need access to 'exchange'.
             # For simplicity, we create a temporary exchange instance here since it's just one call.
             temp_exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
             ticker = temp_exchange.fetch_ticker('BTC/USDT')
             price = ticker['last']
             
             success = execute_trade(temp_exchange, 'BTC/USDT', action, price, reason="Manual Override")
             if success:
                 return {"message": f"Manual {action} executed successfully"}
             else:
                 raise HTTPException(status_code=400, detail="Trade failed (Insufficient balance or error)")
        else:
             # In Testnet mode, we need keys. 
             # Refactoring to make 'exchange' global would be best, but for now:
             api_key = os.getenv('BINANCE_TESTNET_KEY')
             secret_key = os.getenv('BINANCE_TESTNET_SECRET')
             temp_exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
             })
             temp_exchange.set_sandbox_mode(True)
             
             ticker = temp_exchange.fetch_ticker('BTC/USDT')
             price = ticker['last']
             
             success = execute_trade(temp_exchange, 'BTC/USDT', action, price, reason="Manual Override")
             if success:
                 return {"message": f"Manual {action} executed successfully"}
             else:
                 raise HTTPException(status_code=400, detail="Trade failed")
                 
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
def startup_event():
    print("Starting Trading Bot in Background Thread...")
    t = threading.Thread(target=start_trading_loop, daemon=True)
    t.start()
    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
