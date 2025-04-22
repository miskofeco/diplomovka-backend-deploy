from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def add_fact_check_columns(engine):
    with engine.connect() as connection:
        print("Adding fact check columns...")
        connection.execute(text("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS fact_check_results JSONB DEFAULT '{"facts": [], "summary": ""}'::jsonb,
            ADD COLUMN IF NOT EXISTS summary_annotations JSONB DEFAULT '{"text": "", "annotations": []}'::jsonb;
        """))
        connection.commit()
        print("Fact check columns added successfully.")

if __name__ == "__main__":
    engine = create_engine(DB_URL)
    add_fact_check_columns(engine)