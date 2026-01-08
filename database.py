import os
import dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Load environment variables
dotenv.load_dotenv()

# Get Database URL (Default to a local sqlite file if not set, for safety/testing)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_bot.db")

# Setup SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Trade(Base):
    """
    Trade Model for storing transaction history.
    """
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    side = Column(String)          # BUY or SELL
    price = Column(Float)
    amount = Column(Float)
    profit = Column(Float, nullable=True) # Nullable because a BUY has no realized profit yet
    strategy = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Create tables in the database."""
    try:
        Base.metadata.create_all(bind=engine)
        print(f"Database initialized at {DATABASE_URL}")
def reset_db():
    """Drop and recreate all tables (Fresh Start)."""
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print(f"⚠️  Database Wiped & Recreated at {DATABASE_URL}")
    except Exception as e:
        print(f"Error resetting database: {e}")

def log_trade(trade_data):
    """
    Saves a trade to the database.
    trade_data should be a dict like:
    {
        'symbol': 'BTC/USDT',
        'side': 'BUY',
        'price': 50000.0,
        'amount': 0.001,
        'strategy': 'Mean_Reversion',
        'profit': None 
    }
    """
    session = SessionLocal()
    try:
        trade = Trade(
            symbol=trade_data.get('symbol'),
            side=trade_data.get('side'),
            price=trade_data.get('price'),
            amount=trade_data.get('amount'),
            strategy=trade_data.get('strategy'),
            profit=trade_data.get('profit')
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        # print(f"✅ Trade logged to DB: ID {trade.id}")
        return trade
    except Exception as e:
        print(f"Error logging trade to DB: {e}")
        session.rollback()
    finally:
        session.close()

def get_pnl_stats():
    """
    Calculates statistics using direct SQL queries (efficient).
    Returns (total_pnl, win_rate, total_closed_trades)
    """
    session = SessionLocal()
    try:
        # 1. Total P&L (Sum of profit column)
        total_pnl = session.query(func.sum(Trade.profit)).filter(Trade.profit != None).scalar() or 0.0
        
        # 2. Counts
        total_closed = session.query(func.count(Trade.id)).filter(Trade.profit != None).scalar() or 0
        winning_trades = session.query(func.count(Trade.id)).filter(Trade.profit > 0).scalar() or 0
        
        # 3. Win Rate
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0.0
        
        return total_pnl, win_rate, total_closed
        
    except Exception as e:
        print(f"Error fetching DB stats: {e}")
        return 0.0, 0.0, 0
    finally:
        session.close()

if __name__ == "__main__":
    init_db()
