from sqlalchemy import create_engine, text
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
# Load PostgreSQL connection details
DB_URL = os.getenv("DATABASE_URL")

def add_scraped_at_column(engine):
    with engine.connect() as connection:
        print("Connected to DB. Adding column if needed...")
        connection.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMP;
        """))
        print("Column checked/added.")

        print("Updating existing rows...")
        connection.execute(text("""
            UPDATE articles
            SET scraped_at = :now
            WHERE scraped_at IS NULL;
        """), {"now": datetime.now()})
        print("Rows updated.")

def add_political_orientation(engine):
    with engine.connect() as connection:
        print("Adding political orientation columns...")
        with open('backend/data/migrations/add_political_orientation.sql', 'r') as f:
            sql = f.read()
            connection.execute(text(sql))
            connection.commit()
        print("Political orientation columns added.")

# Example of initializing the engine
engine = create_engine(DB_URL)

# Call the function after initializing the engine
if __name__ == "__main__":
    add_scraped_at_column(engine)
    add_political_orientation(engine)
