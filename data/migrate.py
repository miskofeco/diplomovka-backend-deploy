from sqlalchemy import text
from db import engine
import os

def run_migration():
    # Získame cestu k adresáru, kde sa nachádza tento skript
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Vytvoríme správnu cestu k SQL súboru
    sql_file_path = os.path.join(current_dir, 'migrations', 'add_fact_check_columns.sql')
    
    print(f"Attempting to read migration file from: {sql_file_path}")
    
    # Načítajte a spustite novú migráciu
    with open(sql_file_path, 'r') as f:
        sql = f.read()
        
    with engine.connect() as conn:
        print("Executing migration...")
        conn.execute(text(sql))
        conn.commit()
        print("Migration completed successfully.")

def update_political_orientation_column(engine):
    with engine.connect() as connection:
        print("Updating political_orientation column type...")
        connection.execute(text("""
            ALTER TABLE articles 
            ALTER COLUMN political_orientation TYPE JSONB 
            USING CASE 
                WHEN political_orientation IS NULL THEN NULL
                WHEN political_orientation ~ '^[a-z-]+$' THEN 
                    json_build_object('orientation', political_orientation)::jsonb
                ELSE 
                    '{"orientation": "neutral"}'::jsonb
            END;
        """))
        connection.commit()
        print("Political orientation column updated to JSONB type.")

if __name__ == "__main__":
    run_migration()
    update_political_orientation_column(engine)
