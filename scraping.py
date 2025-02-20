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
LANDING_PAGE_URL = "https://www.aktuality.sk"  # The main news page
URL_PATTERNS = ["/clanok/"]                    # Patterns in link HREF to filter for articles
PROCESSED_URLS_FILE = "processed_urls.json"    # File to keep track of processed article URLs
SCRAPED_ARTICLES_FILE = "scraped_articles.json"# File to store article data
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
    """
    Saves the set of processed URLs to a JSON file.
    """
    try:
        with open(PROCESSED_URLS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_urls), f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to save to {PROCESSED_URLS_FILE}: {e}")

def load_scraped_articles():
    """
    Loads already scraped article data from a JSON file.
    Returns a list if found, else an empty list.
    """
    if not os.path.exists(SCRAPED_ARTICLES_FILE):
        return []
    try:
        with open(SCRAPED_ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load {SCRAPED_ARTICLES_FILE}: {e}")
        return []

def save_scraped_articles(articles_data):
    """
    Saves article data to a JSON file.
    """
    try:
        with open(SCRAPED_ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump(articles_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to save to {SCRAPED_ARTICLES_FILE}: {e}")

def get_landing_page_links(url):
    """
    Fetches the landing page and finds links that match the URL_PATTERNS.
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
    # e.g., "https://example.com"
    scheme_and_domain = url.split("//")[0] + "//" + url.split("//")[1].split("/")[0]

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Check if this link matches our patterns
        if any(pattern in href for pattern in URL_PATTERNS):
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

        data = {
            "url": url,
            "title": article.title or "No Title",
            "authors": article.authors or ["Unknown Author"],
            "publish_date": (article.publish_date.strftime("%Y-%m-%d %H:%M:%S") 
                             if article.publish_date else "Unknown Date"),
            "text": article.text or "No Content",
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Optionally run NLP
        #article.nlp()
        #data["summary"] = article.summary
        #data["keywords"] = article.keywords

        return data

    except Exception as e:
        logging.error(f"Failed to parse article at {url}: {e}")
        return None

def scrape_for_new_articles(landing_page_url):
    """
    - Loads previously processed URLs.
    - Gets new links from the landing page.
    - For each link, checks if it's already processed.
      - If not, parse with newspaper3k and store the result.
    - Saves updated processed URLs and article data to JSON.
    """

    # 1. Load previously processed URLs and existing articles
    processed_urls = load_processed_urls()
    articles_data = load_scraped_articles()

    # 2. Get current article links from the landing page
    current_links = get_landing_page_links(landing_page_url)

    # 3. Filter new links
    new_links = [link for link in current_links if link not in processed_urls]
    logging.info(f"Number of new articles found: {len(new_links)}")

    # 4. Parse each new link
    for link in new_links:
        article_data = parse_article(link)
        if article_data:
            articles_data.append(article_data)
            # Mark this link as processed
            processed_urls.add(link)
            # Log a short snippet of the title to keep track
            logging.info(f"New article scraped: {article_data['title'][:50]}...")

        # Optional: short delay to respect the site's resources
        time.sleep(1)

    # 5. Save updated data
    save_scraped_articles(articles_data)
    save_processed_urls(processed_urls)

    # Optionally return new articles, or just return the entire data
    return articles_data

if __name__ == "__main__":
    # You can call this function once, or schedule it to run periodically.
    updated_articles = scrape_for_new_articles(LANDING_PAGE_URL)
    # For demonstration, print how many total articles we have after this run
    logging.info(f"Total articles stored so far: {len(updated_articles)}")