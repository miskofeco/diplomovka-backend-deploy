import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from data.db import SessionLocal
from app.services.fact_check_service import fact_check_article, FactCheckServiceError
from app.utils.scraper.scraping import scrape_for_new_articles, scrape_single_landing_page
from app.utils.scraper.constants import LANDING_PAGES
from app.utils.scraper.threading_utils import ThreadSafeCounter


def _collect_processed_urls(scrape_payload: Dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for page_result in scrape_payload.get("details", []):
        if not isinstance(page_result, dict):
            continue
        for raw_url in page_result.get("processed_article_urls", []) or []:
            url = str(raw_url or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def _resolve_article_ids_by_urls(urls: list[str], limit: int) -> list[str]:
    if not urls:
        return []

    session = SessionLocal()
    try:
        article_ids: list[str] = []
        seen_ids: set[str] = set()

        for url in urls:
            row = session.execute(
                text(
                    """
                    SELECT id
                    FROM articles
                    WHERE :url = ANY(url)
                    ORDER BY scraped_at DESC
                    LIMIT 1
                    """
                ),
                {"url": url},
            ).fetchone()

            if not row:
                continue

            article_id = str(row[0])
            if article_id in seen_ids:
                continue

            seen_ids.add(article_id)
            article_ids.append(article_id)

            if len(article_ids) >= limit:
                break

        return article_ids
    finally:
        session.close()


def _resolve_article_ids_since(started_at: datetime, limit: int) -> list[str]:
    session = SessionLocal()
    try:
        rows = session.execute(
            text(
                """
                SELECT id
                FROM articles
                WHERE scraped_at >= :started_at
                ORDER BY scraped_at DESC
                LIMIT :limit
                """
            ),
            {"started_at": started_at, "limit": limit},
        ).fetchall()
        return [str(row[0]) for row in rows]
    finally:
        session.close()


def run_scraping(max_articles_per_page: int = 3, max_total_articles: Optional[int] = None) -> Dict[str, Any]:
    """Trigger parallel scraping workflow and summarise the outcome."""
    logging.info(
        "Starting scraping request: %s per page, max total: %s",
        max_articles_per_page,
        max_total_articles,
    )

    results = scrape_for_new_articles(
        max_articles_per_page=max_articles_per_page,
        max_total_articles=max_total_articles,
    )

    return {
        "message": "Parallel scraping completed successfully",
        "summary": {
            "articles_processed": results["total_processed"],
            "articles_found": results["total_found"],
            "errors": results["total_errors"],
            "landing_pages_scraped": len(results["results_by_page"]),
        },
        "details": results["results_by_page"],
    }


def run_scraping_per_source(
    target_per_source: int = 5,
    max_rounds_per_source: int = 5,
    max_articles_per_page: Optional[int] = None,
) -> Dict[str, Any]:
    """Scrape until each landing page processes target_per_source articles or rounds exhausted."""
    if max_articles_per_page is None:
        max_articles_per_page = target_per_source

    results_by_page = []
    total_processed = 0
    total_found = 0
    total_errors = 0

    for page in LANDING_PAGES:
        processed_for_page = 0
        found_for_page = 0
        errors_for_page = []

        for _round in range(max_rounds_per_source):
            counter = ThreadSafeCounter()
            result = scrape_single_landing_page(
                page_config=page,
                max_articles_per_page=max_articles_per_page,
                global_counter=counter,
                max_total_articles=None,
            )

            processed_for_page += result.get("articles_processed", 0)
            found_for_page += result.get("articles_found", 0)
            errors_for_page.extend(result.get("errors", []))

            if result.get("articles_processed", 0) == 0:
                # No progress this round; avoid infinite retries.
                break
            if processed_for_page >= target_per_source:
                break

        total_processed += processed_for_page
        total_found += found_for_page
        total_errors += len(errors_for_page)
        results_by_page.append(
            {
                "landing_url": page["url"],
                "articles_processed": processed_for_page,
                "articles_found": found_for_page,
                "errors": errors_for_page,
            }
        )

    return {
        "message": "Per-source scraping completed",
        "summary": {
            "articles_processed": total_processed,
            "articles_found": total_found,
            "errors": total_errors,
            "landing_pages_scraped": len(results_by_page),
            "target_per_source": target_per_source,
        },
        "details": results_by_page,
    }


def run_scraping_with_fact_check(
    max_total_articles: int = 3,
    max_articles_per_page: int = 3,
    max_facts_per_article: int = 5,
) -> Dict[str, Any]:
    """Run scraping with overall limit, then fact-check processed articles from this run."""
    if max_total_articles <= 0:
        max_total_articles = 1

    session = SessionLocal()
    try:
        started_at = session.execute(text("SELECT CURRENT_TIMESTAMP")).scalar()
    finally:
        session.close()

    if not started_at:
        started_at = datetime.utcnow()

    scrape_payload = run_scraping(
        max_articles_per_page=max_articles_per_page,
        max_total_articles=max_total_articles,
    )

    processed_urls = _collect_processed_urls(scrape_payload)
    processed_article_ids = _resolve_article_ids_by_urls(
        urls=processed_urls,
        limit=max_total_articles,
    )
    if not processed_article_ids:
        # Fallback for older payloads or unusual URL matching edge-cases.
        processed_article_ids = _resolve_article_ids_since(
            started_at=started_at,
            limit=max_total_articles,
        )

    fact_check_results = []
    fact_check_errors = []

    logging.info(
        "Fact-check pipeline selected %s article(s) from %s processed URL(s).",
        len(processed_article_ids),
        len(processed_urls),
    )

    for article_id in processed_article_ids:
        try:
            result = fact_check_article(article_id, max_facts=max_facts_per_article)
            fact_check_results.append(
                {
                    "article_id": article_id,
                    "status": result.get("status"),
                    "facts_count": len(result.get("facts", [])),
                }
            )
        except FactCheckServiceError as exc:
            fact_check_errors.append(
                {
                    "article_id": article_id,
                    "error": str(exc),
                }
            )
        except Exception as exc:  # pragma: no cover
            logging.error("Unexpected fact-check failure for %s: %s", article_id, exc, exc_info=True)
            fact_check_errors.append(
                {
                    "article_id": article_id,
                    "error": "Unexpected fact-check failure",
                }
            )

    return {
        "message": "Scraping with fact-check completed",
        "summary": scrape_payload.get("summary", {}),
        "details": scrape_payload.get("details", []),
        "fact_check": {
            "selected_article_ids": processed_article_ids,
            "processed_urls_count": len(processed_urls),
            "processed_count": len(fact_check_results),
            "error_count": len(fact_check_errors),
            "results": fact_check_results,
            "errors": fact_check_errors,
        },
    }


__all__ = ["run_scraping", "run_scraping_per_source", "run_scraping_with_fact_check"]
