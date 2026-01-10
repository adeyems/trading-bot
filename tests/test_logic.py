import pytest
from unittest.mock import patch
from main import get_dynamic_position_size, check_risk_exits
from database import log_trade
import main

@pytest.fixture(autouse=True)
def mock_dependencies():
    with patch('main.send_discord_alert') as mock_alert, \
         patch('main.get_performance_metrics') as mock_metrics:
        # Default mock returns
        mock_metrics.return_value = (10500.0, 500.0, 5.0)
        yield

def test_dynamic_position_size_tiers(db_session):
    # Case 1: No history (Default 50% win rate -> Normal Tier)
    amount, tier, win_rate = get_dynamic_position_size(10000, 50000)
    assert tier == "Tier 2 (Normal)"
    assert amount == (10000 * 0.01) / 50000 # 1% risk

    # Case 2: Hot Hand (>60% WR)
    log_trade({"symbol": "BTC", "side": "SELL", "price": 0, "amount": 0, "profit": 10}) # Win
    log_trade({"symbol": "BTC", "side": "SELL", "price": 0, "amount": 0, "profit": 10}) # Win
    # 2 wins / 2 total = 100% WR
    
    amount, tier, win_rate = get_dynamic_position_size(10000, 50000)
    assert tier == "Tier 1 (Hot Hand)"
    assert amount == (10000 * 0.02) / 50000 # 2% risk

def test_check_risk_exits(db_session):
    class MockExchange:
        def fetch_ticker(self, symbol):
            return {'last': 44000.0 if symbol == "BTC/USDT" else 0}
        def fetch_balance(self):
            return {'total': {'USDT': 10000, 'BTC': 1.0}}
        def create_market_sell_order(self, symbol, amount):
            print("MOCK SELL ORDER EXECUTED")
            return {'id': 'mock_order_id', 'price': 44000}

    # Use patch to ensure strict mode separation
    with patch("main.PAPER_MODE", False):
        # Needs to be IN_POSITION based on DB
        # Setup: Log a BUY so the bot thinks it has a position to sell
        log_trade({"symbol": "BTC/USDT", "side": "BUY", "price": 50000, "amount": 1, "profit": None})
        
        # 1. Stop Loss Hit (Price drops 10%)
        # Entry: 50000. SL @ 10% = 45000.
        # Current Price: 44000 (Below SL)
        # check_risk_exits -> calls execute_trade -> calls MockExchange
        action = check_risk_exits(MockExchange(), "BTC/USDT", 44000)
        
        assert action == "SELL"
