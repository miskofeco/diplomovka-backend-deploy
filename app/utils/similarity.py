import logging
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

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

SEMANTIC_WEIGHT = 0.4
SUMMARY_WEIGHT = 0.25
KEYWORD_WEIGHT = 0.2
BODY_WEIGHT = 0.1
TAG_WEIGHT = 0.05
MAX_KEYWORDS = 30
DEFAULT_KEYWORD_THRESHOLD = 0.35
DEFAULT_MIN_KEYWORD_OVERLAP = 3
DEFAULT_COMBINED_THRESHOLD = 0.7
SEMANTIC_SIMILARITY_THRESHOLD = 0.82
SUMMARY_SIMILARITY_THRESHOLD = 0.6
BODY_SIMILARITY_THRESHOLD = 0.5
ARTICLE_TEXT_EMBED_LIMIT = 4000

QUERY_SEMANTIC_WEIGHT = 0.6
QUERY_KEYWORD_WEIGHT = 0.25
QUERY_TITLE_WEIGHT = 0.1
QUERY_TEXT_WEIGHT = 0.05
QUERY_COMBINED_THRESHOLD = 0.45


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


def normalize_text(value: str | None) -> str:
    """Normalize text for textual similarity comparisons."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def enrich_keywords_with_tags(keywords: list[str], tags: list[str] | None) -> list[str]:
    """Merge normalized tags into keyword list keeping original order."""
    if not tags:
        return keywords
    enhanced = list(keywords)
    seen = {kw for kw in keywords}
    for tag in tags:
        normalized = strip_diacritics(tag) if tag else ""
        if not normalized or normalized in seen:
            continue
        enhanced.append(normalized)
        seen.add(normalized)
    return enhanced


def tag_overlap(new_tags: set[str], candidate_tags: list[str] | None) -> float:
    """Compute Jaccard overlap between normalized tag sets."""
    if not new_tags or not candidate_tags:
        return 0.0

    candidate_normalized = {
        strip_diacritics(tag) for tag in candidate_tags if tag
    }
    if not candidate_normalized:
        return 0.0

    intersection = new_tags & candidate_normalized
    union = new_tags | candidate_normalized
    if not union:
        return 0.0
    return len(intersection) / len(union)


def tokenize_for_overlap(text: str) -> set[str]:
    """Tokenize text into a set of normalized tokens suitable for overlap comparisons."""
    if not text:
        return set()
    tokens = TOKEN_PATTERN.findall(text.lower())
    normalized_tokens = {
        strip_diacritics(token)
        for token in tokens
        if len(strip_diacritics(token)) > 2 and any(char.isalpha() for char in token)
    }
    return normalized_tokens


def _row_to_article_dict(row) -> dict:
    """Convert a DB row into an article dictionary."""
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


def find_similar_article(
    article_summary: str,
    article_text: str | None = None,
    *,
    article_title: str | None = None,
    article_tags: list[str] | None = None,
    threshold: float = DEFAULT_COMBINED_THRESHOLD,
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

    summary_embedding_raw = get_embedding(article_summary)
    if summary_embedding_raw is None:
        logging.warning("Failed to obtain embedding for new article summary")
        return {"article": None, "score": 0.0, "candidate_title": None, "candidate_id": None}

    summary_embedding = np.array(summary_embedding_raw, dtype=np.float32)

    body_embedding = None
    if article_text:
        truncated_text = article_text[:ARTICLE_TEXT_EMBED_LIMIT]
        body_embedding_raw = get_embedding(truncated_text)
        if body_embedding_raw is not None:
            body_embedding = np.array(body_embedding_raw, dtype=np.float32)

    keyword_source = article_summary
    if article_text:
        keyword_source = f"{article_summary}\n{article_text[:ARTICLE_TEXT_EMBED_LIMIT]}"

    new_keywords = enrich_keywords_with_tags(
        extract_keywords(keyword_source),
        article_tags
    )
    normalized_summary = normalize_text(article_summary)
    normalized_tags = {strip_diacritics(tag) for tag in (article_tags or []) if tag}

    with SessionLocal() as session:
        return extracted_articles(
            session=session,
            summary_embedding=summary_embedding,
            summary_text=normalized_summary,
            new_keywords=new_keywords,
            article_text_embedding=body_embedding,
            article_tags=normalized_tags,
            combined_threshold=threshold,
            keyword_threshold=keyword_threshold,
            min_keyword_overlap=min_keyword_overlap,
        )


def extracted_articles(
    session,
    summary_embedding: np.ndarray,
    summary_text: str,
    new_keywords: list[str],
    article_text_embedding: np.ndarray | None,
    article_tags: set[str],
    combined_threshold: float,
    keyword_threshold: float,
    min_keyword_overlap: int,
):
    """Evaluate stored articles against new content using multiple similarity signals."""
    result = session.execute(
        text(
            """
            SELECT ae.id, ae.summary, ae.embedding, a.title, a.tags
            FROM article_embeddings ae
            LEFT JOIN articles a ON a.id = ae.id
            """
        )
    )
    stored_articles = result.fetchall()

    most_similar = None
    highest_combined_score = 0.0
    matched_metrics = None

    best_candidate = None
    best_candidate_score = 0.0
    best_candidate_metrics = None

    new_norm = np.linalg.norm(summary_embedding)
    if new_norm == 0:
        logging.warning("Summary embedding norm is zero; skipping similarity search.")
        return {
            "article": None,
            "score": 0.0,
            "candidate_title": None,
            "candidate_id": None,
            "metrics": {"best_match": None, "closest_candidate": None},
        }

    for article_id, summary, stored_embedding, stored_title, stored_tags in stored_articles:
        if not stored_embedding:
            continue

        stored_embedding = np.array(stored_embedding, dtype=np.float32)
        if stored_embedding.size == 0:
            continue

        stored_norm = np.linalg.norm(stored_embedding)
        if stored_norm == 0:
            continue

        semantic_similarity = float(
            np.dot(summary_embedding, stored_embedding) / (new_norm * stored_norm)
        )

        candidate_summary_normalized = normalize_text(summary)
        summary_similarity = SequenceMatcher(
            None, summary_text, candidate_summary_normalized
        ).ratio()

        candidate_keywords = enrich_keywords_with_tags(
            extract_keywords(summary or ""),
            stored_tags
        )
        keyword_score, overlap_count = keyword_overlap_score(new_keywords, candidate_keywords)
        keywords_available = bool(new_keywords) and bool(candidate_keywords)
        meets_keyword_requirement = (
            not keywords_available
            or (
                keyword_score >= keyword_threshold
                and overlap_count >= min_keyword_overlap
            )
        )

        if article_text_embedding is not None:
            body_norm = np.linalg.norm(article_text_embedding)
            body_similarity = (
                float(np.dot(article_text_embedding, stored_embedding) / (body_norm * stored_norm))
                if body_norm != 0 else 0.0
            )
        else:
            body_similarity = 0.0

        tag_score = tag_overlap(article_tags, stored_tags) if article_tags else 0.0

        weights = {
            "semantic": SEMANTIC_WEIGHT,
            "summary": SUMMARY_WEIGHT,
            "keyword": KEYWORD_WEIGHT if keywords_available else 0.0,
            "body": BODY_WEIGHT if article_text_embedding is not None else 0.0,
            "tag": TAG_WEIGHT if article_tags else 0.0,
        }
        weight_sum = sum(weights.values()) or 1.0

        combined_score = (
            weights["semantic"] * semantic_similarity
            + weights["summary"] * summary_similarity
            + weights["keyword"] * keyword_score
            + weights["body"] * body_similarity
            + weights["tag"] * tag_score
        ) / weight_sum

        metrics_snapshot = {
            "semantic": round(semantic_similarity, 4),
            "summary": round(summary_similarity, 4),
            "keyword": round(keyword_score, 4),
            "keyword_overlap": overlap_count,
            "body": round(body_similarity, 4),
            "tag": round(tag_score, 4),
            "combined": round(combined_score, 4),
        }

        if combined_score > best_candidate_score:
            best_candidate_score = combined_score
            best_candidate = {
                "id": article_id,
                "summary": summary,
                "title": stored_title,
                "tags": stored_tags,
            }
            best_candidate_metrics = metrics_snapshot

        passes_semantic = semantic_similarity >= SEMANTIC_SIMILARITY_THRESHOLD
        passes_summary = summary_similarity >= SUMMARY_SIMILARITY_THRESHOLD
        passes_body = (article_text_embedding is None) or (body_similarity >= BODY_SIMILARITY_THRESHOLD)
        passes_combined = combined_score >= combined_threshold

        if passes_semantic and passes_summary and passes_body and meets_keyword_requirement and passes_combined:
            if combined_score > highest_combined_score:
                highest_combined_score = combined_score
                most_similar = {
                    "id": article_id,
                    "summary": summary,
                    "title": stored_title,
                    "tags": stored_tags,
                }
                matched_metrics = metrics_snapshot
        else:
            logging.debug(
                "Article %s below thresholds (semantic=%.3f, summary=%.3f, body=%.3f, keywords=%.3f/%s, combined=%.3f)",
                article_id,
                semantic_similarity,
                summary_similarity,
                body_similarity,
                keyword_score,
                overlap_count,
                combined_score,
            )

    if most_similar:
        return {
            "article": most_similar,
            "score": highest_combined_score,
            "candidate_title": most_similar.get("title"),
            "candidate_id": most_similar.get("id"),
            "metrics": {
                "best_match": matched_metrics,
                "closest_candidate": best_candidate_metrics,
            },
        }

    return {
        "article": None,
        "score": best_candidate_score,
        "candidate_title": (best_candidate or {}).get("title"),
        "candidate_id": (best_candidate or {}).get("id"),
        "metrics": {
            "best_match": None,
            "closest_candidate": best_candidate_metrics,
        },
    }


def semantic_query_search(
    session,
    query_embedding: np.ndarray,
    query_text: str,
    limit: int = 20,
) -> list[dict]:
    """Perform semantic search for arbitrary query text using stored article embeddings."""
    if query_embedding.size == 0:
        logging.warning("Empty query embedding supplied; returning no semantic results.")
        return []

    query_norm = np.linalg.norm(query_embedding)
    if query_norm == 0:
        logging.warning("Zero-norm query embedding supplied; returning no semantic results.")
        return []

    normalized_query = normalize_text(query_text)
    query_keywords = extract_keywords(query_text)
    query_tokens = tokenize_for_overlap(query_text)

    articles_query = """
        SELECT 
            a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at,
            ae.embedding
        FROM articles a
        INNER JOIN article_embeddings ae ON a.id = ae.id
        WHERE ae.embedding IS NOT NULL
    """

    result = session.execute(text(articles_query))
    candidates: list[dict] = []

    for row in result:
        stored_embedding = row[9]
        if not stored_embedding:
            continue

        stored_vector = np.array(stored_embedding, dtype=np.float32)
        if stored_vector.size == 0:
            continue

        stored_norm = np.linalg.norm(stored_vector)
        if stored_norm == 0:
            continue

        semantic_similarity = float(np.dot(query_embedding, stored_vector) / (query_norm * stored_norm))

        title = row[1] or ""
        intro = row[2] or ""
        summary = row[3] or ""
        raw_tags = row[6] or []
        tags = raw_tags if isinstance(raw_tags, list) else ([raw_tags] if raw_tags else [])

        title_similarity = SequenceMatcher(
            None,
            normalized_query,
            normalize_text(title),
        ).ratio()

        context_for_keywords = f"{title}\n{intro}\n{summary}"
        candidate_keywords = extract_keywords(context_for_keywords)
        keyword_score, overlap_count = keyword_overlap_score(query_keywords, candidate_keywords)

        article_tokens = tokenize_for_overlap(" ".join([title, intro, summary, " ".join(tags)]))
        token_overlap = (
            len(query_tokens & article_tokens) / len(query_tokens)
            if query_tokens else 0.0
        )

        weights = {
            "semantic": QUERY_SEMANTIC_WEIGHT,
            "keyword": QUERY_KEYWORD_WEIGHT if query_keywords else 0.0,
            "title": QUERY_TITLE_WEIGHT,
            "text": QUERY_TEXT_WEIGHT if query_tokens else 0.0,
        }
        weight_sum = sum(weights.values()) or 1.0

        combined_score = (
            weights["semantic"] * semantic_similarity
            + weights["keyword"] * keyword_score
            + weights["title"] * title_similarity
            + weights["text"] * token_overlap
        ) / weight_sum

        candidates.append(
            {
                "metrics": {
                    "semantic": round(semantic_similarity, 4),
                    "keyword": round(keyword_score, 4),
                    "keyword_overlap": overlap_count,
                    "title": round(title_similarity, 4),
                    "tokens": round(token_overlap, 4),
                    "combined": round(combined_score, 4),
                },
                "data": _row_to_article_dict(row),
            }
        )

    if not candidates:
        return []

    candidates.sort(key=lambda item: item["metrics"]["combined"], reverse=True)

    selected = [
        {
            **candidate["data"],
            "match_score": candidate["metrics"]["combined"],
        }
        for candidate in candidates
        if candidate["metrics"]["combined"] >= QUERY_COMBINED_THRESHOLD
    ][:limit]

    if not selected:
        selected = [
            {
                **candidate["data"],
                "match_score": candidate["metrics"]["combined"],
            }
            for candidate in candidates[:limit]
        ]

    logging.info(
        "Semantic query search evaluated %s candidates; returning %s results.",
        len(candidates),
        len(selected),
    )

    return selected
