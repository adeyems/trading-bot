# Binance SMA Trading Bot

A Python-based crypto trading bot that trades **BTC/USDT** on the **Binance Testnet** using a Simple Moving Average (SMA-20) crossover strategy.

## Features

-   **Trend Analysis**: Calculates the 20-period SMA on 1-hour candles to determine BULLISH/BEARISH trends.
-   **Automated Trading**: Executes Market Buy/Sell orders based on trend indicators.
-   **Testnet Ready**: Configured by default for Binance Sandbox Mode (safe testing).
-   **Smart Execution**:
    -   **Balance Checks**: Prevents orders if funds are insufficient.
    -   **State Machine**: Prevents duplicate trades (e.g., won't sell if already in a cash position).
    -   **Startup Detection**: Automatically detects if you are currently "Invested" (BTC) or "Cash" (USDT) at startup.
-   **Deployment Ready**: Includes `Procfile` for easy cloud deployment (Render, Railway, etc.).

## Prerequisites

-   Python 3.9+
-   A Binance Testnet Account (API Key & Secret)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd trading-bot
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment:**
    Create a `.env` file in the root directory and add your keys:
    ```env
    BINANCE_TESTNET_KEY=your_api_key_here
    BINANCE_TESTNET_SECRET=your_secret_key_here
    ```

## Usage

### Run Locally

Start the bot:
```bash
python main.py
```
The bot will run in a continuous loop (every 10 seconds), logging price analysis and trade execution to the console.

### Deploy to Cloud

This project is configured for PaaS deployment.

1.  **Push to GitHub**.
2.  **Connect to Provider** (e.g., Render, Railway).
3.  **Set Environment Variables** (`BINANCE_TESTNET_KEY`, `BINANCE_TESTNET_SECRET`) in your dashboard.
4.  **Deploy**. The `Procfile` will automatically start the worker process.

## Strategy

-   **Timeframe**: 1 Hour
-   **Indicator**: SMA-20
-   **Logic**:
    -   **BUY**: Close Price > SMA-20 (and currently in Cash position).
    -   **SELL**: Close Price < SMA-20 (and currently in Invested position).

## Disclaimer

This software is for educational purposes only. Do not use with real funds until you have fully verified the strategy and code integrity. Use at your own risk.
