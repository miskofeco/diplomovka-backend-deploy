import logging
from flask import Blueprint, jsonify, request

from app.routes.admin_guard import require_processing_admin
from app.services.scraping_service import (
    run_scraping,
    run_scraping_per_source,
    run_scraping_with_fact_check,
)

scraping_bp = Blueprint("scraping", __name__)


@scraping_bp.route("/api/scrape", methods=["POST"])
def scrape_articles():
    guard_response = require_processing_admin()
    if guard_response:
        return guard_response

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


@scraping_bp.route("/api/scrape-per-source", methods=["POST"])
def scrape_articles_per_source():
    guard_response = require_processing_admin()
    if guard_response:
        return guard_response

    try:
        data = request.get_json() or {}
        target_per_source = data.get("target_per_source", 5)
        max_rounds_per_source = data.get("max_rounds_per_source", 5)
        max_articles_per_page = data.get("max_articles_per_page")

        response = run_scraping_per_source(
            target_per_source=target_per_source,
            max_rounds_per_source=max_rounds_per_source,
            max_articles_per_page=max_articles_per_page,
        )
        return jsonify(response)
    except Exception as exc:
        logging.error("Error during per-source scraping: %s", exc, exc_info=True)
        return jsonify({"error": "Scraping failed", "details": str(exc)}), 500


@scraping_bp.route("/api/scrape-with-fact-check", methods=["POST"])
def scrape_articles_with_fact_check():
    guard_response = require_processing_admin()
    if guard_response:
        return guard_response

    try:
        data = request.get_json() or {}
        max_total_articles = data.get("max_total_articles", 3)
        max_articles_per_page = data.get("max_articles_per_page", 3)
        max_facts_per_article = data.get("max_facts_per_article", 5)

        response = run_scraping_with_fact_check(
            max_total_articles=max_total_articles,
            max_articles_per_page=max_articles_per_page,
            max_facts_per_article=max_facts_per_article,
        )
        return jsonify(response)
    except Exception as exc:
        logging.error("Error during scrape + fact-check: %s", exc, exc_info=True)
        return jsonify({"error": "Scraping with fact-check failed", "details": str(exc)}), 500
