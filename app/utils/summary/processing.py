import logging
from typing import Callable, Optional

from .summary_service import get_category_and_tags, get_summary, get_title_and_intro
from .verification import verify_category_tags, verify_summary, verify_title_intro


def _emit_step(log_step: Optional[Callable[[str], None]], message: str) -> None:
    if not log_step:
        return
    try:
        log_step(message)
    except Exception:
        logging.debug("Failed to emit log step '%s'", message)


def process_article(text: str, log_step: Optional[Callable[[str], None]] = None) -> dict:
    try:
        logging.info("Starting article processing with verification")
        _emit_step(log_step, "Generating categories and tags")

        logging.info("Generating and verifying category/tags...")
        cat_tags = get_category_and_tags(text)
        verified_cat_tags = verify_category_tags(text, cat_tags)
        _emit_step(log_step, "Categories and tags generated")

        _emit_step(log_step, "Generating title and intro")
        logging.info("Generating and verifying title/intro...")
        title_intro = get_title_and_intro(text)
        verified_title_intro = verify_title_intro(text, title_intro)
        _emit_step(log_step, "Title and intro generated")

        _emit_step(log_step, "Generating summary")
        logging.info("Generating and verifying summary...")
        summary = get_summary(
            text,
            title=verified_title_intro.get("title"),
            intro=verified_title_intro.get("intro"),
        )
        verified_summary = verify_summary(
            text,
            summary,
            title=verified_title_intro.get("title"),
            intro=verified_title_intro.get("intro"),
        )
        _emit_step(log_step, "Summary generated")

        article_data = {
            "category": verified_cat_tags.get("category"),
            "tags": verified_cat_tags.get("tags", []),
            "title": verified_title_intro.get("title"),
            "intro": verified_title_intro.get("intro"),
            "summary": verified_summary.get("summary"),
        }
        _emit_step(log_step, "Article metadata verification completed")

        logging.info("Article processing with verification completed successfully")
        logging.debug("Final verified article data: %s", article_data)
        return article_data

    except Exception as exc:
        logging.error("Error in process_article with verification: %s", str(exc), exc_info=True)
        return {
            "category": "",
            "tags": [],
            "title": "",
            "intro": "",
            "summary": "",
            "political_orientation": {},
            "facts": [],
        }
