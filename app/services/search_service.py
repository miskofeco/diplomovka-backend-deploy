import logging
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import text

from data.db import SessionLocal
from app.utils.vectorstore import store_embedding
from app.utils.similarity import semantic_query_search

from .embedding_service import cosine_similarity, get_embedding


class SearchServiceError(Exception):
    """Base class for search-related failures."""


class EmbeddingGenerationError(SearchServiceError):
    """Raised when embeddings cannot be generated."""


def search_articles(query: str, advanced: bool) -> List[Dict]:
    """Search articles either via text match or embedding similarity."""
    if not query or len(query) < 2:
        return []

    session = SessionLocal()
    try:
        if advanced:
            logging.info("Performing advanced vector search for: %s", query)
            query_embedding = get_embedding(query)
            if not query_embedding:
                raise EmbeddingGenerationError("Failed to generate query embedding")

            embeddings_count = session.execute(
                text("SELECT COUNT(*) FROM article_embeddings WHERE embedding IS NOT NULL")
            ).scalar()
            logging.info("Found %s articles with embeddings", embeddings_count)

            if embeddings_count and embeddings_count > 0:
                articles = semantic_query_search(
                    session=session,
                    query_embedding=np.array(query_embedding, dtype=np.float32),
                    query_text=query,
                )
                if articles:
                    logging.info("Semantic vector search returned %s results", len(articles))
                    return articles

                logging.warning(
                    "No similar articles found with vector search, falling back to regular search"
                )
            else:
                logging.warning("No embeddings found, falling back to regular search")

        logging.info("Performing regular text search for: %s", query)
        search_query = f"%{query.lower()}%"
        sql_query = """
            SELECT DISTINCT
                id, title, intro, summary, url, category, tags, top_image, scraped_at
            FROM articles 
            WHERE 
                LOWER(title) LIKE :query OR
                LOWER(summary) LIKE :query OR
                LOWER(intro) LIKE :query OR
                LOWER(category) LIKE :query OR
                tags::text LIKE :query
            ORDER BY scraped_at DESC
            LIMIT 20
        """

        result = session.execute(text(sql_query), {"query": search_query})
        articles = []
        seen_titles = set()
        for r in result:
            title = r[1]
            if title not in seen_titles:
                seen_titles.add(title)
                articles.append(_row_to_article_dict(r))

        logging.info("Regular search returned %s results", len(articles))
        return articles
    except EmbeddingGenerationError:
        raise
    except Exception as exc:
        session.rollback()
        logging.error("Error searching articles: %s", exc)
        raise SearchServiceError("Search failed") from exc
    finally:
        session.close()


def find_similar_articles(article_id: str) -> List[Dict]:
    """Find semantically similar articles based on embeddings."""
    session = SessionLocal()
    try:
        logging.info("Starting fresh similarity search for article %s", article_id)
        current_article_query = """
            SELECT a.id, a.title, a.summary, ae.embedding
            FROM articles a
            LEFT JOIN article_embeddings ae ON a.id = ae.id
            WHERE a.id = :article_id
        """

        current_result = session.execute(
            text(current_article_query),
            {"article_id": article_id},
        ).fetchone()

        if not current_result:
            logging.error("Article %s not found", article_id)
            raise SearchServiceError("Article not found")

        current_embedding = current_result[3]
        current_summary = current_result[2]
        current_title = current_result[1]

        logging.info("Processing article: %s...", current_title[:50])

        if not current_embedding and current_summary:
            logging.warning(
                "No embedding found for article %s, generating fresh embedding",
                article_id,
            )
            fresh_embedding = get_embedding(current_summary)
            if fresh_embedding:
                try:
                    store_embedding(article_id, current_summary)
                    current_embedding = fresh_embedding
                    logging.info(
                        "Generated and stored new embedding for article %s",
                        article_id,
                    )
                except Exception as exc:
                    logging.warning("Could not store embedding: %s", exc)
                    current_embedding = fresh_embedding

        if not current_embedding:
            logging.warning(
                "Could not generate embedding for article %s, using recent articles fallback",
                article_id,
            )
            return _recent_articles(session, article_id, limit=10)

        logging.info("Performing fresh semantic similarity search across all articles")
        similarity_query = """
            SELECT 
                a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at,
                ae.embedding
            FROM articles a
            INNER JOIN article_embeddings ae ON a.id = ae.id
            WHERE a.id != :article_id AND ae.embedding IS NOT NULL
            ORDER BY a.scraped_at DESC
        """

        articles_with_similarity = _collect_similar_articles(
            session, similarity_query, article_id, current_embedding, 0.1
        )

        if not articles_with_similarity:
            logging.warning(
                "No articles found with similarity > 0.1, trying with very low threshold"
            )
            articles_with_similarity = _collect_similar_articles(
                session, similarity_query, article_id, current_embedding, 0.05
            )

        if not articles_with_similarity:
            logging.warning(
                "No similar articles found even with very low threshold, using recent articles"
            )
            return _recent_articles(session, article_id, limit=10)

        articles_with_similarity.sort(key=lambda x: x["similarity"], reverse=True)
        logging.info("Top 10 similarity matches:")
        for index, article in enumerate(articles_with_similarity[:10]):
            logging.info("%s. %s (%.4f)", index + 1, article["title"], article["similarity"])

        top_articles = []
        seen_titles = set()
        for article in articles_with_similarity:
            title = article["title"]
            if title not in seen_titles:
                seen_titles.add(title)
                article_without_similarity = dict(article)
                article_without_similarity.pop("similarity", None)
                top_articles.append(article_without_similarity)
            if len(top_articles) >= 10:
                break

        if not top_articles:
            logging.warning(
                "Similarity list collapsed after deduplication, using emergency fallback"
            )
            return _recent_articles(session, article_id, limit=8)

        return top_articles
    except SearchServiceError:
        raise
    except Exception as exc:
        session.rollback()
        logging.error("Error finding similar articles: %s", exc)
        raise SearchServiceError("Failed to find similar articles") from exc
    finally:
        session.close()
def _collect_similar_articles(
    session, query: str, article_id: str, base_embedding: List[float], threshold: float
) -> List[Dict]:
    result = session.execute(text(query), {"article_id": article_id})
    articles_with_similarity: List[Dict] = []
    similarity_scores = []
    processed_count = 0

    for row in result:
        stored_embedding = row[9]
        if stored_embedding and len(stored_embedding) > 0:
            try:
                similarity = cosine_similarity(base_embedding, stored_embedding)
                processed_count += 1
                similarity_scores.append(similarity)
                if similarity > threshold:
                    articles_with_similarity.append(
                        {
                            "similarity": float(similarity),
                            **_row_to_article_dict(row),
                        }
                    )
            except Exception as exc:
                logging.warning("Error calculating similarity for article %s: %s", row[0], exc)

    if similarity_scores:
        avg_similarity = sum(similarity_scores) / len(similarity_scores)
        max_similarity = max(similarity_scores)
        logging.info(
            "Similarity stats: processed=%s, found=%s, avg=%.3f, max=%.3f",
            processed_count,
            len(articles_with_similarity),
            avg_similarity,
            max_similarity,
        )

    return articles_with_similarity


def _recent_articles(session, article_id: str, limit: int) -> List[Dict]:
    recent_query = """
        SELECT DISTINCT
            a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at
        FROM articles a
        WHERE a.id != :article_id
        ORDER BY a.scraped_at DESC
        LIMIT :limit
    """

    result = session.execute(text(recent_query), {"article_id": article_id, "limit": limit})
    articles = [_row_to_article_dict(row) for row in result]
    logging.info("Fallback: returning %s recent articles", len(articles))
    return articles


def _row_to_article_dict(row) -> Dict:
    return {
        "id": str(row[0]) if row[0] else None,
        "title": row[1],
        "intro": row[2],
        "summary": row[3],
        "url": row[4],
        "category": row[5],
        "tags": row[6],
        "top_image": row[7],
        "scraped_at": row[8].isoformat() if row[8] else None,
    }


__all__ = [
    "EmbeddingGenerationError",
    "SearchServiceError",
    "find_similar_articles",
    "search_articles",
]
