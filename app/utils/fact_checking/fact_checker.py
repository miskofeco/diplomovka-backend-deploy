from datetime import datetime, timezone
import logging
import json
import re
from typing import Any, Dict, List

from .client import CLIENT, FACT_CHECK_MODEL
from .parser import safe_json
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


def _strip_closing_sentence(summary: str) -> str:
    if not summary:
        return summary
    if "Záver:" in summary:
        return summary.split("Záver:")[0].strip()
    return summary.strip()


def _normalize_fact_items(raw_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    normalized = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact", "")).strip()
        source_url = item.get("source_url")
        source_title = item.get("source_title")
        status = str(item.get("status", "")).strip().lower()

        source_url_clean = str(source_url).strip() if source_url else ""
        if source_url_clean and not source_url_clean.startswith(("http://", "https://")):
            source_url_clean = ""

        if not source_url_clean:
            status = "not_found"
            source_title = None
        elif status not in {"found", "not_found"}:
            status = "found"

        normalized.append(
            {
                "fact": fact,
                "source_url": source_url_clean or None,
                "source_title": source_title,
                "status": status,
            }
        )
    return normalized


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "") or ""
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        if not isinstance(content, list):
            continue

        for part in content:
            part_text = getattr(part, "text", None)
            if part_text is None and isinstance(part, dict):
                part_text = part.get("text")
            if isinstance(part_text, str) and part_text.strip():
                chunks.append(part_text.strip())

    return "\n".join(chunks).strip()


def _fallback_facts_from_summary(summary: str, max_facts: int) -> List[Dict[str, Any]]:
    # Keep a deterministic fallback so frontend always has explicit "not found" facts
    # when external search output is malformed.
    candidates = re.split(r"(?<=[.!?])\s+", summary.strip())
    facts: List[Dict[str, Any]] = []
    for sentence in candidates:
        cleaned = sentence.strip()
        if len(cleaned) < 25:
            continue
        facts.append(
            {
                "fact": cleaned,
                "source_url": None,
                "source_title": None,
                "status": "not_found",
            }
        )
        if len(facts) >= max_facts:
            break
    return facts


def _extract_search_sources(response: Any) -> List[Dict[str, str]]:
    sources: List[Dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None)
        if item_type is None and isinstance(item, dict):
            item_type = item.get("type")
        if item_type != "web_search_call":
            continue

        action = getattr(item, "action", None)
        if action is None and isinstance(item, dict):
            action = item.get("action")

        raw_sources = None
        if action is not None:
            raw_sources = getattr(action, "sources", None)
            if raw_sources is None and isinstance(action, dict):
                raw_sources = action.get("sources")

        if not isinstance(raw_sources, list):
            continue

        for source in raw_sources:
            if isinstance(source, dict):
                url = str(source.get("url", "")).strip()
                title = str(source.get("title", "")).strip()
            else:
                url = str(getattr(source, "url", "") or "").strip()
                title = str(getattr(source, "title", "") or "").strip()

            if not url.startswith(("http://", "https://")):
                continue
            if url in seen_urls:
                continue

            seen_urls.add(url)
            sources.append({"url": url, "title": title})

    return sources


def _assign_distinct_sources(
    facts: List[Dict[str, Any]],
    sources: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    if not facts:
        return facts

    source_pool = [
        source for source in sources
        if source.get("url", "").startswith(("http://", "https://"))
    ]
    if not source_pool:
        return facts

    used_urls: set[str] = set()
    source_index = 0

    # Keep already assigned unique URLs first.
    for fact in facts:
        existing_url = str(fact.get("source_url") or "").strip()
        if existing_url and existing_url not in used_urls:
            used_urls.add(existing_url)
            fact["status"] = "found"
            continue
        fact["source_url"] = None
        fact["source_title"] = None
        fact["status"] = "not_found"

    for fact in facts:
        if fact.get("source_url"):
            continue

        while source_index < len(source_pool):
            candidate = source_pool[source_index]
            source_index += 1
            candidate_url = str(candidate.get("url") or "").strip()
            if not candidate_url or candidate_url in used_urls:
                continue
            used_urls.add(candidate_url)
            fact["source_url"] = candidate_url
            fact["source_title"] = candidate.get("title") or None
            fact["status"] = "found"
            break

    return facts


def _ensure_facts_in_slovak(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not facts:
        return facts

    fact_texts = [str(fact.get("fact", "")).strip() for fact in facts]
    if not any(fact_texts):
        for fact in facts:
            fact["fact"] = "Nepodarilo sa vygenerovať slovenský fakt."
        return facts

    prompt = (
        "Preveď všetky tvrdenia do spisovnej slovenčiny.\n"
        "- Zachovaj význam.\n"
        "- Nepouži iný jazyk.\n"
        "- Vráť iba JSON bez markdownu.\n"
        "Formát:\n"
        '{"facts": ["..."]}\n'
        f"Vstupné tvrdenia:\n{json.dumps(fact_texts, ensure_ascii=False)}"
    )

    try:
        response = CLIENT.responses.create(
            model=FACT_CHECK_MODEL,
            instructions=(
                "Si jazykový editor. Výstup musí byť výhradne v slovenčine "
                "a vo validnom JSON."
            ),
            input=prompt,
            max_output_tokens=500,
        )
        translated_payload = safe_json(_extract_response_text(response))
        translated_items = translated_payload.get("facts")
    except Exception as exc:
        logging.warning("Failed to normalize fact language to Slovak: %s", exc)
        translated_items = None

    for idx, fact in enumerate(facts):
        translated = ""
        if isinstance(translated_items, list) and idx < len(translated_items):
            translated = str(translated_items[idx] or "").strip()
        if translated:
            fact["fact"] = translated
        else:
            # Strict Slovak-only guardrail for persisted facts.
            fact["fact"] = "Nepodarilo sa spoľahlivo vytvoriť slovenské znenie faktu."

    return facts


def _create_fact_check_response(prompt: str) -> Any:
    params = {
        "model": FACT_CHECK_MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": 800,
    }

    try:
        return CLIENT.responses.create(
            **params,
            tool_choice="required",
        )
    except Exception as exc:
        logging.warning(
            "Fact-check with required tool_choice failed, retrying with auto: %s",
            exc,
        )
        return CLIENT.responses.create(
            **params,
            tool_choice="auto",
        )


def _compute_overall_status(facts: List[Dict[str, Any]]) -> str:
    if not facts:
        return "Neoverene fakty"

    found_count = sum(1 for fact in facts if fact.get("status") == "found")
    if found_count == len(facts):
        return "Overene fakty"
    if found_count == 0:
        return "Neoverene fakty"
    return "Ciastocne overene fakty"


def fact_check_summary(summary: str, max_facts: int = 5) -> Dict[str, Any]:
    if max_facts <= 0:
        max_facts = 1
    if max_facts > 8:
        max_facts = 8

    cleaned_summary = _strip_closing_sentence(summary or "")
    if not cleaned_summary:
        return {
            "status": "Neoverene fakty",
            "facts": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "model": FACT_CHECK_MODEL,
        }

    prompt = USER_PROMPT_TEMPLATE.format(summary=cleaned_summary, max_facts=max_facts)

    response = _create_fact_check_response(prompt)

    output_text = _extract_response_text(response)

    payload = safe_json(output_text)
    facts = _normalize_fact_items(payload.get("facts"))
    if max_facts and len(facts) > max_facts:
        facts = facts[:max_facts]

    if not facts:
        logging.warning(
            "Fact-check output for model %s had no parsable facts; using summary fallback.",
            FACT_CHECK_MODEL,
        )
        facts = _fallback_facts_from_summary(cleaned_summary, max_facts=max_facts)

    # Attach discovered search sources and prefer distinct URLs per fact.
    sources = _extract_search_sources(response)
    facts = _assign_distinct_sources(facts, sources)
    facts = _ensure_facts_in_slovak(facts)

    status = _compute_overall_status(facts)

    return {
        "status": status,
        "facts": facts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "model": FACT_CHECK_MODEL,
    }
