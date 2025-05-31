import os
import json
import time
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from newspaper import Article
from sqlalchemy import text
from processing.vectorstore import store_embedding

import logging
from datetime import datetime
import os

from sqlalchemy import text
from data.db import SessionLocal
from processing.similarity import find_similar_article
from processing.summary import process_article, update_article_summary, verify_article_update

from data.db import SessionLocal


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
        if not article_text:
            logging.warning("Empty article text, skipping processing")
            return

        with SessionLocal() as session:
            try:
                # Skontrolujeme či existuje podobný článok
                similar_article = find_similar_article(article_text)
                
                if similar_article:
                    logging.info(f"Found similar article ID: {similar_article['id']}")
                    
                    # Aktualizujeme existujúci článok
                    updated_data = update_article_summary(
                        existing_summary=similar_article['summary'],
                        new_article_text=article_text
                    )
                    
                    # NOVÉ: Verifikujeme aktualizáciu pred uložením
                    logging.info("Verifying article update before saving...")
                    verified_update = verify_article_update(
                        original_summary=similar_article['summary'],
                        new_article_text=article_text,
                        updated_data=updated_data
                    )
                    
                    # Aktualizujeme článok v databáze s verifikovanými údajmi
                    session.execute(
                        text("""
                        UPDATE articles 
                        SET 
                            intro = :intro,
                            summary = :summary,
                            url = array_append(url, :new_url)
                        WHERE id = :article_id
                        """),
                        {
                            "intro": verified_update["intro"],
                            "summary": verified_update["summary"],
                            "new_url": article_data.get("url"),
                            "article_id": similar_article["id"]
                        }
                    )
                    
                    # Aktualizujeme embedding pre nový súhrn
                    store_embedding(similar_article["id"], verified_update["summary"])
                    
                    session.commit()
                    logging.info(f"Updated existing article {similar_article['id']} with verified content")
                    return

                # Spracovanie nového článku (existing code with verification)
                logging.info("Processing new article with verification...")
                llm_data = process_article(article_text)  # This already includes verification
                
                # Basic insert data without additional processing
                insert_data = {
                    "url": [article_data.get("url", "")],  # Wrap in list for ARRAY type
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
                logging.info("New article processed and saved successfully with verification")
                
            except Exception as e:
                session.rollback()
                logging.error(f"Error processing article: {str(e)}")
                logging.error(f"Article data: {article_data}")
                raise

    except Exception as e:
        logging.error(f"Error processing article: {str(e)}")
        logging.error(f"Stack trace:", exc_info=True)
        raise

def scrape_for_new_articles(max_articles_per_page: int = 3, max_total_articles: int = None):
    session = SessionLocal()
    processed_urls = get_processed_urls(session)
    
    total_count = 0
    
    try:
        for page in LANDING_PAGES:
            landing_url = page["url"]
            patterns = page["patterns"]
            logging.info(f"Processing landing page: {landing_url} with patterns {patterns}")

            current_links = get_landing_page_links(landing_url, patterns)
            new_links = [link for link in current_links if link not in processed_urls]
            logging.info(f"Number of new articles found on {landing_url}: {len(new_links)}")
            
            # Counter for articles from this page
            page_count = 0
            
            for link in new_links:
                # Check if we've reached the max for this page
                if page_count >= max_articles_per_page:
                    logging.info(f"Reached maximum of {max_articles_per_page} articles for {landing_url}")
                    break
                
                # Check if we've reached the total max (if specified)
                if max_total_articles is not None and total_count >= max_total_articles:
                    logging.info(f"Reached maximum total of {max_total_articles} articles")
                    break
                    
                article_data = parse_article(link)
                if not article_data:
                    logging.warning(f"Failed to parse article at {link}")
                    mark_url_processed(session, link)
                    continue

                text_content = article_data.get("text", "").strip()
                if text_content and text_content.lower() != "no content":
                    process_new_article(article_data)
                    logging.info(f"New article scraped: {article_data['title'][:50]}...")
                    total_count += 1
                    page_count += 1
                else:
                    logging.info(f"Article from {link} has no valid text (found: '{text_content}'), marking as processed and skipping saving article data.")
                
                mark_url_processed(session, link)
                time.sleep(1)  # Delay to respect site's resources
    except Exception as e:
        logging.error(f"Error during scraping: {str(e)}")
        raise
    finally:
        session.close()

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
