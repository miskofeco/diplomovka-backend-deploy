import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()


def _get_database_url() -> str:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    # SQLAlchemy expects postgresql://, some platforms still provide postgres://.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _get_connect_args(database_url: str) -> dict:
    connect_args: dict = {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
        "keepalives": 1,
        "keepalives_idle": int(os.getenv("DB_KEEPALIVES_IDLE_SECONDS", "30")),
        "keepalives_interval": int(os.getenv("DB_KEEPALIVES_INTERVAL_SECONDS", "10")),
        "keepalives_count": int(os.getenv("DB_KEEPALIVES_COUNT", "5")),
    }

    # Respect explicit URL/env configuration first.
    if "sslmode=" in database_url:
        return connect_args

    ssl_mode = (os.getenv("DB_SSLMODE") or "").strip()
    if ssl_mode:
        connect_args["sslmode"] = ssl_mode
    elif "render.com" in database_url:
        # Safer default for hosted Postgres when URL does not specify sslmode.
        connect_args["sslmode"] = "prefer"

    return connect_args


DB_URL = _get_database_url()
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "180")),
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_POOL_MAX_OVERFLOW", "5")),
    connect_args=_get_connect_args(DB_URL),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
