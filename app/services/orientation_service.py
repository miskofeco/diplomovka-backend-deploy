import logging
from typing import Dict, List

from sqlalchemy import text

from data.db import SessionLocal


def fetch_url_orientations(urls: List[str]) -> Dict[str, Dict]:
    """Return stored political orientation metadata for the given URLs."""
    if not urls:
        return {}

    session = SessionLocal()
    try:
        placeholders = ",".join([f":url{i}" for i in range(len(urls))])
        query = f"""
            SELECT url, orientation, confidence, reasoning
            FROM processed_urls 
            WHERE url IN ({placeholders})
        """

        params = {f"url{i}": url for i, url in enumerate(urls)}
        result = session.execute(text(query), params)

        orientations: Dict[str, Dict] = {}
        for row in result.fetchall():
            orientations[row[0]] = {
                "orientation": row[1] or "neutral",
                "confidence": float(row[2]) if row[2] is not None else 0.0,
                "reasoning": row[3] or "",
            }

        return orientations
    except Exception as exc:
        session.rollback()
        logging.error("Error fetching URL orientations: %s", exc)
        raise
    finally:
        session.close()


__all__ = ["fetch_url_orientations"]
