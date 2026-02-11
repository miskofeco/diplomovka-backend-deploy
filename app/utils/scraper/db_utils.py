from sqlalchemy import text

from data.db import SessionLocal

from .logging_utils import logger
from .url_utils import canonicalize_url


def get_processed_urls(session):
    """Get set of all processed URLs from database"""
    result = session.execute(text("SELECT url FROM processed_urls"))
    return {row[0] for row in result.fetchall()}


def mark_url_processed(session, url, canonical_url: str | None = None):
    urls_to_mark = {url}

    canonical_from_url = canonicalize_url(url)
    if canonical_from_url and canonical_from_url != url:
        urls_to_mark.add(canonical_from_url)

    if canonical_url:
        normalized = canonicalize_url(canonical_url)
        if normalized:
            urls_to_mark.add(normalized)

    for value in urls_to_mark:
        session.execute(
            text("INSERT INTO processed_urls (url) VALUES (:url) ON CONFLICT DO NOTHING"),
            {"url": value}
        )
    session.commit()


def is_url_processed(url: str) -> bool:
    """Check if URL has already been processed (including canonical variants)."""
    session = SessionLocal()
    try:
        urls_to_check = {url}
        canonical = canonicalize_url(url)
        if canonical:
            urls_to_check.add(canonical)

        result = session.execute(
            text("SELECT 1 FROM processed_urls WHERE url = ANY(:urls)"),
            {"urls": list(urls_to_check)}
        ).fetchone()
        return result is not None
    finally:
        session.close()


def _reserve_url_for_processing(url: str, canonical_url: str | None) -> bool:
    """Reserve a URL in processed_urls to avoid concurrent duplicate processing."""
    if not url:
        return False

    session = SessionLocal()
    try:
        primary = canonical_url or url
        urls_to_reserve = []
        if primary:
            urls_to_reserve.append(primary)
        if url and url != primary:
            urls_to_reserve.append(url)

        reserved = False
        for index, value in enumerate(urls_to_reserve):
            result = session.execute(
                text(
                    """
                    INSERT INTO processed_urls (url, orientation, confidence, reasoning)
                    VALUES (:url, :orientation, 0.0, :reasoning)
                    ON CONFLICT (url) DO NOTHING
                    RETURNING url
                    """
                ),
                {
                    "url": value,
                    "orientation": "pending",
                    "reasoning": "Rezervované na spracovanie článku",
                },
            ).fetchone()

            if index == 0:
                # Primary URL (canonical or original) determines reservation success
                if result is None:
                    session.rollback()
                    return False
                reserved = True

        session.commit()
        return reserved
    except Exception as exc:
        session.rollback()
        logger.error("Failed to reserve URL %s: %s", url, exc)
        return False
    finally:
        session.close()


def mark_url_as_processed(
    url: str,
    orientation: str = 'neutral',
    confidence: float = 0.0,
    reasoning: str = "",
    canonical_url: str | None = None
):
    """Mark URL as processed with political orientation analysis"""
    session = SessionLocal()
    try:
        if not reasoning or reasoning.strip() == "":
            if confidence == 0.0:
                reasoning = "URL označené ako spracované bez analýzy orientácie"
            else:
                reasoning = f"Orientácia: {orientation}, istota: {confidence:.1f}"
        urls_to_mark = {url}
        canonical_from_url = canonicalize_url(url)
        if canonical_from_url and canonical_from_url != url:
            urls_to_mark.add(canonical_from_url)
        if canonical_url:
            normalized = canonicalize_url(canonical_url)
            if normalized:
                urls_to_mark.add(normalized)

        for target_url in urls_to_mark:
            existing = session.execute(
                text("SELECT url, orientation, confidence, reasoning FROM processed_urls WHERE url = :url"),
                {"url": target_url}
            ).fetchone()

            if existing:
                existing_confidence = existing[2] or 0.0
                if confidence > existing_confidence:
                    logger.info(
                        "Updating URL with better analysis: %s (confidence: %.2f -> %.2f)",
                        target_url,
                        existing_confidence,
                        confidence,
                    )
                    session.execute(
                        text("""
                        UPDATE processed_urls 
                        SET orientation = :orientation,
                            confidence = :confidence,
                            reasoning = :reasoning,
                            scraped_at = CURRENT_TIMESTAMP
                        WHERE url = :url
                        """),
                        {
                            "url": target_url, 
                            "orientation": orientation,
                            "confidence": confidence,
                            "reasoning": reasoning
                        }
                    )
                else:
                    logger.info("URL už bolo spracované s rovnakou alebo vyššou istotou: %s", target_url)
            else:
                session.execute(
                    text("""
                    INSERT INTO processed_urls (url, orientation, confidence, reasoning) 
                    VALUES (:url, :orientation, :confidence, :reasoning)
                    """),
                    {
                        "url": target_url, 
                        "orientation": orientation,
                        "confidence": confidence,
                        "reasoning": reasoning
                    }
                )
                logger.info(
                    "New URL processed: %s - %s (confidence: %.2f)",
                    target_url,
                    orientation,
                    confidence,
                )

        session.commit()

    except Exception as exc:
        session.rollback()
        logger.error("Error marking URL as processed: %s", exc)
    finally:
        session.close()
