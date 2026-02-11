import logging
import sys

logger = logging.getLogger("app.scraper")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _article_label(title: str | None, url: str | None) -> str:
    safe_title = (title or "Bez názvu").strip()
    safe_url = (url or "bez-url").strip()
    return f"{safe_title} ({safe_url})"


def log_article_step(title: str | None, url: str | None, message: str, level: int = logging.INFO) -> None:
    logger.log(level, "%s - %s", message, _article_label(title, url))
