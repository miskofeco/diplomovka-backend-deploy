import logging
from flask import Blueprint, jsonify, request

from app.services.scraping_service import run_scraping

scraping_bp = Blueprint("scraping", __name__)


@scraping_bp.route("/api/scrape", methods=["POST"])
def scrape_articles():
    try:
        data = request.get_json() or {}
        max_articles_per_page = data.get("max_articles_per_page", 3)
        max_total_articles = data.get("max_total_articles")

        response = run_scraping(
            max_articles_per_page=max_articles_per_page,
            max_total_articles=max_total_articles,
        )
        return jsonify(response)
    except Exception as exc:
        logging.error("Error during scraping: %s", exc, exc_info=True)
        return jsonify({"error": "Scraping failed", "details": str(exc)}), 500
