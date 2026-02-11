from datetime import datetime

import requests
from bs4 import BeautifulSoup
from newspaper import Article

from .logging_utils import logger


def get_landing_page_links(url, patterns):
    """
    Fetches the landing page and finds links that match the given URL patterns.
    Returns a list of absolute URLs.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("Error fetching landing page %s: %s", url, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    all_links = []

    # Identify domain for absolute URL creation
    scheme_and_domain = url.split("//")[0] + "//" + url.split("//")[1].split("/")[0]

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        if any(pattern in href for pattern in patterns):
            full_url = scheme_and_domain + href if href.startswith("/") else href
            if full_url not in all_links:
                all_links.append(full_url)

    logger.info("Found %s potential article links on %s", len(all_links), url)
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
            "videos": videos,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        logger.error("Failed to parse article at %s: %s", url, exc)
        return None
