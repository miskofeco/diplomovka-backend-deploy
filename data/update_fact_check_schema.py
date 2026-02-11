from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


def ensure_fact_check_schema(engine):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file_path = os.path.join(current_dir, "migrations", "ensure_fact_check_schema.sql")

    with open(sql_file_path, "r", encoding="utf-8") as sql_file:
        sql = sql_file.read()

    with engine.connect() as connection:
        connection.execute(text(sql))
        connection.commit()


if __name__ == "__main__":
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set.")
    engine = create_engine(DB_URL)
    ensure_fact_check_schema(engine)
    print("Fact-check schema ensured.")
