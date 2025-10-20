import atexit
import logging
import os
import threading
from typing import Optional

from flask import Flask

from app.services.scraping_service import run_scraping


def _env_flag(name: str, default: str = "false") -> bool:
    """Return True if the env variable is truthy."""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Return integer value from environment with fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logging.warning(
            "Invalid integer value for %s; falling back to %s", name, default
        )
        return default


class ScraperScheduler:
    """Simple background scheduler that triggers scraping in fixed intervals."""

    def __init__(
        self,
        app: Flask,
        interval_seconds: int,
        max_articles_per_page: int,
        max_total_articles: Optional[int],
    ) -> None:
        self.app = app
        self.interval_seconds = interval_seconds
        self.max_articles_per_page = max_articles_per_page
        self.max_total_articles = max_total_articles
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logging.debug("Scraper scheduler already running; skipping start.")
            return

        self._thread = threading.Thread(
            target=self._run_loop, name="ScraperScheduler", daemon=True
        )
        self._thread.start()
        logging.info(
            "Scraper scheduler started (interval=%ss, max_per_page=%s, max_total=%s).",
            self.interval_seconds,
            self.max_articles_per_page,
            self.max_total_articles,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logging.info("Scraper scheduler stopped.")

    # Internal helpers -----------------------------------------------------
    def _run_loop(self) -> None:
        with self.app.app_context():
            self._run_scraping(initial=True)
            while not self._stop_event.wait(self.interval_seconds):
                self._run_scraping(initial=False)

    def _run_scraping(self, *, initial: bool) -> None:
        try:
            logging.info(
                "Scheduled scraping run started (%s).",
                "initial" if initial else "periodic",
            )
            result = run_scraping(
                max_articles_per_page=self.max_articles_per_page,
                max_total_articles=self.max_total_articles,
            )
            summary = result.get("summary", {})
            logging.info(
                "Scheduled scraping run finished. Summary: processed=%s, found=%s, errors=%s",
                summary.get("articles_processed"),
                summary.get("articles_found"),
                summary.get("errors"),
            )
        except Exception as exc:  # pragma: no cover - safeguard against silent failures
            logging.error("Scheduled scraping run failed: %s", exc, exc_info=True)


def init_scraper_scheduler(app: Flask) -> None:
    """Initialise the scraper scheduler when enabled via environment variable."""
    if "scraper_scheduler" in app.extensions:
        logging.debug("Scraper scheduler already initialised; skipping re-initialisation.")
        return

    if not _env_flag("SCRAPER_SCHEDULER_ENABLED", "false"):
        logging.info("Scraper scheduler disabled via environment variable.")
        return

    interval_minutes = _env_int("SCRAPER_SCHEDULER_INTERVAL_MINUTES", 15)
    interval_seconds = max(60, interval_minutes * 60)
    max_per_page = _env_int("SCRAPER_SCHEDULER_MAX_PER_PAGE", 10)

    max_total_env = os.getenv("SCRAPER_SCHEDULER_MAX_TOTAL")
    try:
        max_total: Optional[int] = (
            int(max_total_env) if max_total_env is not None else None
        )
    except ValueError:
        logging.warning(
            "Invalid SCRAPER_SCHEDULER_MAX_TOTAL value '%s'; ignoring.", max_total_env
        )
        max_total = None

    scheduler = ScraperScheduler(
        app=app,
        interval_seconds=interval_seconds,
        max_articles_per_page=max_per_page,
        max_total_articles=max_total,
    )
    scheduler.start()

    app.extensions["scraper_scheduler"] = scheduler
    atexit.register(scheduler.stop)


__all__ = ["init_scraper_scheduler", "ScraperScheduler"]
