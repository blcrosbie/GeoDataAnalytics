"""
Database configuration for GeoDataAnalytics test suite
"""

import os
from typing import Optional
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DatabaseConfig:
    """Database configuration class"""
    
    def __init__(self):
        self.host = os.getenv('POSTGRES_HOST', 'localhost')
        self.port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.database = os.getenv('POSTGRES_DB', 'geodata_analytics')
        self.user = os.getenv('POSTGRES_USER', 'postgres')
        self.password = os.getenv('POSTGRES_PASSWORD', 'postgres')
        self.environment = os.getenv('ENVIRONMENT', 'development')
    
    @property
    def connection_string(self) -> str:
        """Get database connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def test_connection_string(self) -> str:
        """Get test database connection string"""
        test_db_url = os.getenv('TEST_DATABASE_URL')
        if test_db_url:
            return test_db_url
        
        # Default test database configuration
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}_test"
    
    def create_engine(self, test_mode: bool = False):
        """Create SQLAlchemy engine"""
        connection_string = self.test_connection_string if test_mode else self.connection_string
        
        engine_kwargs = {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
        }
        
        if self.environment == 'production':
            engine_kwargs.update({
                'pool_size': 20,
                'max_overflow': 30,
                'pool_timeout': 30,
            })
        else:
            engine_kwargs.update({
                'pool_size': 5,
                'max_overflow': 10,
            })
        
        return create_engine(connection_string, **engine_kwargs)

# Global database configuration instance
db_config = DatabaseConfig()

# SQLAlchemy components
Base = declarative_base()
metadata = MetaData()

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_config.create_engine())
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_config.create_engine(test_mode=True))

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_test_db():
    """Get test database session"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    """Initialize database with required schemas"""
    engine = db_config.create_engine()
    
    # Create schemas if they don't exist
    with engine.connect() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS test_framework")
        conn.execute("CREATE SCHEMA IF NOT EXISTS test_data")
        conn.execute("CREATE SCHEMA IF NOT EXISTS test_results")
        conn.commit()
    
    return engine

class TestDatabaseManager:
    """Manager for test database operations"""
    
    def __init__(self):
        self.engine = db_config.create_engine(test_mode=True)
        self.session = TestSessionLocal()
    
    def setup_test_database(self):
        """Set up test database with required schemas and data"""
        # Create schemas
        with self.engine.connect() as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS test_framework")
            conn.execute("CREATE SCHEMA IF NOT EXISTS test_data")
            conn.execute("CREATE SCHEMA IF NOT EXISTS test_results")
            conn.execute("DROP TABLE IF EXISTS test_framework.test_execution_log CASCADE")
            conn.execute("DROP TABLE IF EXISTS test_results.test_results CASCADE")
            conn.commit()
        
        # Run initialization SQL
        init_sql_path = os.path.join(os.path.dirname(__file__), '..', 'docker', 'postgres', 'init.sql')
        if os.path.exists(init_sql_path):
            with open(init_sql_path, 'r') as f:
                init_sql = f.read()
            
            with self.engine.connect() as conn:
                conn.execute(init_sql)
                conn.commit()
    
    def cleanup_test_database(self):
        """Clean up test database after tests"""
        with self.engine.connect() as conn:
            conn.execute("DROP SCHEMA IF EXISTS test_framework CASCADE")
            conn.execute("DROP SCHEMA IF EXISTS test_data CASCADE")
            conn.execute("DROP SCHEMA IF EXISTS test_results CASCADE")
            conn.commit()
    
    def close(self):
        """Close database connections"""
        self.session.close()
        self.engine.dispose()