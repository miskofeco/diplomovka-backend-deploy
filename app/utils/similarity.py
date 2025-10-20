import logging
import re
import unicodedata
from collections import Counter

import numpy as np
from sqlalchemy import text

from data.db import SessionLocal
from app.utils.vectorstore import get_embedding


TOKEN_PATTERN = re.compile(r"\b[\w][\w'-]*\b", flags=re.UNICODE)


def strip_diacritics(value: str) -> str:
    """Return a lower-cased token without Slovak diacritics for easier comparisons."""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    ).lower()


# Slovak stopwords stored in diacritic-free form for consistent comparisons.
STOPWORDS = {
    "a", "aby", "aj", "ak", "ako", "ale", "alebo", "ani", "aspon", "avsak", "az", "bez",
    "bol", "bola", "boli", "bolo", "bud", "bude", "budu", "by", "byt", "cez", "ci", "co",
    "cize", "do", "este", "ho", "iba", "ich", "inak", "iny", "ja", "je", "jej", "jemu",
    "jeho", "ju", "k", "kam", "ked", "kedze", "kde", "keby", "kolko", "ktora", "ktore",
    "ktori", "ktory", "ktoru", "ktoreho", "ktorej", "ktorom", "ktorych", "ktorou",
    "ktosi", "kto", "lebo", "len", "ma", "maju", "mal", "mala", "mali", "malo", "mam",
    "mame", "mate", "medzi", "mi", "mna", "mnou", "moze", "mozu", "mus", "musi",
    "musime", "musite", "my", "na", "nad", "naco", "najma", "napr", "nas", "nasa",
    "nasich", "nasim", "nase", "nasi", "nasu", "ne", "nebo", "nebol", "nebola", "neboli",
    "nebolo", "nech", "nechce", "nechcem", "nej", "nejsu", "nemaju", "nemal", "nemame",
    "nemusi", "nie", "nijako", "nieco", "niekto", "nik", "nikto", "o", "od", "okolo",
    "okrem", "on", "ona", "ono", "oni", "ony", "po", "pod", "podla", "pokial", "potom",
    "pre", "pred", "pri", "pricom", "proti", "s", "sa", "seba", "sem", "si", "sme",
    "svoj", "svoja", "svoje", "svojich", "svojim", "svojmu", "som", "ste", "su", "tak",
    "taka", "take", "taki", "takto", "taky", "takze", "tam", "te", "ten", "tento", "tie",
    "tiez", "to", "toto", "tu", "tym", "tymto", "uz", "v", "vam", "vas", "vasa", "vase",
    "vasi", "vasej", "vasu", "vsak", "vsetci", "vsetko", "vy", "z", "za", "zo", "zatial",
    "ze", "zeby",
}

SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3
MAX_KEYWORDS = 30
DEFAULT_KEYWORD_THRESHOLD = 0.35
DEFAULT_MIN_KEYWORD_OVERLAP = 3


def extract_keywords(text: str, max_keywords: int = MAX_KEYWORDS) -> list[str]:
    """Extract a ranked list of keywords based on term frequency."""
    if not text:
        return []

    tokens = TOKEN_PATTERN.findall(text.lower())
    filtered = []
    for token in tokens:
        normalized = strip_diacritics(token)
        if len(normalized) <= 2:
            continue
        if normalized in STOPWORDS:
            continue
        if not any(char.isalpha() for char in normalized):
            continue
        filtered.append(normalized)

    if not filtered:
        return []

    counts = Counter(filtered)
    ranked = [word for word, _ in counts.most_common(max_keywords)]
    return ranked


def keyword_overlap_score(base_keywords: list[str], candidate_keywords: list[str]) -> tuple[float, int]:
    """Calculate overlap score and count between two keyword sets."""
    if not base_keywords or not candidate_keywords:
        return 0.0, 0

    base_set = set(base_keywords[:MAX_KEYWORDS])
    candidate_set = set(candidate_keywords[:MAX_KEYWORDS])

    if not base_set or not candidate_set:
        return 0.0, 0

    overlap = base_set & candidate_set
    union = base_set | candidate_set
    overlap_count = len(overlap)
    if not union:
        return 0.0, overlap_count

    score = overlap_count / len(union)
    return score, overlap_count


def find_similar_article(
    article_summary: str,
    threshold: float = 0.85,
    keyword_threshold: float = DEFAULT_KEYWORD_THRESHOLD,
    min_keyword_overlap: int = DEFAULT_MIN_KEYWORD_OVERLAP,
):
    """Compare a summary against stored article summaries to find near-duplicates.

    Returns a dict with:
        - article: matching article dict (id, summary, title) if threshold met, else None
        - score: best combined similarity score observed
        - candidate_title: title of closest article even if below threshold
        - candidate_id: id of closest article even if below threshold
    """

    # Generate the embedding for the new article summary
    new_embedding = get_embedding(article_summary)
    if new_embedding is None:
        return {"article": None, "score": 0.0, "candidate_title": None, "candidate_id": None}

    new_embedding = np.array(new_embedding, dtype=np.float32)
    new_keywords = extract_keywords(article_summary)

    with SessionLocal() as session:
        return extracted_articles(
            session,
            new_embedding,
            new_keywords,
            threshold,
            keyword_threshold,
            min_keyword_overlap,
        )


def extracted_articles(
    session,
    new_embedding: np.ndarray,
    new_keywords: list[str],
    semantic_threshold: float,
    keyword_threshold: float,
    min_keyword_overlap: int,
):
    # Fetch stored embeddings from database along with titles
    result = session.execute(
        text(
            """
            SELECT ae.id, ae.summary, ae.embedding, a.title
            FROM article_embeddings ae
            LEFT JOIN articles a ON a.id = ae.id
            """
        )
    )
    stored_articles = result.fetchall()

    most_similar = None
    highest_combined_score = 0.0
    best_candidate = None
    best_candidate_score = 0.0

    # Compare with stored embeddings
    for article_id, summary, stored_embedding, stored_title in stored_articles:
        if not stored_embedding:
            continue

        stored_embedding = np.array(stored_embedding)
        if stored_embedding.size == 0:
            continue

        new_norm = np.linalg.norm(new_embedding)
        stored_norm = np.linalg.norm(stored_embedding)
        if new_norm == 0 or stored_norm == 0:
            continue

        similarity = float(np.dot(new_embedding, stored_embedding) / (new_norm * stored_norm))

        candidate_keywords = extract_keywords(summary or "")
        keyword_score, overlap_count = keyword_overlap_score(new_keywords, candidate_keywords)

        keywords_available = bool(new_keywords) and bool(candidate_keywords)
        meets_keyword_requirement = (
            not keywords_available
            or (
                keyword_score >= keyword_threshold
                and overlap_count >= min_keyword_overlap
            )
        )

        combined_score = (SEMANTIC_WEIGHT * similarity) + (KEYWORD_WEIGHT * keyword_score)

        if combined_score > best_candidate_score:
            best_candidate_score = combined_score
            best_candidate = {
                "id": article_id,
                "summary": summary,
                "title": stored_title,
            }

        if similarity >= semantic_threshold and meets_keyword_requirement:
            if combined_score > highest_combined_score:
                highest_combined_score = combined_score
                most_similar = {"id": article_id, "summary": summary, "title": stored_title}
        else:
            logging.debug(
                "Skipping article %s due to low similarity or keyword overlap "
                "(semantic=%.3f, keyword=%.3f, overlap=%s)",
                article_id,
                similarity,
                keyword_score,
                overlap_count,
            )

    if most_similar:
        return {
            "article": most_similar,
            "score": highest_combined_score,
            "candidate_title": most_similar.get("title"),
            "candidate_id": most_similar.get("id"),
        }

    return {
        "article": None,
        "score": best_candidate_score,
        "candidate_title": (best_candidate or {}).get("title"),
        "candidate_id": (best_candidate or {}).get("id"),
    }
