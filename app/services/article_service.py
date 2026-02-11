import logging
import json
import re
import unicodedata
from typing import Dict, List, Optional

from sqlalchemy import text

from data.db import SessionLocal


def _parse_json_field(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def fetch_articles(limit: Optional[int], offset: Optional[int]) -> List[Dict]:
    """Return paginated list of articles ordered by recency."""
    session = SessionLocal()
    try:
        query = """
            SELECT 
                id, title, intro, summary, url, category, tags, top_image, scraped_at,
                fact_check_results, summary_annotations
            FROM articles 
            ORDER BY scraped_at DESC
        """

        params = {}
        if limit is not None:
            query += " LIMIT :limit"
            params["limit"] = limit
        if offset is not None:
            query += " OFFSET :offset"
            params["offset"] = offset

        result = session.execute(text(query), params)
        return [
            {
                "id": str(row[0]) if row[0] else None,
                "title": row[1],
                "intro": row[2],
                "summary": row[3],
                "url": row[4],
                "category": row[5],
                "tags": row[6],
                "top_image": row[7],
                "scraped_at": row[8].isoformat() if row[8] else None,
                "fact_check_results": _parse_json_field(row[9]),
                "summary_annotations": _parse_json_field(row[10]),
            }
            for row in result.fetchall()
        ]
    except Exception as exc:
        session.rollback()
        logging.error("Error fetching articles: %s", exc)
        raise
    finally:
        session.close()


def get_article_details_by_slug(article_slug: str) -> Optional[Dict]:
    """Return article details that match the provided slug-alike string."""
    session = SessionLocal()
    try:
        query = """
            SELECT id, title, intro, summary, url, category, tags, top_image, scraped_at,
                   fact_check_results, summary_annotations
            FROM articles 
            WHERE LOWER(REPLACE(REPLACE(REPLACE(title, ' ', '-'), '.', ''), ',', '')) LIKE :slug
            LIMIT 1
        """

        slug_pattern = f"%{article_slug.replace('-', '%')}%"
        result = session.execute(text(query), {"slug": slug_pattern}).fetchone()

        if result:
            return _row_to_article_dict(result, article_slug)

        fallback_article = _fallback_match_by_slug(session, article_slug)
        if fallback_article:
            return fallback_article

        return None
    except Exception as exc:
        session.rollback()
        logging.error("Error getting article details: %s", exc)
        raise
    finally:
        session.close()


__all__ = ["fetch_articles", "get_article_details_by_slug"]


def _row_to_article_dict(row, article_slug: str) -> Dict:
    return {
        "id": str(row[0]) if row[0] else None,
        "title": row[1],
        "intro": row[2],
        "summary": row[3],
        "url": row[4],
        "category": row[5],
        "tags": row[6],
        "top_image": row[7],
        "scraped_at": row[8].isoformat() if row[8] else None,
        "fact_check_results": _parse_json_field(row[9]),
        "summary_annotations": _parse_json_field(row[10]),
        "slug": article_slug,
    }


def _fallback_match_by_slug(session, article_slug: str) -> Optional[Dict]:
    """
    Attempt to match article slug by normalising Unicode characters.
    Helps when stored titles contain diacritics that were stripped on the frontend.
    """
    fallback_query = """
        SELECT id, title, intro, summary, url, category, tags, top_image, scraped_at,
               fact_check_results, summary_annotations
        FROM articles
        ORDER BY scraped_at DESC
        LIMIT 1000
    """

    slug_normalised = _normalise_slug(article_slug)

    for row in session.execute(text(fallback_query)):
        title = row[1] or ""
        title_slug = _normalise_slug(_title_to_slug(title))
        if title_slug == slug_normalised:
            return _row_to_article_dict(row, article_slug)

    return None


def _title_to_slug(title: str) -> str:
    slug = re.sub(r"[.,]", "", title)
    slug = slug.strip().replace(" ", "-")
    return slug.lower()


def _normalise_slug(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9-]", "", ascii_only.lower())
