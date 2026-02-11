import logging
from datetime import datetime

from sqlalchemy import text

from app.utils.political_analysis import analyze_political_orientation
from app.utils.similarity import find_similar_article
from app.utils.summary import process_article, update_article_summary, verify_article_update
from app.utils.vectorstore import store_embedding
from data.db import SessionLocal

from .constants import DEFAULT_TOP_IMAGE
from .db_utils import mark_url_as_processed
from .logging_utils import log_article_step, logger
from .url_utils import canonicalize_url

MIN_ARTICLE_TEXT_LENGTH = 200
MIN_SUMMARY_LENGTH = 80
PLACEHOLDER_TITLES = {
    "",
    "untitled",
    "no title",
    "bez nazvu",
    "bez názvu",
}


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _has_meaningful_text(value: str, min_length: int) -> bool:
    text = _normalize_text(value)
    if len(text) < min_length:
        return False
    return any(ch.isalpha() for ch in text)


def _is_placeholder_title(value: str | None) -> bool:
    title = _normalize_text(value).lower()
    return title in PLACEHOLDER_TITLES


def _select_final_title(generated_title: str | None, parsed_title: str | None) -> str:
    generated = _normalize_text(generated_title)
    parsed = _normalize_text(parsed_title)
    if not _is_placeholder_title(generated):
        return generated
    if not _is_placeholder_title(parsed):
        return parsed
    return ""


def _select_final_intro(generated_intro: str | None, fallback_summary: str) -> str:
    intro = _normalize_text(generated_intro)
    if intro:
        return intro
    # Short fallback so article metadata is still coherent when intro generation fails.
    return _normalize_text(fallback_summary)[:220]


def process_new_article(article_data: dict) -> bool:
    article_saved = False
    try:
        article_text = article_data.get("text", "").strip()
        article_url = article_data.get("url", "")
        canonical_url = canonicalize_url(article_url) if article_url else article_url
        raw_title = article_data.get("title", "")
        article_title = raw_title.strip() if raw_title else None

        if not _has_meaningful_text(article_text, MIN_ARTICLE_TEXT_LENGTH):
            log_article_step(
                article_title,
                article_url,
                "Article text is missing or too short, skipping persistence",
                level=logging.WARNING,
            )
            mark_url_as_processed(
                url=article_url,
                orientation="neutral",
                confidence=0.0,
                reasoning="Článok nemá obsah na analýzu",
                canonical_url=canonical_url
            )
            return False

        log_article_step(article_title, article_url, "Starting article processing")

        log_article_step(article_title, article_url, "Analyzing political orientation")
        try:
            political_analysis = analyze_political_orientation(article_text)
            log_article_step(
                article_title,
                article_url,
                f"Political orientation analyzed - {political_analysis['orientation']} ({political_analysis['confidence']:.2f})",
            )
        except Exception as analysis_error:
            logger.error("Political analysis failed for %s: %s", article_url, analysis_error)
            political_analysis = {
                "orientation": "neutral",
                "confidence": 0.0,
                "reasoning": f"Chyba pri analýze orientácie: {str(analysis_error)[:50]}"
            }
            log_article_step(
                article_title,
                article_url,
                "Political orientation fallback applied",
                level=logging.WARNING,
            )

        log_article_step(article_title, article_url, "Generating structured article data")
        llm_data = process_article(
            article_text,
            log_step=lambda message: log_article_step(article_title, article_url, message),
        )
        article_summary = (llm_data.get("summary", "") or "").strip()
        if not article_summary:
            logger.warning(
                "Verified summary generation returned empty result for %s; using fallback truncation.",
                article_url,
            )
            article_summary = article_text[:2000]
            log_article_step(
                article_title,
                article_url,
                "Summary generation empty, using truncated article text",
                level=logging.WARNING,
            )
        if not _has_meaningful_text(article_summary, MIN_SUMMARY_LENGTH):
            log_article_step(
                article_title,
                article_url,
                "Generated summary is too short, skipping persistence",
                level=logging.WARNING,
            )
            mark_url_as_processed(
                url=article_url,
                orientation=political_analysis["orientation"],
                confidence=political_analysis["confidence"],
                reasoning="Článok preskočený - nevalidné alebo krátke zhrnutie",
                canonical_url=canonical_url,
            )
            return False

        final_title = _select_final_title(llm_data.get("title"), article_title)
        final_intro = _select_final_intro(llm_data.get("intro"), article_summary)

        if not final_title:
            log_article_step(
                article_title,
                article_url,
                "Title guardrail triggered - skipping persistence",
                level=logging.WARNING,
            )
            mark_url_as_processed(
                url=article_url,
                orientation=political_analysis["orientation"],
                confidence=political_analysis["confidence"],
                reasoning="Článok preskočený - chýba validný titulok",
                canonical_url=canonical_url,
            )
            return False

        with SessionLocal() as session:
            try:
                existing_article_row = session.execute(
                    text(
                        """
                        SELECT id, title, intro, summary, url
                        FROM articles
                        WHERE (:article_url <> '' AND :article_url = ANY(url))
                           OR (:canonical_url <> '' AND :canonical_url = ANY(url))
                        LIMIT 1
                        """
                    ),
                    {
                        "article_url": article_url or "",
                        "canonical_url": canonical_url or "",
                    },
                ).fetchone()

                log_article_step(article_title, article_url, "Finding similar article...")
                if existing_article_row:
                    log_article_step(
                        article_title,
                        article_url,
                        "Found existing article priamo podľa URL, aktualizujem záznam",
                    )
                    similar_article = {
                        "id": str(existing_article_row[0]),
                        "title": existing_article_row[1],
                        "intro": existing_article_row[2],
                        "summary": existing_article_row[3],
                        "url": existing_article_row[4],
                    }
                    similarity_result = {"article": similar_article, "score": 1.0}
                else:
                    similarity_result = find_similar_article(
                        article_summary=article_summary,
                        article_text=article_text,
                        article_title=llm_data.get("title") or article_title,
                        article_tags=llm_data.get("tags", []),
                    )
                    similar_article = similarity_result.get("article")

                if similar_article:
                    log_article_step(
                        article_title,
                        article_url,
                        f"Found similar article - Score {similarity_result.get('score', 0.0):.2f} - {similar_article.get('title') or 'Bez názvu'}",
                    )
                    metrics = similarity_result.get("metrics", {}).get("best_match")
                    if metrics:
                        logger.debug(
                            "Similarity metrics for %s: %s",
                            f"{article_title} ({article_url})",
                            metrics,
                        )

                    log_article_step(article_title, article_url, "Updating existing article summary")
                    new_urls = []
                    for candidate in (article_url, canonical_url):
                        if candidate and candidate not in new_urls:
                            new_urls.append(candidate)

                    updated_data = update_article_summary(
                        existing_summary=similar_article["summary"],
                        new_article_text=article_text,
                        title=similar_article.get("title")
                    )

                    log_article_step(article_title, article_url, "Verifying updated article summary")
                    verified_update = verify_article_update(
                        original_summary=similar_article["summary"],
                        new_article_text=article_text,
                        updated_data=updated_data,
                        title=similar_article.get("title")
                    )
                    validated_intro = _normalize_text(verified_update.get("intro"))
                    validated_summary = _normalize_text(verified_update.get("summary"))
                    if not validated_summary:
                        validated_summary = _normalize_text(similar_article.get("summary"))
                    if not validated_intro:
                        validated_intro = _normalize_text(similar_article.get("intro"))
                    if not validated_summary:
                        log_article_step(
                            article_title,
                            article_url,
                            "Update guardrail triggered - summary missing, skipping update",
                            level=logging.WARNING,
                        )
                        session.rollback()
                        return False

                    current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    session.execute(
                        text("""
                        UPDATE articles 
                        SET 
                            intro = :intro,
                            summary = :summary,
                            url = (
                                SELECT ARRAY(
                                    SELECT DISTINCT val
                                    FROM unnest(url || :new_urls) AS val
                                )
                            ),
                            scraped_at = :scraped_at
                        WHERE id = :article_id
                        """),
                        {
                            "intro": validated_intro,
                            "summary": validated_summary,
                            "new_urls": new_urls if new_urls else similar_article.get("url", []),
                            "scraped_at": current_timestamp,
                            "article_id": similar_article["id"]
                        }
                    )

                    log_article_step(article_title, article_url, "Refreshing summary embedding")
                    store_embedding(similar_article["id"], validated_summary)

                    session.commit()
                    article_saved = True
                    log_article_step(
                        article_title,
                        article_url,
                        f"Existing article updated - {similar_article['id']}",
                    )
                else:
                    best_title = similarity_result.get("candidate_title") or "no candidate"
                    log_article_step(
                        article_title,
                        article_url,
                        f"Found no similar article - Best score {similarity_result.get('score', 0.0):.2f} - {best_title}",
                    )
                    candidate_metrics = similarity_result.get("metrics", {}).get("closest_candidate")
                    if candidate_metrics:
                        logger.debug(
                            "Closest article metrics for %s: %s",
                            f"{article_title} ({article_url})",
                            candidate_metrics,
                        )
                    log_article_step(article_title, article_url, "Persisting new article with verified data")

                    unique_urls = []
                    for candidate in (article_url, canonical_url):
                        if candidate and candidate not in unique_urls:
                            unique_urls.append(candidate)
                    if not unique_urls and article_url:
                        unique_urls.append(article_url)

                    insert_data = {
                        "url": unique_urls,
                        "title": final_title,
                        "intro": final_intro,
                        "summary": article_summary,
                        "category": llm_data.get("category", ""),
                        "tags": llm_data.get("tags", []),
                        "top_image": article_data.get("top_image") or DEFAULT_TOP_IMAGE,
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
                        log_article_step(article_title, article_url, "Storing summary embedding")
                        store_embedding(article_id, article_summary)

                    session.commit()
                    article_saved = True
                    log_article_step(article_title, article_url, "New article processed and saved")

            except Exception as exc:
                session.rollback()
                logger.error("Error processing article content: %s", str(exc))

        mark_url_as_processed(
            url=article_url,
            orientation=political_analysis["orientation"],
            confidence=political_analysis["confidence"],
            reasoning=political_analysis["reasoning"],
            canonical_url=canonical_url
        )

        log_article_step(
            article_title,
            article_url,
            "URL marked as processed",
        )
        log_article_step(article_title, article_url, "Article processing completed")
        return article_saved

    except Exception as exc:
        logger.error("Error processing article: %s", str(exc))
        logger.error("Stack trace:", exc_info=True)

        article_url = article_data.get("url", "unknown")
        canonical_url = canonicalize_url(article_url)
        mark_url_as_processed(
            url=article_url,
            orientation="neutral",
            confidence=0.0,
            reasoning=f"Chyba pri spracovaní článku: {str(exc)[:50]}",
            canonical_url=canonical_url
        )
        raise
