import logging
from flask import Blueprint, jsonify, request

from app.services.orientation_service import fetch_url_orientations

orientations_bp = Blueprint("orientations", __name__)


@orientations_bp.route("/api/url-orientations", methods=["POST"])
def get_url_orientations():
    try:
        data = request.get_json() or {}
        urls = data.get("urls", [])
        orientations = fetch_url_orientations(urls)
        return jsonify(orientations)
    except Exception as exc:
        logging.error("Error fetching URL orientations: %s", exc)
        return jsonify({"error": "Could not fetch orientations"}), 500
