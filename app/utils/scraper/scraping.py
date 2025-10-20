import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from newspaper import Article
from sqlalchemy import text

from app.utils.political_analysis import analyze_political_orientation
from app.utils.similarity import find_similar_article
from app.utils.summary import process_article, update_article_summary, verify_article_update
from app.utils.vectorstore import store_embedding
from data.db import SessionLocal

logger = logging.getLogger("app.scraper")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

DEFAULT_TOP_IMAGE = "/no_image_press.png"


def canonicalize_url(url: str) -> str:
    """Return canonical form of URL without query parameters or fragments."""
    try:
        parts = urlsplit(url.strip())
        if not parts.scheme or not parts.netloc:
            return url

        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()

        path = parts.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/") or "/"

        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return url


def _article_label(title: str | None, url: str | None) -> str:
    safe_title = (title or "Bez názvu").strip()
    safe_url = (url or "bez-url").strip()
    return f"{safe_title} ({safe_url})"


def log_article_step(title: str | None, url: str | None, message: str, level: int = logging.INFO) -> None:
    logger.log(level, "%s - %s", message, _article_label(title, url))

# Thread-safe counter for tracking total articles processed
class ThreadSafeCounter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def increment(self):
        with self._lock:
            self._value += 1
            return self._value

    @property
    def value(self):
        with self._lock:
            return self._value

# ------------------------ CONFIG ------------------------ #
# Hospodarske noviny, hlavnespravy.sk, trend.sk, noviny.sk, topky.sk, novycas.sk
LANDING_PAGES = [
    {
        "url": "https://pravda.sk/",
        "patterns": ["/clanok/"]
    },
    {
        "url": "https://www.aktuality.sk",
        "patterns": ["/clanok/"]
    },
    {
        "url": "https://domov.sme.sk/",
        "patterns": ["/c/"]
    },
    {
        "url": "https://topky.sk",
        "patterns": ["/cl/"]
    },
    {
        "url": "https://teraz.sk/",
        "patterns": ["/slovensko/","/veda/","/sport/","/zahranicie/","/kultura/","/ekonomika/","/krimi/","/regiony/","/slovensko/","/obce/","/zdravie/"]
    },
    {
        "url": "https://hnonline.sk/",
        "patterns": ["/ekonomika/","/svet/","/slovensko/"]
    }
]

MEDIA_SOURCES = {
    "pravda.sk": {
        "name": "Pravda",
        "orientation": "center-left",
        "logo": "https://path-to-pravda-logo.svg",
        "domain": "pravda.sk"
    },
    "dennikn.sk": {
        "name": "Denník N",
        "orientation": "center-left",
        "logo": "https://path-to-dennikn-logo.svg",
        "domain": "dennikn.sk"
    },
    "aktuality.sk": {
        "name": "Aktuality",
        "orientation": "neutral",
        "logo": "https://path-to-aktuality-logo.svg",
        "domain": "aktuality.sk"
    },
    "sme.sk": {
        "name": "SME",
        "orientation": "center",
        "logo": "https://path-to-sme-logo.svg",
        "domain": "sme.sk"
    },
    "hnonline.sk": {
        "name": "Hospodárske noviny",
        "orientation": "center-right",
        "logo": "https://path-to-hnonline-logo.svg",
        "domain": "hnonline.sk"
    },
    "postoj.sk": {
        "name": "Postoj",
        "orientation": "right",
        "logo": "https://path-to-postoj-logo.svg",
        "domain": "postoj.sk"
    }
}

def get_source_info(url: str) -> dict:
    """Get source information for a given URL"""
    try:
        domain = url.split("//")[-1].split("/")[0]
        return MEDIA_SOURCES.get(domain, {
            "name": domain,
            "orientation": "neutral",
            "logo": None,
            "domain": domain
        })
    except Exception:
        return None

def get_processed_urls(session):
    """Get set of all processed URLs from database"""
    result = session.execute(text("SELECT url FROM processed_urls"))
    return {row[0] for row in result.fetchall()}

def mark_url_processed(session, url, canonical_url: str | None = None):
    urls_to_mark = {url}

    canonical_from_url = canonicalize_url(url)
    if canonical_from_url and canonical_from_url != url:
        urls_to_mark.add(canonical_from_url)

    if canonical_url:
        normalized = canonicalize_url(canonical_url)
        if normalized:
            urls_to_mark.add(normalized)

    for value in urls_to_mark:
        session.execute(
            text("INSERT INTO processed_urls (url) VALUES (:url) ON CONFLICT DO NOTHING"),
            {"url": value}
        )
    session.commit()

def is_url_processed(url: str) -> bool:
    """Check if URL has already been processed (including canonical variants)."""
    session = SessionLocal()
    try:
        urls_to_check = {url}
        canonical = canonicalize_url(url)
        if canonical:
            urls_to_check.add(canonical)

        result = session.execute(
            text("SELECT 1 FROM processed_urls WHERE url = ANY(:urls)"),
            {"urls": list(urls_to_check)}
        ).fetchone()
        return result is not None
    finally:
        session.close()


def _reserve_url_for_processing(url: str, canonical_url: str | None) -> bool:
    """Reserve a URL in processed_urls to avoid concurrent duplicate processing."""
    if not url:
        return False

    session = SessionLocal()
    try:
        primary = canonical_url or url
        urls_to_reserve = []
        if primary:
            urls_to_reserve.append(primary)
        if url and url != primary:
            urls_to_reserve.append(url)

        reserved = False
        for index, value in enumerate(urls_to_reserve):
            result = session.execute(
                text(
                    """
                    INSERT INTO processed_urls (url, orientation, confidence, reasoning)
                    VALUES (:url, :orientation, 0.0, :reasoning)
                    ON CONFLICT (url) DO NOTHING
                    RETURNING url
                    """
                ),
                {
                    "url": value,
                    "orientation": "pending",
                    "reasoning": "Rezervované na spracovanie článku",
                },
            ).fetchone()

            if index == 0:
                # Primary URL (canonical or original) determines reservation success
                if result is None:
                    session.rollback()
                    return False
                reserved = True

        session.commit()
        return reserved
    except Exception as exc:
        session.rollback()
        logger.error("Failed to reserve URL %s: %s", url, exc)
        return False
    finally:
        session.close()

def mark_url_as_processed(
    url: str,
    orientation: str = 'neutral',
    confidence: float = 0.0,
    reasoning: str = "",
    canonical_url: str | None = None
):
    """Mark URL as processed with political orientation analysis"""
    session = SessionLocal()
    try:
        # Ensure reasoning is never None or empty
        if not reasoning or reasoning.strip() == "":
            if confidence == 0.0:
                reasoning = "URL označené ako spracované bez analýzy orientácie"
            else:
                reasoning = f"Orientácia: {orientation}, istota: {confidence:.1f}"
        urls_to_mark = {url}
        canonical_from_url = canonicalize_url(url)
        if canonical_from_url and canonical_from_url != url:
            urls_to_mark.add(canonical_from_url)
        if canonical_url:
            normalized = canonicalize_url(canonical_url)
            if normalized:
                urls_to_mark.add(normalized)

        for target_url in urls_to_mark:
            existing = session.execute(
                text("SELECT url, orientation, confidence, reasoning FROM processed_urls WHERE url = :url"),
                {"url": target_url}
            ).fetchone()

            if existing:
                existing_confidence = existing[2] or 0.0
                if confidence > existing_confidence:
                    logger.info(
                        "Updating URL with better analysis: %s (confidence: %.2f -> %.2f)",
                        target_url,
                        existing_confidence,
                        confidence,
                    )
                    session.execute(
                        text("""
                        UPDATE processed_urls 
                        SET orientation = :orientation,
                            confidence = :confidence,
                            reasoning = :reasoning,
                            scraped_at = CURRENT_TIMESTAMP
                        WHERE url = :url
                        """),
                        {
                            "url": target_url, 
                            "orientation": orientation,
                            "confidence": confidence,
                            "reasoning": reasoning
                        }
                    )
                else:
                    logger.info("URL už bolo spracované s rovnakou alebo vyššou istotou: %s", target_url)
            else:
                session.execute(
                    text("""
                    INSERT INTO processed_urls (url, orientation, confidence, reasoning) 
                    VALUES (:url, :orientation, :confidence, :reasoning)
                    """),
                    {
                        "url": target_url, 
                        "orientation": orientation,
                        "confidence": confidence,
                        "reasoning": reasoning
                    }
                )
                logger.info(
                    "New URL processed: %s - %s (confidence: %.2f)",
                    target_url,
                    orientation,
                    confidence,
                )

        session.commit()
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error marking URL as processed: {e}")
    finally:
        session.close()

def get_landing_page_links(url, patterns):
    """
    Fetches the landing page and finds links that match the given URL patterns.
    Returns a list of absolute URLs.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching landing page {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    all_links = []

    # Identify domain for absolute URL creation
    scheme_and_domain = url.split("//")[0] + "//" + url.split("//")[1].split("/")[0]

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Check if this link matches our patterns
        if any(pattern in href for pattern in patterns):
            # Convert to absolute if needed
            full_url = scheme_and_domain + href if href.startswith("/") else href
            if full_url not in all_links:
                all_links.append(full_url)

    logger.info(f"Found {len(all_links)} potential article links on {url}")
    return all_links

def parse_article(url):
    """
    Parses a single article using newspaper3k and returns a dict of extracted data.
    """
    try:
        article = Article(url)
        article.download()
        article.parse()

        top_image = article.top_image or ""
        # Extract video URLs if any
        videos = article.movies or []

        return {
            "url": url,
            "title": article.title or "No Title",
            "publish_date": (
                article.publish_date.strftime("%Y-%m-%d %H:%M:%S")
                if article.publish_date
                else "Unknown Date"
            ),
            "text": article.text or "No Content",
            "top_image": top_image,
            "videos": videos,  # Added video links
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        logger.error(f"Failed to parse article at {url}: {e}")
        return None

def process_new_article(article_data: dict):
    try:
        article_text = article_data.get("text", "").strip()
        article_url = article_data.get("url", "")
        canonical_url = canonicalize_url(article_url) if article_url else article_url
        raw_title = article_data.get("title", "")
        article_title = raw_title.strip() if raw_title else None

        if not _reserve_url_for_processing(article_url, canonical_url):
            log_article_step(
                article_title,
                article_url,
                "URL už je spracovaná alebo čaká na spracovanie, preskakujem duplicitu",
                level=logging.INFO,
            )
            return

        if not article_text:
            log_article_step(article_title, article_url, "Empty article text, skipping", level=logging.WARNING)
            mark_url_as_processed(
                url=article_url,
                orientation="neutral",
                confidence=0.0,
                reasoning="Článok nemá obsah na analýzu",
                canonical_url=canonical_url
            )
            return

        log_article_step(article_title, article_url, "Starting article processing")

        # Analyze political orientation FIRST
        log_article_step(article_title, article_url, "Analyzing political orientation")
        try:
            political_analysis = analyze_political_orientation(article_text)
            log_article_step(
                article_title,
                article_url,
                f"Political orientation analyzed - {political_analysis['orientation']} ({political_analysis['confidence']:.2f})",
            )
        except Exception as analysis_error:
            logger.error("Political analysis failed for %s: %s", article_url, analysis_error)
            political_analysis = {
                "orientation": "neutral",
                "confidence": 0.0,
                "reasoning": f"Chyba pri analýze orientácie: {str(analysis_error)[:50]}"
            }
            log_article_step(
                article_title,
                article_url,
                "Political orientation fallback applied",
                level=logging.WARNING,
            )

        log_article_step(article_title, article_url, "Generating structured article data")
        llm_data = process_article(
            article_text,
            log_step=lambda message: log_article_step(article_title, article_url, message),
        )
        article_summary = (llm_data.get("summary", "") or "").strip()
        if not article_summary:
            logger.warning(
                "Verified summary generation returned empty result for %s; using fallback truncation.",
                article_url,
            )
            article_summary = article_text[:2000]
            log_article_step(
                article_title,
                article_url,
                "Summary generation empty, using truncated article text",
                level=logging.WARNING,
            )

        with SessionLocal() as session:
            try:
                existing_article_row = session.execute(
                    text(
                        """
                        SELECT id, title, intro, summary, url
                        FROM articles
                        WHERE (:article_url <> '' AND :article_url = ANY(url))
                           OR (:canonical_url <> '' AND :canonical_url = ANY(url))
                        LIMIT 1
                        """
                    ),
                    {
                        "article_url": article_url or "",
                        "canonical_url": canonical_url or "",
                    },
                ).fetchone()

                # Check for similar articles
                log_article_step(article_title, article_url, "Finding similar article...")
                if existing_article_row:
                    log_article_step(
                        article_title,
                        article_url,
                        "Found existing article priamo podľa URL, aktualizujem záznam",
                    )
                    similar_article = {
                        "id": str(existing_article_row[0]),
                        "title": existing_article_row[1],
                        "intro": existing_article_row[2],
                        "summary": existing_article_row[3],
                        "url": existing_article_row[4],
                    }
                    similarity_result = {"article": similar_article, "score": 1.0}
                else:
                    similarity_result = find_similar_article(
                        article_summary=article_summary,
                        article_text=article_text,
                        article_title=llm_data.get("title") or article_title,
                        article_tags=llm_data.get("tags", []),
                    )
                    similar_article = similarity_result.get("article")

                if similar_article:
                    log_article_step(
                        article_title,
                        article_url,
                        f"Found similar article - Score {similarity_result.get('score', 0.0):.2f} - {similar_article.get('title') or 'Bez názvu'}",
                    )
                    metrics = similarity_result.get("metrics", {}).get("best_match")
                    if metrics:
                        logger.debug(
                            "Similarity metrics for %s: %s",
                            _article_label(article_title, article_url),
                            metrics,
                        )

                    # Update existing article
                    log_article_step(article_title, article_url, "Updating existing article summary")
                    new_urls = []
                    for candidate in (article_url, canonical_url):
                        if candidate and candidate not in new_urls:
                            new_urls.append(candidate)

                    updated_data = update_article_summary(
                        existing_summary=similar_article["summary"],
                        new_article_text=article_text,
                        title=similar_article.get("title")
                    )

                    # Verify update
                    log_article_step(article_title, article_url, "Verifying updated article summary")
                    verified_update = verify_article_update(
                        original_summary=similar_article["summary"],
                        new_article_text=article_text,
                        updated_data=updated_data,
                        title=similar_article.get("title")
                    )

                    # Update article with new timestamp
                    current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    session.execute(
                        text("""
                        UPDATE articles 
                        SET 
                            intro = :intro,
                            summary = :summary,
                            url = (
                                SELECT ARRAY(
                                    SELECT DISTINCT val
                                    FROM unnest(url || :new_urls) AS val
                                )
                            ),
                            scraped_at = :scraped_at
                        WHERE id = :article_id
                        """),
                        {
                            "intro": verified_update["intro"],
                            "summary": verified_update["summary"],
                            "new_urls": new_urls if new_urls else similar_article.get("url", []),
                            "scraped_at": current_timestamp,
                            "article_id": similar_article["id"]
                        }
                    )

                    # Update embedding
                    log_article_step(article_title, article_url, "Refreshing summary embedding")
                    store_embedding(similar_article["id"], verified_update["summary"])

                    session.commit()
                    log_article_step(
                        article_title,
                        article_url,
                        f"Existing article updated - {similar_article['id']}",
                    )
                else:
                    best_title = similarity_result.get("candidate_title") or "no candidate"
                    log_article_step(
                        article_title,
                        article_url,
                        f"Found no similar article - Best score {similarity_result.get('score', 0.0):.2f} - {best_title}",
                    )
                    candidate_metrics = similarity_result.get("metrics", {}).get("closest_candidate")
                    if candidate_metrics:
                        logger.debug(
                            "Closest article metrics for %s: %s",
                            _article_label(article_title, article_url),
                            candidate_metrics,
                        )
                    log_article_step(article_title, article_url, "Persisting new article with verified data")
                    # Insert new article
                    unique_urls = []
                    for candidate in (article_url, canonical_url):
                        if candidate and candidate not in unique_urls:
                            unique_urls.append(candidate)
                    if not unique_urls and article_url:
                        unique_urls.append(article_url)

                    insert_data = {
                        "url": unique_urls,
                        "title": llm_data.get("title", ""),
                        "intro": llm_data.get("intro", ""),
                        "summary": llm_data.get("summary", ""),
                        "category": llm_data.get("category", ""),
                        "tags": llm_data.get("tags", []),
                        "top_image": article_data.get("top_image") or DEFAULT_TOP_IMAGE,
                        "scraped_at": article_data.get("scraped_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }

                    result = session.execute(
                        text("""
                        INSERT INTO articles (
                            id, url, title, intro, summary, category, tags, 
                            top_image, scraped_at
                        )
                        VALUES (
                            gen_random_uuid(), :url, :title, :intro, :summary, 
                            :category, :tags, :top_image, :scraped_at
                        )
                        RETURNING id
                        """),
                        insert_data
                    )

                    article_id = result.scalar()
                    if article_id:
                        log_article_step(article_title, article_url, "Storing summary embedding")
                        store_embedding(article_id, llm_data.get("summary", ""))

                    session.commit()
                    log_article_step(article_title, article_url, "New article processed and saved")

            except Exception as e:
                session.rollback()
                logger.error("Error processing article content: %s", str(e))
                # Don't return here - still mark URL as processed

        mark_url_as_processed(
            url=article_url,
            orientation=political_analysis["orientation"],
            confidence=political_analysis["confidence"],
            reasoning=political_analysis["reasoning"],
            canonical_url=canonical_url
        )

        log_article_step(
            article_title,
            article_url,
            "URL marked as processed",
        )
        log_article_step(article_title, article_url, "Article processing completed")

    except Exception as e:
        logger.error("Error processing article: %s", str(e))
        logger.error("Stack trace:", exc_info=True)

        # Ensure URL is marked as processed even if there was an error
        article_url = article_data.get("url", "unknown")
        canonical_url = canonicalize_url(article_url)
        mark_url_as_processed(
            url=article_url,
            orientation="neutral",
            confidence=0.0,
            reasoning=f"Chyba pri spracovaní článku: {str(e)[:50]}",
            canonical_url=canonical_url
        )
        raise

def scrape_single_landing_page(page_config: dict, max_articles_per_page: int, global_counter: ThreadSafeCounter, max_total_articles: int = None):
    """
    Scrape a single landing page and process its articles.
    This function will be run in parallel for each landing page.
    """
    landing_url = page_config["url"]
    patterns = page_config["patterns"]
    thread_id = threading.current_thread().name
    
    logger.info(f"[{thread_id}] Starting scraping for: {landing_url}")
    
    # Create a separate session for this thread
    session = SessionLocal()
    processed_urls = get_processed_urls(session)
    processed_canonicals = {canonicalize_url(url) for url in processed_urls}
    
    page_results = {
        "landing_url": landing_url,
        "articles_processed": 0,
        "articles_found": 0,
        "errors": []
    }
    
    try:
        # Get links for this landing page
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
        logger.info(f"[{thread_id}] Found {len(new_links)} new articles on {landing_url}")
        
        # Process articles for this page
        page_count = 0
        
        for link in new_links:
            canonical_link = canonicalize_url(link)
            # Check if we've reached the max for this page
            if page_count >= max_articles_per_page:
                logger.info(f"[{thread_id}] Reached maximum of {max_articles_per_page} articles for {landing_url}")
                break
            
            # Check global limit (thread-safe)
            if max_total_articles is not None and global_counter.value >= max_total_articles:
                logger.info(f"[{thread_id}] Global maximum of {max_total_articles} articles reached")
                break
            
            try:
                # Parse article
                article_data = parse_article(link)
                if not article_data:
                    logger.warning(f"[{thread_id}] Failed to parse article at {link}")
                    mark_url_processed(session, link, canonical_url=canonical_link)
                    continue

                log_article_step(article_data.get("title"), link, "Scraped article")

                text_content = article_data.get("text", "").strip()
                if text_content and text_content.lower() != "no content":
                    # Process the article
                    process_new_article(article_data)
                    
                    # Increment counters (thread-safe)
                    total_processed = global_counter.increment()
                    page_count += 1
                    page_results["articles_processed"] += 1
                    
                    logger.info(f"[{thread_id}] Article processed: {article_data['title'][:50]}... (Total: {total_processed})")
                else:
                    log_article_step(article_data.get("title"), link, "No valid text detected, skipping", level=logging.WARNING)
                    logger.info(f"[{thread_id}] Article from {link} has no valid text, skipping")
                
                # Mark URL as processed
                mark_url_processed(session, link, canonical_url=canonical_link)
                
                # Small delay to be respectful to the website
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = f"Error processing article {link}: {str(e)}"
                logger.error(f"[{thread_id}] {error_msg}")
                page_results["errors"].append(error_msg)
                
                # Still mark URL as processed even if there was an error
                try:
                    mark_url_processed(session, link, canonical_url=canonical_link)
                except Exception as mark_error:
                    logger.error(f"[{thread_id}] Error marking URL as processed: {mark_error}")
                
                continue
    
    except Exception as e:
        error_msg = f"Error scraping landing page {landing_url}: {str(e)}"
        logger.error(f"[{thread_id}] {error_msg}")
        page_results["errors"].append(error_msg)
    
    finally:
        session.close()
    
    logger.info(f"[{thread_id}] Completed scraping {landing_url}: {page_results['articles_processed']} articles processed")
    return page_results

def scrape_for_new_articles(max_articles_per_page: int = 3, max_total_articles: int = None):
    """
    Scrape articles from all landing pages in parallel.
    Each landing page will be processed in a separate thread.
    """
    logger.info(f"Starting parallel scraping: {max_articles_per_page} articles per page, max total: {max_total_articles}")
    
    # Thread-safe counter for total articles processed
    global_counter = ThreadSafeCounter()
    
    # Store results from all threads
    all_results = []
    
    # Use ThreadPoolExecutor for parallel processing
    max_workers = min(len(LANDING_PAGES), 5)  # Limit to 5 threads max
    
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Scraper") as executor:
        # Submit scraping tasks for each landing page
        future_to_page = {
            executor.submit(
                scrape_single_landing_page, 
                page, 
                max_articles_per_page, 
                global_counter, 
                max_total_articles
            ): page for page in LANDING_PAGES
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_page):
            page_config = future_to_page[future]
            
            try:
                result = future.result()
                all_results.append(result)
                
                logger.info(f"Completed scraping {result['landing_url']}: "
                           f"{result['articles_processed']} processed, "
                           f"{result['articles_found']} found, "
                           f"{len(result['errors'])} errors")
                
            except Exception as e:
                error_msg = f"Landing page {page_config['url']} generated an exception: {e}"
                logger.error(error_msg)
                all_results.append({
                    "landing_url": page_config['url'],
                    "articles_processed": 0,
                    "articles_found": 0,
                    "errors": [error_msg]
                })
    
    # Summary logging
    total_processed = sum(result['articles_processed'] for result in all_results)
    total_found = sum(result['articles_found'] for result in all_results)
    total_errors = sum(len(result['errors']) for result in all_results)
    
    logger.info(f"Parallel scraping completed:")
    logger.info(f"  - Total articles found: {total_found}")
    logger.info(f"  - Total articles processed: {total_processed}")
    logger.info(f"  - Total errors: {total_errors}")
    
    # Log detailed results for each landing page
    for result in all_results:
        logger.info(f"  - {result['landing_url']}: {result['articles_processed']}/{result['articles_found']} processed")
        if result['errors']:
            for error in result['errors']:
                logger.warning(f"    Error: {error}")
    
    return {
        "total_processed": total_processed,
        "total_found": total_found,
        "total_errors": total_errors,
        "results_by_page": all_results
    }

def calculate_source_orientation(urls: list) -> dict:
    """
    Calculate the political orientation distribution based on source URLs.
    Returns percentages for each orientation category.
    """
    # Predefined orientation weights for different domains
    domain_orientations = {
        "pravda.sk": "center-left",
        "dennikn.sk": "center-left",
        "aktuality.sk": "center",
        "sme.sk": "center",
        "hnonline.sk": "center-right",
        "postoj.sk": "right",
        # Add more domains as needed
    }
    
    # Initialize counters
    orientations = {
        "left": 0,
        "center-left": 0,
        "neutral": 0,
        "center-right": 0,
        "right": 0
    }
    
    # Count orientations for each URL
    total_urls = len(urls)
    if total_urls == 0:
        return {
            "left_percent": 0,
            "center_left_percent": 0,
            "neutral_percent": 100,  # Default to neutral if no URLs
            "center_right_percent": 0,
            "right_percent": 0
        }
    
    for url in urls:
        # Extract domain from URL
        try:
            domain = url.split("//")[-1].split("/")[0]
            orientation = domain_orientations.get(domain, "neutral")
            orientations[orientation] = orientations.get(orientation, 0) + 1
        except Exception:
            orientations["neutral"] += 1
    
    # Calculate percentages
    return {
        "left_percent": (orientations["left"] / total_urls) * 100,
        "center_left_percent": (orientations["center-left"] / total_urls) * 100,
        "neutral_percent": (orientations["neutral"] / total_urls) * 100,
        "center_right_percent": (orientations["center-right"] / total_urls) * 100,
        "right_percent": (orientations["right"] / total_urls) * 100
    }
