import logging
from dotenv import load_dotenv
from datetime import datetime
import os

from sqlalchemy.orm import Session
from sqlalchemy import text
from data.db import SessionLocal
from processing.similarity import find_similar_article
from processing.summary import process_article, update_article_summary
import openai
from openai import OpenAI

from scraping.scraping import scrape_for_new_articles
from processing.vectorstore import store_embedding

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

    logging.info(f"Processed {len(articles)} new articles.")