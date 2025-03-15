import logging
import json
import os
import uuid
from datetime import datetime

from scraping.scraping import scrape_for_new_articles
from processing.summary import process_article
from processing.vectorstore import update_faiss_index

def process_new_articles():
    # Scrape new articles (assumes scrape_for_new_articles returns a list of articles)
    articles = scrape_for_new_articles()  
    processed_articles = []

    for article in articles:
        text = article.get("text", "").strip()
        if not text:
            logging.info("Article text is empty; skipping.")
            continue

        try:
            # Process article text via the LLM (should return a dict with keys like title, intro, summary, category, tags, etc.)
            llm_data = process_article(text)
        except Exception as e:
            logging.error(f"LLM processing error for article {article.get('url')}: {e}")
            continue

        # Merge scraped article info with LLM output and add a timestamp
        processed_article = {
            "id": str(uuid.uuid4()),
            "url": article.get("url", ""),
            "top_image": article.get("top_image", ""),
            **llm_data,
            "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        processed_articles.append(processed_article)

        # Update vector store with the article's summary embedding (if available)
        summary_text = llm_data.get("summary", "").strip()
        if summary_text:
            update_faiss_index(summary_text, processed_article["id"])
        else:
            logging.info(f"Article {article['id']} has no summary for embedding.")

    # Append new processed articles to processed.json
    processed_file = "./data/processed.json"
    if os.path.exists(processed_file):
        with open(processed_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []
    existing.extend(processed_articles)
    with open(processed_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=4)
    logging.info(f"Processed {len(processed_articles)} new articles.")