import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time

# --- Config ---
# Default to the deployed Railway URL
DEFAULT_API_URL = "https://worker-production-5225.up.railway.app"
API_URL = st.sidebar.text_input("Bot API URL", value=DEFAULT_API_URL)

st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")
st.title("🤖 Algo-Trading Command Center")

# --- Helper Functions ---
def fetch_stats():
    try:
        response = requests.get(f"{API_URL}/stats", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        return None

def fetch_trades():
    try:
        response = requests.get(f"{API_URL}/trades", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        return []

def send_command(action):
    try:
        response = requests.post(f"{API_URL}/trade/{action}")
        if response.status_code == 200:
            st.success(f"✅ {action.upper()} Executed Successfully!")
        else:
            st.error(f"❌ Failed: {response.text}")
    except Exception as e:
        st.error(f"Error: {e}")

def update_config(buy_rsi, sell_rsi):
    try:
        payload = {"buy_rsi": buy_rsi, "sell_rsi": sell_rsi}
        response = requests.post(f"{API_URL}/config", json=payload)
        if response.status_code == 200:
            st.sidebar.success("✅ Config Updated!")
        else:
            st.sidebar.error("❌ Update Failed")
    except:
        st.sidebar.error("Connection Error")

# --- Sidebar Controls ---
st.sidebar.header("🕹️ Manual Control")
col1, col2 = st.sidebar.columns(2)
if col1.button("🔴 Force SELL"):
    send_command("sell")
if col2.button("🟢 Force BUY"):
    send_command("buy")

st.sidebar.header("⚙️ Strategy Tuner")
# Fetch current config from stats to set default values
stats = fetch_stats()
if stats and 'config' in stats:
    current_buy = stats['config']['buy_rsi']
    current_sell = stats['config']['sell_rsi']
else:
    current_buy = 25
    current_sell = 65

new_buy = st.sidebar.slider("Buy Threshold (RSI)", 10, 50, current_buy)
new_sell = st.sidebar.slider("Sell Threshold (RSI)", 50, 90, current_sell)

if st.sidebar.button("Update Parameters"):
    update_config(new_buy, new_sell)
    time.sleep(1)
    st.rerun()

# --- Main Dashboard ---
if not stats:
    st.warning("⚠️ Cannot connect to Bot API. Is it running?")
    st.stop()

# 1. Metrics Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("Status", "ONLINE 🟢" if stats else "OFFLINE")
m2.metric("Wallet Balance", f"${stats.get('usdt_balance', 0):,.2f}")
m3.metric("Total P&L", f"${stats.get('total_pnl', 0):.2f}")
m4.metric("Win Rate", stats.get('win_rate', '0%'))

# 2. Charts
st.subheader("Recent Activity")
trades_data = fetch_trades()

if trades_data:
    df = pd.DataFrame(trades_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Create Price Chart
    fig = px.line(df, x='timestamp', y='price', title='Trade Execution Prices', markers=True)
    
    # Color markers by Side
    colors = {'BUY': 'green', 'SELL': 'red'}
    fig.update_traces(marker=dict(size=12, color=[colors.get(x, 'blue') for x in df['side']]))
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Data Table
    st.dataframe(df)
else:
    st.info("No recent trades found.")

# Auto-Refresh
if st.checkbox("Auto-Refresh Data (5s)", value=True):
    time.sleep(5)
    st.rerun()
