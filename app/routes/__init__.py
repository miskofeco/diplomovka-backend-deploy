from flask import Flask

from .articles import articles_bp
from .orientations import orientations_bp
from .scraping import scraping_bp


def register_routes(app: Flask) -> None:
    """Attach all API blueprints to the Flask application."""
    app.register_blueprint(articles_bp)
    app.register_blueprint(scraping_bp)
    app.register_blueprint(orientations_bp)


__all__ = ["register_routes"]
