import logging
import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from data.db import engine
from .models import Base
from .routes import register_routes

load_dotenv()


def _get_cors_origins():
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return "*"

    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or "*"


def create_app() -> Flask:
    """Application factory that wires up extensions, routes, and database."""
    app = Flask(__name__)
    cors_origins = _get_cors_origins()
    if cors_origins == "*":
        CORS(app)
    else:
        CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    _initialize_database(app)
    register_routes(app)

    return app


def _initialize_database(app: Flask) -> None:
    """Ensure database tables exist before handling requests."""
    try:
        print("Attempting to create database tables if they don't exist...")
        with app.app_context():
            Base.metadata.create_all(bind=engine)
        print("Database tables check/creation complete.")
    except Exception as exc:
        logging.exception("An error occurred during table creation: %s", exc)


__all__ = ["create_app"]
