import os
import sys
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import engine, SessionLocal

def add_orientation_column():
    """Add orientation column to processed_urls table and set default values"""
    
    with SessionLocal() as session:
        try:
            # Check if column already exists
            check_column_query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'processed_urls' 
                AND column_name = 'orientation'
            """
            
            result = session.execute(text(check_column_query)).fetchone()
            
            if result:
                print("Orientation column already exists")
                return
            
            # Add the column
            print("Adding orientation column to processed_urls table...")
            alter_query = """
                ALTER TABLE processed_urls 
                ADD COLUMN orientation VARCHAR DEFAULT 'neutral'
            """
            session.execute(text(alter_query))
            
            # Update all existing records to have 'neutral' orientation
            print("Updating existing records to have 'neutral' orientation...")
            update_query = """
                UPDATE processed_urls 
                SET orientation = 'neutral' 
                WHERE orientation IS NULL
            """
            result = session.execute(text(update_query))
            
            session.commit()
            print(f"Successfully added orientation column and updated {result.rowcount} existing records")
            
        except Exception as e:
            session.rollback()
            print(f"Error adding orientation column: {e}")
            raise

if __name__ == "__main__":
    add_orientation_column()