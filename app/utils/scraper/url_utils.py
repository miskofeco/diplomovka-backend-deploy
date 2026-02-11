import re
from urllib.parse import urlsplit, urlunsplit

from .constants import MEDIA_SOURCES


def canonicalize_url(url: str) -> str:
    """Return canonical form of URL without query parameters or fragments."""
    try:
        parts = urlsplit(url.strip())
        if not parts.scheme or not parts.netloc:
            return url

        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()

        path = parts.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/") or "/"

        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return url


def get_source_info(url: str) -> dict | None:
    """Get source information for a given URL"""
    try:
        domain = url.split("//")[-1].split("/")[0]
        return MEDIA_SOURCES.get(domain, {
            "name": domain,
            "orientation": "neutral",
            "logo": None,
            "domain": domain
        })
    except Exception:
        return None
