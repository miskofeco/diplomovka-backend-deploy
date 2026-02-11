import logging
from flask import Blueprint, jsonify, request

from app.routes.admin_guard import require_processing_admin
from app.services import article_service, fact_check_service, search_service
from app.services.search_service import (
    EmbeddingGenerationError,
    SearchServiceError,
)

articles_bp = Blueprint("articles", __name__)


@articles_bp.route("/api/articles", methods=["GET"])
def get_articles():
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int)
    try:
        articles = article_service.fetch_articles(limit=limit, offset=offset)
        return jsonify(articles)
    except Exception as exc:  # pragma: no cover - preserves original behaviour
        logging.error("Error fetching articles: %s", exc)
        return (
            jsonify({"error": "Could not fetch articles", "details": str(exc)}),
            500,
        )


@articles_bp.route("/api/articles/search", methods=["GET"])
def search_articles():
    query = request.args.get("q", "")
    advanced = request.args.get("advanced", "false").lower() == "true"

    try:
        articles = search_service.search_articles(query=query, advanced=advanced)
        return jsonify(articles)
    except EmbeddingGenerationError as exc:
        return jsonify({"error": str(exc)}), 500
    except SearchServiceError as exc:
        logging.error("Error searching articles: %s", exc)
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logging.error("Unhandled error searching articles: %s", exc)
        return jsonify({"error": "Search failed"}), 500


@articles_bp.route("/api/articles/<article_id>/similar", methods=["GET"])
def get_similar_articles(article_id):
    try:
        articles = search_service.find_similar_articles(article_id)
        return jsonify(articles)
    except SearchServiceError as exc:
        message = str(exc)
        status = 404 if message == "Article not found" else 500
        return jsonify({"error": message}), status
    except Exception as exc:
        logging.error("Error finding similar articles: %s", exc)
        return jsonify({"error": "Failed to find similar articles"}), 500


@articles_bp.route("/api/articles/<article_slug>/details", methods=["GET"])
def get_article_details(article_slug):
    try:
        article = article_service.get_article_details_by_slug(article_slug)
        if not article:
            logging.warning("Article not found for slug: %s", article_slug)
            return jsonify({"error": "Article not found"}), 404
        logging.info("Found article: ID=%s, Title=%s...", article["id"], article["title"][:50])
        return jsonify(article)
    except Exception as exc:
        logging.error("Error getting article details: %s", exc)
        return jsonify({"error": "Failed to get article details"}), 500


@articles_bp.route("/api/articles/<article_id>/fact-check", methods=["POST"])
def fact_check_article(article_id):
    guard_response = require_processing_admin()
    if guard_response:
        return guard_response

    data = request.get_json() or {}
    max_facts = data.get("max_facts", 5)

    try:
        result = fact_check_service.fact_check_article(article_id, max_facts=max_facts)
        return jsonify(result)
    except fact_check_service.FactCheckServiceError as exc:
        message = str(exc)
        status = 404 if message == "Article not found" else 500
        return jsonify({"error": message}), status
    except Exception as exc:
        logging.error("Error fact-checking article: %s", exc, exc_info=True)
        return jsonify({"error": "Fact-checking failed"}), 500
