from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
# Load PostgreSQL connection details
DB_URL = os.getenv("DATABASE_URL")

# Create database engine
engine = create_engine(DB_URL)

# Create a session factory
SessionLocal = sessionmaker(bind=engine)