import requests
from bs4 import BeautifulSoup
import schedule
import time
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_website_one():
    """
    Fetches articles from the first news website, parses the HTML,
    extracts relevant details (title, date, author, content), and returns them as a list of dicts.
    """
    url = "https://example-news-1.com"
    articles_data = []

    try:
        # 1. Send a GET request
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Check if the request was successful

        # 2. Parse the HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # 3. Find all article containers
        # (Modify the selector based on the site’s structure)
        article_elements = soup.find_all('div', class_='article-container')

        # 4. Extract info from each article
        for article in article_elements:
            title_tag = article.find('h2', class_='article-title')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            author_tag = article.find('span', class_='author-name')
            author = author_tag.get_text(strip=True) if author_tag else "Unknown"

            date_tag = article.find('span', class_='publish-date')
            publish_date = date_tag.get_text(strip=True) if date_tag else "No Date"

            content_div = article.find('div', class_='article-body')
            content = content_div.get_text(strip=True) if content_div else "No Content"

            # Build a dictionary for each article
            articles_data.append({
                "title": title,
                "author": author,
                "publish_date": publish_date,
                "content": content,
                "source_url": url
            })

        logging.info(f"Scraped {len(articles_data)} articles from Website One.")

    except Exception as e:
        logging.error(f"Error scraping Website One: {e}")

    return articles_data


def scrape_website_two():
    """
    Fetches articles from the second news website.
    This is a placeholder with a different structure as an example.
    """
    url = "https://example-news-2.com"
    articles_data = []

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Example: second site might have <article> elements with different classes
        article_elements = soup.find_all('article')

        for article in article_elements:
            # Adjust the selectors for the second site
            title = article.find('h1').get_text(strip=True) if article.find('h1') else "No Title"
            author = article.find('p', class_='byline').get_text(strip=True) if article.find('p', class_='byline') else "Unknown Author"
            publish_date = article.find('time').get_text(strip=True) if article.find('time') else "No Date"
            content = article.find('div', class_='content-section').get_text(strip=True) if article.find('div', class_='content-section') else "No Content"

            articles_data.append({
                "title": title,
                "author": author,
                "publish_date": publish_date,
                "content": content,
                "source_url": url
            })

        logging.info(f"Scraped {len(articles_data)} articles from Website Two.")

    except Exception as e:
        logging.error(f"Error scraping Website Two: {e}")

    return articles_data


def scrape_all_websites():
    """
    Calls individual scrapers for multiple websites and combines the data.
    It also demonstrates basic text processing and saving the results in a JSON file.
    """
    all_articles = []
    
    # Scrape from Website One
    articles_one = scrape_website_one()
    
    # Simple text processing example: make the content lowercase (just a demonstration)
    for article in articles_one:
        article['content'] = article['content'].lower()
    all_articles.extend(articles_one)

    # Scrape from Website Two
    articles_two = scrape_website_two()
    
    # Another text processing example: remove certain words or punctuation
    for article in articles_two:
        # Very naive text cleanup example
        article['content'] = article['content'].replace('.', '')
    all_articles.extend(articles_two)

    # Save the combined articles to a JSON file
    output_filename = f"scraped_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_filename, "w", encoding='utf-8') as outfile:
        json.dump(all_articles, outfile, ensure_ascii=False, indent=4)

    logging.info(f"Saved a total of {len(all_articles)} articles to {output_filename}")


def schedule_scraping():
    """
    Demonstrates using the schedule library to run `scrape_all_websites()`
    periodically. Adjust the interval as needed.
    """
    # Example: Run scrape_all_websites() every hour
    schedule.every(1).hours.do(scrape_all_websites)

    while True:
        schedule.run_pending()
        # Sleep for a short duration to avoid busy waiting
        time.sleep(60)

# Uncomment the below lines if you want to run the scraping periodically.
# if __name__ == "__main__":
#     schedule_scraping()

# Or call the function once to scrape all websites now:
if __name__ == "__main__":
    scrape_all_websites()