import logging
import json
import os
import uuid
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text
from data.db import SessionLocal

from scraping.scraping import scrape_for_new_articles
from processing.summary import process_article
from processing.vectorstore import store_embedding

def process_new_articles():
    """Scrapes, processes, and stores articles & embeddings in PostgreSQL."""
    articles = scrape_for_new_articles()

    # Use a context manager so the session is properly closed.
    with SessionLocal() as session:
        for article in articles:
            article_text = article.get("text", "").strip()
            if not article_text:
                logging.info("Skipping empty article.")
                continue

            # Process article with LLM
            llm_data = process_article(article_text)

            # Insert article into PostgreSQL and retrieve the article ID
            result = session.execute(
                text("""
                INSERT INTO articles (id, url, title, intro, summary, category, tags, top_image)
                VALUES (gen_random_uuid(), ARRAY[:url], :title, :intro, :summary, :category, ARRAY[:tags], :top_image)
                ON CONFLICT (id) DO UPDATE
                SET url = array_append(articles.url, EXCLUDED.url::TEXT),
                    tags = array_cat(articles.tags, EXCLUDED.tags::TEXT[]),
                    title = EXCLUDED.title,
                    intro = EXCLUDED.intro,
                    summary = EXCLUDED.summary,
                    category = EXCLUDED.category,
                    top_image = EXCLUDED.top_image
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

    logging.info(f"Processed {len(articles)} new articles.")