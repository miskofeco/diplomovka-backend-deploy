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
from processing.summary import process_article, update_article_summary

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
    #{
    #    "url": "https://domov.sme.sk/",
    #    "patterns": ["/c/"]
    #}
]

def get_processed_urls_db(session):
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

session = SessionLocal()
def process_new_article(article):
            article_text = article.get("text", "").strip()
            if not article_text:
                logging.info("Skipping empty article.")
                return

            if similar_article := find_similar_article(article_text):
                logging.info(f"Updating existing article ID: {similar_article['id']}")
                updated_data = update_article_summary(similar_article["summary"], article_text)
                session.execute(
                    text("""
                    UPDATE articles
                    SET summary = :summary,
                        intro = :intro,
                        url = array_append(articles.url, :url)
                    WHERE id = :article_id
                    """),
                    {
                        "summary": updated_data["summary"],
                        "intro": updated_data["intro"],
                        "url": article.get("url", ""),
                        "article_id": similar_article["id"],
                    }
                )
            else:
                # Process article with LLM
                llm_data = process_article(article_text)

                result = session.execute(
                    text("""
                    INSERT INTO articles (id, url, title, intro, summary, category, tags, top_image)
                    VALUES (gen_random_uuid(), ARRAY[:url], :title, :intro, :summary, :category, ARRAY[:tags], :top_image)
                    RETURNING id
                    """),
                    {
                        "url": article.get("url", ""),
                        "title": llm_data.get("title", ""),
                        "intro": llm_data.get("intro", ""),
                        "summary": llm_data.get("summary", ""),
                        "category": llm_data.get("category", ""),
                        "tags": llm_data.get("tags", []),
                        "top_image": article.get("top_image", ""),
                    },
                )
                if article_id := result.scalar():
                    store_embedding(article_id, llm_data.get("summary", ""))

            session.commit()

def scrape_for_new_articles():
    session = SessionLocal()
    processed_urls = get_processed_urls_db(session)

    for page in LANDING_PAGES:
        landing_url = page["url"]
        patterns = page["patterns"]
        logging.info(f"Processing landing page: {landing_url} with patterns {patterns}")

        current_links = get_landing_page_links(landing_url, patterns)
        new_links = [link for link in current_links if link not in processed_urls]
        logging.info(f"Number of new articles found on {landing_url}: {len(new_links)}")

        for link in new_links:
            article_data = parse_article(link)
            text_content = article_data.get("text", "").strip() if article_data else ""
            if article_data and text_content and text_content.lower() != "no content":
                process_new_article(article_data)
                logging.info(f"New article scraped: {article_data['title'][:50]}...")
            else:
                logging.info(f"Article from {link} has no valid text (found: '{text_content}'), marking as processed and skipping saving article data.")
            
            # Mark the URL as processed in the database
            mark_url_processed(session, link)
            time.sleep(1)  # Delay to respect site's resources
