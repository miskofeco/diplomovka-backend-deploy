import os
import json
import time
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from newspaper import Article

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ------------------------ CONFIG ------------------------ #
# Hospodarske noviny, hlavnespravy.sk, trend.sk, noviny.sk, topky.sk, novycas.sk
LANDING_PAGES = [
    #{
    #    "url": "https://pravda.sk/",
    #    "patterns": ["/clanok/"]
    #},
    {
        "url": "https://www.aktuality.sk",
        "patterns": ["/clanok/"]
    },
    #{
    #    "url": "https://domov.sme.sk/",
    #    "patterns": ["/c/"]
    #}
]
PROCESSED_URLS_FILE = "../data/urls.json"    # File to keep track of processed article URLs
SCRAPED_ARTICLES_FILE = "../data/scraped.json"  # File to store article data
# -------------------------------------------------------- #

def load_processed_urls():
    """
    Loads processed article URLs from JSON file into a Python set. 
    Returns an empty set if the file doesn't exist or is invalid.
    """
    if not os.path.exists(PROCESSED_URLS_FILE):
        return set()
    try:
        with open(PROCESSED_URLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert list to set for faster membership checks
            return set(data)
    except Exception as e:
        logging.error(f"Failed to load {PROCESSED_URLS_FILE}: {e}")
        return set()

def save_processed_urls(processed_urls):

    try:
        with open(PROCESSED_URLS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_urls), f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to save to {PROCESSED_URLS_FILE}: {e}")

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
            if href.startswith("/"):
                full_url = scheme_and_domain + href
            else:
                full_url = href
            
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

        top_image = article.top_image if article.top_image else ""
        # Extract video URLs if any
        videos = article.movies if article.movies else []

        data = {
            "url": url,
            "title": article.title or "No Title",
            "publish_date": (article.publish_date.strftime("%Y-%m-%d %H:%M:%S") 
                            if article.publish_date else "Unknown Date"),
            "text": article.text or "No Content",
            "top_image": top_image,
            "videos": videos,  # Added video links
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return data

    except Exception as e:
        logging.error(f"Failed to parse article at {url}: {e}")
        return None

def scrape_for_new_articles():
    processed_urls = load_processed_urls()
    new_articles = [] 
    articles_count = 0  # Counter for the number of successfully scraped articles

    for page in LANDING_PAGES:
        landing_url = page["url"]
        patterns = page["patterns"]
        logging.info(f"Processing landing page: {landing_url} with patterns {patterns}")

        current_links = get_landing_page_links(landing_url, patterns)
        new_links = [link for link in current_links if link not in processed_urls]
        logging.info(f"Number of new articles found on {landing_url}: {len(new_links)}")

        for link in new_links:

            article_data = parse_article(link)
            # Retrieve and clean the article text
            text_content = article_data.get("text", "").strip() if article_data else ""
            # Check if article_data exists, text is non-empty, and not equal to the default "No Content"
            if article_data and text_content and text_content.lower() != "no content":
                new_articles.append(article_data)
                logging.info(f"New article scraped: {article_data['title'][:50]}...")
                articles_count += 1
            else:
                logging.info(f"Article from {link} has no valid text (found: '{text_content}'), marking as processed and skipping saving article data.")
            # Mark the URL as processed regardless of whether valid article data was retrieved
            processed_urls.add(link)
            time.sleep(1)  # Delay to respect site's resources


    save_processed_urls(processed_urls)
    return new_articles