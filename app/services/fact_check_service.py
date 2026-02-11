import json
import logging
from typing import Any, Dict

from sqlalchemy import text

from data.db import SessionLocal
from app.utils.fact_checking import fact_check_summary


class FactCheckServiceError(Exception):
    """Raised when fact-checking fails."""


def fact_check_article(article_id: str, max_facts: int = 5) -> Dict[str, Any]:
    session = SessionLocal()
    try:
        row = session.execute(
            text("SELECT summary FROM articles WHERE id = :article_id"),
            {"article_id": article_id},
        ).fetchone()

        if not row:
            raise FactCheckServiceError("Article not found")

        summary = row[0] or ""
        result = fact_check_summary(summary, max_facts=max_facts)

        session.execute(
            text(
                "UPDATE articles SET fact_check_results = CAST(:results AS JSONB) "
                "WHERE id = :article_id"
            ),
            {"results": json.dumps(result), "article_id": article_id},
        )
        session.commit()
        logging.info(
            "Fact-check saved for article %s: status=%s facts=%s",
            article_id,
            result.get("status"),
            len(result.get("facts", [])),
        )
        return result
    except FactCheckServiceError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logging.error("Fact-checking failed: %s", exc, exc_info=True)
        raise FactCheckServiceError("Fact-checking failed") from exc
    finally:
        session.close()


__all__ = ["fact_check_article", "FactCheckServiceError"]
