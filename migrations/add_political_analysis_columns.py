import os
import sys
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import engine, SessionLocal

def add_political_analysis_columns():
    """Add confidence and reasoning columns to processed_urls table"""
    
    with SessionLocal() as session:
        try:
            # Check if columns already exist
            check_columns_query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'processed_urls' 
                AND column_name IN ('confidence', 'reasoning')
            """
            
            result = session.execute(text(check_columns_query)).fetchall()
            existing_columns = [row[0] for row in result]
            
            # Add confidence column if it doesn't exist
            if 'confidence' not in existing_columns:
                print("Adding confidence column to processed_urls table...")
                session.execute(text("""
                    ALTER TABLE processed_urls 
                    ADD COLUMN confidence REAL DEFAULT 0.0
                """))
            
            # Add reasoning column if it doesn't exist
            if 'reasoning' not in existing_columns:
                print("Adding reasoning column to processed_urls table...")
                session.execute(text("""
                    ALTER TABLE processed_urls 
                    ADD COLUMN reasoning TEXT
                """))
            
            # Update existing records with default values
            print("Updating existing records with default values...")
            session.execute(text("""
                UPDATE processed_urls 
                SET confidence = 0.0, reasoning = 'Not analyzed'
                WHERE confidence IS NULL OR reasoning IS NULL
            """))
            
            session.commit()
            print("Successfully added political analysis columns")
            
        except Exception as e:
            session.rollback()
            print(f"Error adding political analysis columns: {e}")
            raise

if __name__ == "__main__":
    add_political_analysis_columns()