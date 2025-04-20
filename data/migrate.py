from sqlalchemy import text
from db import engine

def run_migration():
    with open('migrations/add_political_orientation.sql', 'r') as f:
        sql = f.read()
        
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()

if __name__ == "__main__":
    run_migration()