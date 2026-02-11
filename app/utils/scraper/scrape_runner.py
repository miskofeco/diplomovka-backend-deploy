import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.db import SessionLocal

from .article_parser import get_landing_page_links, parse_article
from .article_processing import process_new_article
from .constants import LANDING_PAGES
from .db_utils import (
    _reserve_url_for_processing,
    get_processed_urls,
    mark_url_as_processed,
    mark_url_processed,
)
from .logging_utils import logger, log_article_step
from .threading_utils import ThreadSafeCounter
from .url_utils import canonicalize_url


def scrape_single_landing_page(
    page_config: dict,
    max_articles_per_page: int,
    global_counter: ThreadSafeCounter,
    max_total_articles: int | None = None,
):
    """
    Scrape a single landing page and process its articles.
    This function will be run in parallel for each landing page.
    """
    landing_url = page_config["url"]
    patterns = page_config["patterns"]
    thread_id = threading.current_thread().name

    logger.info("[%s] Starting scraping for: %s", thread_id, landing_url)

    session = SessionLocal()
    processed_urls = get_processed_urls(session)
    processed_canonicals = {canonicalize_url(url) for url in processed_urls}

    page_results = {
        "landing_url": landing_url,
        "articles_processed": 0,
        "articles_found": 0,
        "errors": [],
        "processed_article_urls": [],
    }

    try:
        current_links = get_landing_page_links(landing_url, patterns)
        new_links = []
        seen_canonicals: set[str] = set()

        for link in current_links:
            canonical_link = canonicalize_url(link)
            if (
                link in processed_urls
                or canonical_link in processed_canonicals
                or canonical_link in seen_canonicals
            ):
                continue
            new_links.append(link)
            if canonical_link:
                seen_canonicals.add(canonical_link)

        page_results["articles_found"] = len(new_links)
        logger.info("[%s] Found %s new articles on %s", thread_id, len(new_links), landing_url)

        page_count = 0

        for link in new_links:
            canonical_link = canonicalize_url(link)
            if page_count >= max_articles_per_page:
                logger.info("[%s] Reached maximum of %s articles for %s", thread_id, max_articles_per_page, landing_url)
                break

            if max_total_articles is not None and global_counter.value >= max_total_articles:
                logger.info("[%s] Global maximum of %s articles reached", thread_id, max_total_articles)
                break

            try:
                if not _reserve_url_for_processing(link, canonical_link):
                    log_article_step(
                        None,
                        link,
                        "URL už je spracovaná alebo čaká na spracovanie, preskakujem duplicitu",
                    )
                    continue

                article_data = parse_article(link)
                if not article_data:
                    logger.warning("[%s] Failed to parse article at %s", thread_id, link)
                    mark_url_as_processed(
                        url=link,
                        orientation="neutral",
                        confidence=0.0,
                        reasoning="Článok sa nepodarilo stiahnuť alebo parsovať",
                        canonical_url=canonical_link,
                    )
                    continue

                log_article_step(article_data.get("title"), link, "Scraped article")

                text_content = article_data.get("text", "").strip()
                if text_content and text_content.lower() != "no content":
                    persisted = process_new_article(article_data)

                    if persisted:
                        total_processed = global_counter.increment()
                        page_count += 1
                        page_results["articles_processed"] += 1
                        for candidate_url in (link, canonical_link):
                            if candidate_url and candidate_url not in page_results["processed_article_urls"]:
                                page_results["processed_article_urls"].append(candidate_url)

                        logger.info(
                            "[%s] Article processed: %s... (Total: %s)",
                            thread_id,
                            article_data["title"][:50],
                            total_processed,
                        )
                    else:
                        logger.info(
                            "[%s] Article skipped by guardrails: %s",
                            thread_id,
                            link,
                        )
                else:
                    log_article_step(
                        article_data.get("title"),
                        link,
                        "No valid text detected, skipping",
                        level=logging.WARNING,
                    )
                    mark_url_as_processed(
                        url=link,
                        orientation="neutral",
                        confidence=0.0,
                        reasoning="Článok neobsahuje validný text",
                        canonical_url=canonical_link,
                    )
                    logger.info("[%s] Article from %s has no valid text, skipping", thread_id, link)

                mark_url_processed(session, link, canonical_url=canonical_link)

                time.sleep(0.5)

            except Exception as exc:
                error_msg = f"Error processing article {link}: {str(exc)}"
                logger.error("[%s] %s", thread_id, error_msg)
                page_results["errors"].append(error_msg)

                try:
                    mark_url_processed(session, link, canonical_url=canonical_link)
                except Exception as mark_error:
                    logger.error("[%s] Error marking URL as processed: %s", thread_id, mark_error)

                continue

    except Exception as exc:
        error_msg = f"Error scraping landing page {landing_url}: {str(exc)}"
        logger.error("[%s] %s", thread_id, error_msg)
        page_results["errors"].append(error_msg)

    finally:
        session.close()

    logger.info("[%s] Completed scraping %s: %s articles processed", thread_id, landing_url, page_results["articles_processed"])
    return page_results


def scrape_for_new_articles(max_articles_per_page: int = 3, max_total_articles: int | None = None):
    """
    Scrape articles from all landing pages in parallel.
    Each landing page will be processed in a separate thread.
    """
    logger.info(
        "Starting parallel scraping: %s articles per page, max total: %s",
        max_articles_per_page,
        max_total_articles,
    )

    global_counter = ThreadSafeCounter()

    all_results = []

    max_workers = min(len(LANDING_PAGES), 5)

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Scraper") as executor:
        future_to_page = {
            executor.submit(
                scrape_single_landing_page,
                page,
                max_articles_per_page,
                global_counter,
                max_total_articles,
            ): page for page in LANDING_PAGES
        }

        for future in as_completed(future_to_page):
            page_config = future_to_page[future]

            try:
                result = future.result()
                all_results.append(result)

                logger.info(
                    "Completed scraping %s: %s processed, %s found, %s errors",
                    result["landing_url"],
                    result["articles_processed"],
                    result["articles_found"],
                    len(result["errors"]),
                )

            except Exception as exc:
                error_msg = f"Landing page {page_config['url']} generated an exception: {exc}"
                logger.error(error_msg)
                all_results.append({
                    "landing_url": page_config['url'],
                    "articles_processed": 0,
                    "articles_found": 0,
                    "errors": [error_msg]
                })

    total_processed = sum(result['articles_processed'] for result in all_results)
    total_found = sum(result['articles_found'] for result in all_results)
    total_errors = sum(len(result['errors']) for result in all_results)

    logger.info("Parallel scraping completed:")
    logger.info("  - Total articles found: %s", total_found)
    logger.info("  - Total articles processed: %s", total_processed)
    logger.info("  - Total errors: %s", total_errors)

    for result in all_results:
        logger.info(
            "  - %s: %s/%s processed",
            result['landing_url'],
            result['articles_processed'],
            result['articles_found'],
        )
        if result['errors']:
            for error in result['errors']:
                logger.warning("    Error: %s", error)

    return {
        "total_processed": total_processed,
        "total_found": total_found,
        "total_errors": total_errors,
        "results_by_page": all_results
    }
