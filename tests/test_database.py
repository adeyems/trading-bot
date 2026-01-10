import pytest
from database import log_trade, get_pnl_stats, get_latest_trade, Trade

def test_log_trade_and_fetch(db_session):
    # Arrange
    trade_data = {
        "symbol": "BTC/USDT",
        "side": "BUY",
        "price": 50000.0,
        "amount": 1.0,
        "strategy": "Test",
        "profit": None
    }
    
    # Act
    log_trade(trade_data)
    latest = get_latest_trade()
    
    # Assert
    assert latest is not None
    assert latest.symbol == "BTC/USDT"
    assert latest.side == "BUY"
    assert latest.price == 50000.0

def test_pnl_stats_calculation(db_session):
    # Arrange: Log a mix of winning and losing trades
    log_trade({"symbol": "BTC/USDT", "side": "SELL", "price": 50000, "amount": 1, "profit": 100})  # Win
    log_trade({"symbol": "BTC/USDT", "side": "SELL", "price": 50000, "amount": 1, "profit": 50})   # Win
    log_trade({"symbol": "BTC/USDT", "side": "SELL", "price": 50000, "amount": 1, "profit": -30})  # Loss
    log_trade({"symbol": "BTC/USDT", "side": "BUY", "price": 50000, "amount": 1, "profit": None})  # Open (should ignore)

    # Act
    total_pnl, win_rate, total_closed = get_pnl_stats()
    
    # Assert
    assert total_pnl == 120.0  # 100 + 50 - 30
    assert total_closed == 3
    assert win_rate == 66.66666666666666  # 2 wins out of 3 closed

def test_get_latest_trade_persistence(db_session):
    # Arrange
    log_trade({"symbol": "BTC/USDT", "side": "BUY", "price": 100, "amount": 1, "profit": None})
    log_trade({"symbol": "BTC/USDT", "side": "SELL", "price": 110, "amount": 1, "profit": 10})
    
    # Act
    latest = get_latest_trade()
    
    # Assert
    assert latest.side == "SELL"
    assert latest.profit == 10
