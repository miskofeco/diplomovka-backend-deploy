import os
import json
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import requests
from bs4 import BeautifulSoup
from newspaper import Article
from sqlalchemy import text
from app.utils.vectorstore import store_embedding
from app.utils.political_analysis import analyze_political_orientation

import logging
from datetime import datetime
import os

from sqlalchemy import text
from data.db import SessionLocal
from app.utils.similarity import find_similar_article
from app.utils.summary import process_article, update_article_summary, verify_article_update

from data.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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

def mark_url_processed(session, url):
    session.execute(text("INSERT INTO processed_urls (url) VALUES (:url) ON CONFLICT DO NOTHING"), {"url": url})
    session.commit()

def is_url_processed(url: str) -> bool:
    """Check if URL has already been processed"""
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT url FROM processed_urls WHERE url = :url"),
            {"url": url}
        ).fetchone()
        return result is not None
    finally:
        session.close()

def mark_url_as_processed(url: str, orientation: str = 'neutral', confidence: float = 0.0, reasoning: str = ""):
    """Mark URL as processed with political orientation analysis"""
    session = SessionLocal()
    try:
        # Ensure reasoning is never None or empty
        if not reasoning or reasoning.strip() == "":
            if confidence == 0.0:
                reasoning = "URL označené ako spracované bez analýzy orientácie"
            else:
                reasoning = f"Orientácia: {orientation}, istota: {confidence:.1f}"
        
        # Check if URL already exists
        existing = session.execute(
            text("SELECT url, orientation, confidence, reasoning FROM processed_urls WHERE url = :url"),
            {"url": url}
        ).fetchone()
        
        if existing:
            # Only update if we have better information (higher confidence)
            existing_confidence = existing[2] or 0.0
            if confidence > existing_confidence:
                logging.info(f"Updating URL with better analysis: {url} (confidence: {existing_confidence:.2f} -> {confidence:.2f})")
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
                        "url": url, 
                        "orientation": orientation,
                        "confidence": confidence,
                        "reasoning": reasoning
                    }
                )
            else:
                logging.info(f"URL already processed with equal or better confidence: {url}")
        else:
            # Insert new record
            session.execute(
                text("""
                INSERT INTO processed_urls (url, orientation, confidence, reasoning) 
                VALUES (:url, :orientation, :confidence, :reasoning)
                """),
                {
                    "url": url, 
                    "orientation": orientation,
                    "confidence": confidence,
                    "reasoning": reasoning
                }
            )
            logging.info(f"New URL processed: {url} - {orientation} (confidence: {confidence:.2f})")
        
        session.commit()
        
    except Exception as e:
        session.rollback()
        logging.error(f"Error marking URL as processed: {e}")
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
        logging.error(f"Error fetching landing page {url}: {e}")
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

    logging.info(f"Found {len(all_links)} potential article links on {url}")
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
        logging.error(f"Failed to parse article at {url}: {e}")
        return None

def process_new_article(article_data: dict):
    try:
        article_text = article_data.get("text", "").strip()
        article_url = article_data.get("url", "")
        
        if not article_text:
            logging.warning(f"Empty article text for {article_url}, skipping processing")
            # Still mark URL as processed but with appropriate reasoning
            mark_url_as_processed(
                url=article_url,
                orientation="neutral",
                confidence=0.0,
                reasoning="Článok nemá obsah na analýzu"
            )
            return

        # Analyze political orientation FIRST
        logging.info(f"Analyzing political orientation for: {article_url}")
        try:
            political_analysis = analyze_political_orientation(article_text)
            logging.info(f"Political analysis result: {political_analysis}")
        except Exception as analysis_error:
            logging.error(f"Political analysis failed for {article_url}: {analysis_error}")
            political_analysis = {
                "orientation": "neutral",
                "confidence": 0.0,
                "reasoning": f"Chyba pri analýze orientácie: {str(analysis_error)[:50]}"
            }

        with SessionLocal() as session:
            try:
                # Check for similar articles
                similar_article = find_similar_article(article_text)
                
                if similar_article:
                    logging.info(f"Found similar article ID: {similar_article['id']}")
                    
                    # Update existing article
                    updated_data = update_article_summary(
                        existing_summary=similar_article['summary'],
                        new_article_text=article_text
                    )
                    
                    # Verify update
                    verified_update = verify_article_update(
                        original_summary=similar_article['summary'],
                        new_article_text=article_text,
                        updated_data=updated_data
                    )
                    
                    # Update article with new timestamp
                    current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    session.execute(
                        text("""
                        UPDATE articles 
                        SET 
                            intro = :intro,
                            summary = :summary,
                            url = array_append(url, :new_url),
                            scraped_at = :scraped_at
                        WHERE id = :article_id
                        """),
                        {
                            "intro": verified_update["intro"],
                            "summary": verified_update["summary"],
                            "new_url": article_url,
                            "scraped_at": current_timestamp,
                            "article_id": similar_article["id"]
                        }
                    )
                    
                    # Update embedding
                    store_embedding(similar_article["id"], verified_update["summary"])
                    
                    session.commit()
                    logging.info(f"Updated existing article {similar_article['id']} with new timestamp {current_timestamp}")
                else:
                    # Process new article
                    logging.info("Processing new article with verification...")
                    llm_data = process_article(article_text)
                    
                    # Insert new article
                    insert_data = {
                        "url": [article_url],
                        "title": llm_data.get("title", ""),
                        "intro": llm_data.get("intro", ""),
                        "summary": llm_data.get("summary", ""),
                        "category": llm_data.get("category", ""),
                        "tags": llm_data.get("tags", []),
                        "top_image": article_data.get("top_image", ""),
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
                        store_embedding(article_id, llm_data.get("summary", ""))

                    session.commit()
                    logging.info("New article processed and saved successfully")
                
            except Exception as e:
                session.rollback()
                logging.error(f"Error processing article content: {str(e)}")
                # Don't return here - still mark URL as processed
        
        # Always mark URL as processed with political orientation (outside the try-catch)
        mark_url_as_processed(
            url=article_url,
            orientation=political_analysis["orientation"],
            confidence=political_analysis["confidence"],
            reasoning=political_analysis["reasoning"]
        )
        
        logging.info(f"URL marked as processed: {article_url} - {political_analysis['orientation']} ({political_analysis['confidence']:.2f})")

    except Exception as e:
        logging.error(f"Error processing article: {str(e)}")
        logging.error(f"Stack trace:", exc_info=True)
        
        # Ensure URL is marked as processed even if there was an error
        article_url = article_data.get("url", "unknown")
        mark_url_as_processed(
            url=article_url,
            orientation="neutral",
            confidence=0.0,
            reasoning=f"Chyba pri spracovaní článku: {str(e)[:50]}"
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
    
    logging.info(f"[{thread_id}] Starting scraping for: {landing_url}")
    
    # Create a separate session for this thread
    session = SessionLocal()
    processed_urls = get_processed_urls(session)
    
    page_results = {
        "landing_url": landing_url,
        "articles_processed": 0,
        "articles_found": 0,
        "errors": []
    }
    
    try:
        # Get links for this landing page
        current_links = get_landing_page_links(landing_url, patterns)
        new_links = [link for link in current_links if link not in processed_urls]
        
        page_results["articles_found"] = len(new_links)
        logging.info(f"[{thread_id}] Found {len(new_links)} new articles on {landing_url}")
        
        # Process articles for this page
        page_count = 0
        
        for link in new_links:
            # Check if we've reached the max for this page
            if page_count >= max_articles_per_page:
                logging.info(f"[{thread_id}] Reached maximum of {max_articles_per_page} articles for {landing_url}")
                break
            
            # Check global limit (thread-safe)
            if max_total_articles is not None and global_counter.value >= max_total_articles:
                logging.info(f"[{thread_id}] Global maximum of {max_total_articles} articles reached")
                break
            
            try:
                # Parse article
                article_data = parse_article(link)
                if not article_data:
                    logging.warning(f"[{thread_id}] Failed to parse article at {link}")
                    mark_url_processed(session, link)
                    continue

                text_content = article_data.get("text", "").strip()
                if text_content and text_content.lower() != "no content":
                    # Process the article
                    process_new_article(article_data)
                    
                    # Increment counters (thread-safe)
                    total_processed = global_counter.increment()
                    page_count += 1
                    page_results["articles_processed"] += 1
                    
                    logging.info(f"[{thread_id}] Article processed: {article_data['title'][:50]}... (Total: {total_processed})")
                else:
                    logging.info(f"[{thread_id}] Article from {link} has no valid text, skipping")
                
                # Mark URL as processed
                mark_url_processed(session, link)
                
                # Small delay to be respectful to the website
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = f"Error processing article {link}: {str(e)}"
                logging.error(f"[{thread_id}] {error_msg}")
                page_results["errors"].append(error_msg)
                
                # Still mark URL as processed even if there was an error
                try:
                    mark_url_processed(session, link)
                except Exception as mark_error:
                    logging.error(f"[{thread_id}] Error marking URL as processed: {mark_error}")
                
                continue
    
    except Exception as e:
        error_msg = f"Error scraping landing page {landing_url}: {str(e)}"
        logging.error(f"[{thread_id}] {error_msg}")
        page_results["errors"].append(error_msg)
    
    finally:
        session.close()
    
    logging.info(f"[{thread_id}] Completed scraping {landing_url}: {page_results['articles_processed']} articles processed")
    return page_results

def scrape_for_new_articles(max_articles_per_page: int = 3, max_total_articles: int = None):
    """
    Scrape articles from all landing pages in parallel.
    Each landing page will be processed in a separate thread.
    """
    logging.info(f"Starting parallel scraping: {max_articles_per_page} articles per page, max total: {max_total_articles}")
    
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
                
                logging.info(f"Completed scraping {result['landing_url']}: "
                           f"{result['articles_processed']} processed, "
                           f"{result['articles_found']} found, "
                           f"{len(result['errors'])} errors")
                
            except Exception as e:
                error_msg = f"Landing page {page_config['url']} generated an exception: {e}"
                logging.error(error_msg)
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
    
    logging.info(f"Parallel scraping completed:")
    logging.info(f"  - Total articles found: {total_found}")
    logging.info(f"  - Total articles processed: {total_processed}")
    logging.info(f"  - Total errors: {total_errors}")
    
    # Log detailed results for each landing page
    for result in all_results:
        logging.info(f"  - {result['landing_url']}: {result['articles_processed']}/{result['articles_found']} processed")
        if result['errors']:
            for error in result['errors']:
                logging.warning(f"    Error: {error}")
    
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
