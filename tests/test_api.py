import pytest
from fastapi.testclient import TestClient
from main import app, BUY_RSI_THRESHOLD

client = TestClient(app)

def test_read_stats(db_session):
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "usdt_balance" in data
    assert "current_rsi" in data
    assert "status" in data

def test_update_config():
    payload = {
        "buy_rsi": 30,
        "sell_rsi": 70,
        "stop_loss": 0.05,
        "take_profit": 0.15
    }
    response = client.post("/config", json=payload)
    assert response.status_code == 200
    
    # Verify change reflected in stats
    stats_response = client.get("/stats")
    config = stats_response.json()['config']
    assert config['buy_rsi'] == 30
    assert config['stop_loss'] == 0.05

def test_control_bot():
    # Pause
    response = client.post("/control/pause")
    assert response.status_code == 200
    assert response.json()['status'] == "paused"
    
    # Verify status
    stats = client.get("/stats").json()
    assert stats['status'] == "paused"
    
    # Resume
    response = client.post("/control/resume")
    assert response.status_code == 200
    assert response.json()['status'] == "running"
