import ccxt
import time
import requests
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import init_db, log_trade, get_pnl_stats, get_recent_trades, get_latest_trade
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
BOT_PAUSED = False
CURRENT_RSI = 0.0


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
# Note: JSON state removed in favor of Database Persistence

def restore_state_from_db():
    try:
        total_pnl, win_rate, total_trades = get_pnl_stats()
        latest_trade = get_latest_trade()
        
        # Default State
        status = "NEUTRAL"
        entry_price = 0.0
        amount = 0.0
        
        # Check if we are currently holding a position
        if latest_trade and latest_trade.side == 'BUY' and latest_trade.profit is None:
            status = "IN_POSITION"
            entry_price = latest_trade.price
            amount = latest_trade.amount
            print(f"🔄 Restored State: IN_POSITION (Entry: ${entry_price:,.2f}, Amount: {amount:.5f})")
        else:
            print("🔄 Restored State: NEUTRAL (No open positions found in DB)")
            
        return {
            "status": status,
            "entry_price": entry_price,
            "amount": amount,
            "stats": {
                "total_pnl_usdt": total_pnl,
                "win_rate": win_rate,
                "total_trades": total_trades
            }
        }
    except Exception as e:
        print(f"Error restoring state: {e}")
        return {"status": "NEUTRAL", "entry_price": 0, "amount": 0, "stats": {}}

def get_dynamic_position_size(usdt_balance, btc_price):
    """
    Calculate dynamic position size based on historical win rate (Kelly Criterion tiers).
    Returns: (btc_amount, tier_name, win_rate_percent)
    """
    try:
        # Use DB stats instead of JSON
        total_pnl, win_rate, total_trades = get_pnl_stats()
        
        wins = int(win_rate/100 * total_trades) # Approx
        
        # Determine tier and risk percentage
        
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
                
                return True
            else:
                print(f"Signal is BUY, but insufficient USDT. Required: ${amount * btc_price:.2f}, Available: ${usdt_free:.2f}")
                return False
                
        elif signal == 'SELL':
            # Check DB state for position details
            state = restore_state_from_db()
            if state and state.get('status') == 'IN_POSITION':
                amount = state.get('amount', amount)
                entry_price = state.get('entry_price', btc_price) 
            else:
                entry_price = btc_price 
            
            if btc_free >= amount:
                reason_msg = reason if reason else "RSI > 65 or Stop Loss"
                print(f"Signal: SELL ({reason_msg}) | BTC Free: {btc_free:.5f}")
                
                profit = (btc_price - entry_price) * amount 
                
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
                
                return True
            else:
                print(f"Signal is SELL, but insufficient BTC. Required: {amount:.5f}, Available: {btc_free:.5f}")
                return False
                
        else:
            print(f"Signal: HOLD (RSI between {BUY_RSI_THRESHOLD} and {SELL_RSI_THRESHOLD})")
            return False
            
    except Exception as e:
        print(f"Error executing trade: {e}")
        return False

def check_risk_exits(exchange, symbol, current_price):
    """
    # Checks for Stop Loss or Take Profit conditions.
    # Forces a SELL if triggered.
    """
    state = restore_state_from_db()
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
        
        # Update Global RSI for dashboard
        global CURRENT_RSI
        CURRENT_RSI = last_rsi
        
        # --- Check Pause ---
        if BOT_PAUSED:
            print(f"⏸️ BOT PAUSED. RSI: {last_rsi:.2f}. Standing by...")
            return last_action

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

    print("Detecting initial state from Database...")
    try:
        saved_state = restore_state_from_db()
        last_action = None
        
        # Reconstruct Paper Balance from DB History
        if PAPER_MODE:
             total_pnl = saved_state['stats'].get('total_pnl_usdt', 0.0)
             
             if saved_state['status'] == 'IN_POSITION':
                 # If in position, we hold BTC
                 held_amount = saved_state['amount']
                 entry_price = saved_state['entry_price']
                 
                 paper_balance['BTC'] = held_amount
                 # USDT is Initial + Realized PnL (excluding current trade) - Cost of current trade
                 # Actually, total_pnl from DB is ONLY realized profit.
                 # So Balance = 10000 + total_pnl - (entry_price * held_amount)
                 paper_balance['USDT'] = INITIAL_CAPITAL + total_pnl - (entry_price * held_amount)
                 
                 last_action = 'BUY'
                 print(f"🔄 Restored Position: {held_amount:.5f} BTC @ ${entry_price:,.2f}")
             else:
                 # Neutral
                 paper_balance['BTC'] = 0
                 paper_balance['USDT'] = INITIAL_CAPITAL + total_pnl
                 last_action = 'SELL'
                 print(f"🔄 Restored Neutral: ${paper_balance['USDT']:,.2f} USDT")

        if not PAPER_MODE:
             # Logic for Testnet state matching (omitted for brevity, relying on wallet)
             pass
        
        btc_value_in_usdt = paper_balance['BTC'] * exchange.fetch_ticker('BTC/USDT')['last']
        print(f"Initial Logic State: {last_action} | Balance: ${paper_balance['USDT']:.2f} USDT / ${btc_value_in_usdt:.2f} BTC")
        
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
        "status": "paused" if BOT_PAUSED else "running",
        "total_pnl": total_pnl,
        "win_rate": f"{win_rate:.2f}%",
        "total_trades": total_trades,
        "usdt_balance": usdt,
        "btc_balance": btc,
        "current_rsi": CURRENT_RSI,
        "config": {
            "buy_rsi": BUY_RSI_THRESHOLD,
            "sell_rsi": SELL_RSI_THRESHOLD,
            "stop_loss": STOP_LOSS_PCT,
            "take_profit": TAKE_PROFIT_PCT
        }
    }

class ConfigUpdate(BaseModel):
    buy_rsi: int
    sell_rsi: int
    stop_loss: float
    take_profit: float

@app.post("/config")
def update_config(config: ConfigUpdate):
    global BUY_RSI_THRESHOLD, SELL_RSI_THRESHOLD, STOP_LOSS_PCT, TAKE_PROFIT_PCT
    BUY_RSI_THRESHOLD = config.buy_rsi
    SELL_RSI_THRESHOLD = config.sell_rsi
    STOP_LOSS_PCT = config.stop_loss
    TAKE_PROFIT_PCT = config.take_profit
    return {"message": "Configuration updated", "config": config}

@app.post("/control/{command}")
def control_bot(command: str):
    global BOT_PAUSED
    command = command.lower()
    if command == "pause":
        BOT_PAUSED = True
        return {"status": "paused"}
    elif command == "resume":
        BOT_PAUSED = False
        return {"status": "running"}
    else:
        raise HTTPException(status_code=400, detail="Invalid command. Use pause or resume.")

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
