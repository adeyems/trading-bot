
import pytest
from unittest.mock import patch, MagicMock
import main

@pytest.fixture
def mock_exchange():
    exchange = MagicMock()
    exchange.fetch_ticker.return_value = {'last': 50000.0}
    exchange.fetch_balance.return_value = {'total': {'USDT': 10000.0, 'BTC': 0.0}}
    exchange.create_market_buy_order.return_value = {'id': '123', 'price': 50000.0}
    exchange.create_market_sell_order.return_value = {'id': '124', 'price': 55000.0}
    return exchange

@patch('main.restore_state_from_db')
@patch('main.get_pnl_stats')
@patch('main.send_discord_alert')
@patch('main.get_performance_metrics')
def test_buy_alert_content(mock_metrics, mock_send, mock_stats, mock_state, mock_exchange):
    # Setup
    main.PAPER_MODE = True
    main.paper_balance = {'USDT': 10000.0, 'BTC': 0.0}
    mock_stats.return_value = (0, 0, 0)
    mock_metrics.return_value = (10000.0, 0.0, 0.0) # Equity, Profit, ROI
    
    # Execute BUY
    main.execute_trade(
        exchange=mock_exchange,
        symbol="BTC/USDT",
        signal="BUY",
        price=50000.0,
        reason="Test Buy",
        suppress_alert=False
    )
    
    # Verify Alert was called
    assert mock_send.call_count == 1
    
    # Verify Payloads
    args, _ = mock_send.call_args
    title, description, color, fields = args
    
    print("\n--- BUY ALERT PAYLOAD ---")
    print(f"Title: {title}")
    for f in fields:
        print(f"{f['name']}: {f['value']}")
        
    # Assertions
    assert "ENTRY EXECUTED" in title
    assert color == 0x00FF00 # Green
    
    field_names = [f['name'] for f in fields]
    assert "Symbol" in field_names
    assert "Price" in field_names
    assert "Trade Size" in field_names
    assert "BTC Held" in field_names
    assert "Wallet Value" in field_names # CRITICAL
    
    # Check Wallet Value format
    balance_field = next(f for f in fields if f['name'] == "Wallet Value")
    assert balance_field['value'] == "$10,000.00"

@patch('main.restore_state_from_db')
@patch('main.get_pnl_stats')
@patch('main.send_discord_alert')
@patch('main.get_performance_metrics')
def test_sell_alert_content(mock_metrics, mock_send, mock_stats, mock_state, mock_exchange):
    # Setup
    main.PAPER_MODE = True
    main.paper_balance = {'USDT': 0.0, 'BTC': 0.2} # Holding position
    mock_state.return_value = {
        "status": "IN_POSITION",
        "entry_price": 45000.0,
        "amount": 0.2
    }
    mock_metrics.return_value = (11000.0, 1000.0, 10.0) # Equity $11k, Profit $1k, ROI 10%
    
    # Execute SELL
    main.execute_trade(
        exchange=mock_exchange,
        symbol="BTC/USDT",
        signal="SELL",
        price=55000.0,
        reason="Take Profit",
        suppress_alert=False
    )
    
    # Verify Alert
    args, _ = mock_send.call_args
    title, description, color, fields = args
    
    print("\n--- SELL ALERT PAYLOAD ---")
    print(f"Title: {title}")
    for f in fields:
        print(f"{f['name']}: {f['value']}")
        
    assert "EXIT EXECUTED" in title
    assert color == 0xFFA500 # Orange
    
    field_names = [f['name'] for f in fields]
    assert "Total PnL" in field_names
    assert "Wallet Value" in field_names
    assert "BTC Held" in field_names
    
    pnl_field = next(f for f in fields if f['name'] == "Total PnL")
    assert "+$1,000.00 (+10.00%)" in pnl_field['value']  # Check Profit calc
    # Note: Logic inside execute_trade calculates PnL of *that specific trade* (Profit), 
    # while get_performance_metrics calculates *Total Account PnL*.
    # The field "Total PnL" currently displays the Trade PnL according to main.py logic?
    # Let's check main.py logic: 
    #   pnl_profit = (btc_price - entry_price) * amount 
    #   "Total PnL" field uses `pnl_profit`. So it is TRADE PnL.
    #   Wait, get_performance_metrics returns (equity, profit, roi).
    #   The field uses `pnl_profit` (Trade PnL) for SELL, but `pnl_profit` is 0 for BUY.
    #   Actually, let's verify what the code does.  
    
    # Re-reading main.py logic in test:
    # "Total PnL", value: f"...{pnl_profit}..."
    # For SELL, pnl_profit = (55000 - 45000) * 0.2 = 2000.
    # Wait, my mock says (55000-45000)*0.2 = 2000.
    # Let's check assertions carefully.
