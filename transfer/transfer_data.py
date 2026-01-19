#!/usr/bin/env python3
"""
PostgreSQL Database Transfer Script
Transfers data from source database to target database for the 3 main tables:
- borders
- hexes  
- hexes_borders
"""

import os
import sys
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_env():
    """Load environment variables from .env file"""
    load_dotenv()
    
    # Source DB connection
    source_config = {
        'host': os.getenv('SOURCE_HOST'),
        'port': os.getenv('SOURCE_PORT', '5432'),
        'database': os.getenv('SOURCE_DB_NAME'),
        'user': os.getenv('SOURCE_USER'),
        'password': os.getenv('SOURCE_PASSWORD')
    }
    
    # Target DB connection
    target_config = {
        'host': os.getenv('TARGET_HOST', 'localhost'),
        'port': os.getenv('TARGET_PORT', '5432'),
        'database': os.getenv('TARGET_DB_NAME'),
        'user': os.getenv('TARGET_USER'),
        'password': os.getenv('TARGET_PASSWORD')
    }
    
    return source_config, target_config

def test_connection(config, db_name):
    """Test database connection"""
    try:
        conn = psycopg2.connect(**config)
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            logger.info(f"Connected to {db_name} database: {version[:50]}...")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to connect to {db_name} database: {e}")
        return False

def get_row_count(conn, table_name):
    """Get row count for a table"""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
        return cur.fetchone()[0]

def transfer_table(source_conn, target_conn, table_name, batch_size=10000):
    """Transfer data from source to target table"""
    logger.info(f"Starting transfer for table: {table_name}")
    
    # Get source row count
    source_count = get_row_count(source_conn, table_name)
    logger.info(f"Source table {table_name} has {source_count:,} rows")
    
    # Clear target table
    with target_conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(sql.Identifier(table_name)))
        target_conn.commit()
    logger.info(f"Cleared target table {table_name}")
    
    # Transfer data in batches
    offset = 0
    total_transferred = 0
    
    with source_conn.cursor(name=f"transfer_{table_name}") as source_cur:
        source_cur.execute(sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table_name)))
        
        while True:
            rows = source_cur.fetchmany(batch_size)
            if not rows:
                break
            
            # Get column names from cursor description
            columns = [desc[0] for desc in source_cur.description]
            
            # Insert into target
            with target_conn.cursor() as target_cur:
                insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table_name),
                    sql.SQL(', ').join(map(sql.Identifier, columns)),
                    sql.SQL(', ').join([sql.Placeholder()] * len(columns))
                )
                
                target_cur.executemany(insert_query, rows)
                target_conn.commit()
            
            transferred = len(rows)
            total_transferred += transferred
            offset += transferred
            
            logger.info(f"Transferred {total_transferred:,}/{source_count:,} rows for {table_name}")
    
    logger.info(f"Completed transfer for {table_name}: {total_transferred:,} rows")
    return total_transferred

def main():
    """Main transfer function"""
    logger.info("Starting database transfer process")
    
    # Load environment
    source_config, target_config = load_env()
    
    # Validate required environment variables
    required_vars = ['SOURCE_HOST', 'SOURCE_DB_NAME', 'SOURCE_USER', 'SOURCE_PASSWORD',
                     'TARGET_DB_NAME', 'TARGET_USER', 'TARGET_PASSWORD']
    
    for var in required_vars:
        if not os.getenv(var):
            logger.error(f"Missing required environment variable: {var}")
            sys.exit(1)
    
    # Test connections
    if not test_connection(source_config, "source"):
        sys.exit(1)
    if not test_connection(target_config, "target"):
        sys.exit(1)
    
    # Connect to databases
    try:
        source_conn = psycopg2.connect(**source_config)
        target_conn = psycopg2.connect(**target_config)
        
        # Tables to transfer (in dependency order)
        tables = ['borders', 'hexes', 'hexes_borders']
        
        total_transferred = 0
        for table in tables:
            try:
                count = transfer_table(source_conn, target_conn, table)
                total_transferred += count
            except Exception as e:
                logger.error(f"Failed to transfer table {table}: {e}")
                sys.exit(1)
        
        logger.info(f"Transfer completed successfully! Total rows transferred: {total_transferred:,}")
        
        # Close connections
        source_conn.close()
        target_conn.close()
        
    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()