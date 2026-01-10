# 🤖 Hybrid Algo-Trading Bot (Mean Reversion)

A professional-grade crypto trading bot that trades **BTC/USDT** on the **Binance Testnet** using a Mean Reversion strategy (RSI + Kelly Criterion). The system features a persistent cloud backend (Railway) and a local command center (Streamlit).

## ✨ Features

-   **Backend (Railway)**:
    -   Runs 24/7 in the cloud.
    -   **Persistence**: PostgreSQL database ensures zero data loss on restarts.
    -   **Strategy**: Buy Oversold (RSI < 25) / Sell Overbought (RSI > 65).
    -   **Risk Management**: Dynamic Position Sizing (Kelly Criterion), Stop Loss (10%), Take Profit (20%).
-   **Frontend (Dashboard)**:
    -   Local Streamlit app acts as a remote control.
    -   View Live PnL, Trade History, and Active Positions.
    -   **Manual Override**: Force BUY/SELL buttons.
    -   **Dynamic Config**: Adjust RSI/Risk parameters on the fly.
-   **Alerts**:
    -   **Premium Discord Embeds**: Rich color-coded cards for Entry, Exit, and Profit.

## 🚀 How to Run

### 1. The Backend (Cloud)
This runs automatically on Railway.
-   **Logs**: Check Railway Dashboard.
-   **Status**: Online 24/7.

### 2. The Dashboard (Command Center) 🖥️
Run this on your local machine to control the bot.

```bash
# 1. Install dependencies (if new)
pip install -r requirements.txt

# 2. Launch Dashboard
python3 -m streamlit run dashboard.py
```
*The dashboard will automatically connect to the Production Railway API.*

### 3. Manual Control
-   **Force BUY/SELL**: Click the buttons in the sidebar to execute immediate market orders.
-   **Pause Bot**: Stop auto-trading during high volatility.

## 🛠Configuration

### Environment Variables (.env / Railway)
| Variable | Description |
| :--- | :--- |
| `BINANCE_TESTNET_KEY` | Your Binance Testnet API Key |
| `BINANCE_TESTNET_SECRET` | Your Binance Testnet Secret |
| `DATABASE_URL` | PostgreSQL Connection String |
| `DISCORD_WEBHOOK_URL` | Discord Webhook for Alerts |
| `PAPER_MODE` | Set to `True` for paper trading, `False` for Testnet |

## 📊 Strategy Details
-   **Timeframe**: 4 Hour
-   **RSI Period**: 14
-   **Entry**: RSI < 25 (Extreme Fear)
-   **Exit**: RSI > 65 (Greed) OR Stop Loss hit.

## Disclaimer
This software is for educational purposes only. Use at your own risk.
