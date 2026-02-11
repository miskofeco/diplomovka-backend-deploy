import hmac
import os

from flask import jsonify, request

ADMIN_TOKEN_ENV_NAME = "PROCESSING_ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "X-Processing-Token"


def _extract_admin_token() -> str:
    bearer = request.headers.get("Authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()

    return request.headers.get(ADMIN_TOKEN_HEADER, "").strip()


def require_processing_admin():
    expected_token = os.getenv(ADMIN_TOKEN_ENV_NAME, "").strip()
    if not expected_token:
        return (
            jsonify(
                {
                    "error": (
                        f"{ADMIN_TOKEN_ENV_NAME} is not configured. "
                        "Processing endpoints are disabled."
                    )
                }
            ),
            503,
        )

    provided_token = _extract_admin_token()
    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 403

    return None

