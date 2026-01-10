import pytest
import os
import sys

# Ensure the app root is in path
sys.path.append(os.getcwd())

# Force a test database BEFORE importing database module
TEST_DB = "sqlite:///./test_bot.db"
os.environ["DATABASE_URL"] = TEST_DB

from database import init_db, engine, Base, SessionLocal

@pytest.fixture(scope="function")
def db_session():
    """
    Creates a fresh database for each test function.
    """
    # Create tables
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    
    # Teardown
    Base.metadata.drop_all(bind=engine)
