import logging
from typing import Any, Dict, Optional

from app.utils.scraper.scraping import scrape_for_new_articles


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


__all__ = ["run_scraping"]
