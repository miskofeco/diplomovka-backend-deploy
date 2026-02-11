from datetime import datetime, timezone
import logging
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

    response = CLIENT.responses.create(
        model=FACT_CHECK_MODEL,
        instructions=SYSTEM_PROMPT,
        input=prompt,
        tools=[{"type": "web_search"}],
        tool_choice="auto",
        include=["web_search_call.action.sources"],
        max_output_tokens=800,
    )

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

    # Attach discovered search sources if model response did not map them directly.
    sources = _extract_search_sources(response)
    if sources:
        source_index = 0
        for fact in facts:
            if fact.get("source_url"):
                continue
            if source_index >= len(sources):
                break
            source = sources[source_index]
            source_index += 1
            fact["source_url"] = source["url"]
            fact["source_title"] = source["title"] or None
            fact["status"] = "found"

    status = _compute_overall_status(facts)

    return {
        "status": status,
        "facts": facts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "model": FACT_CHECK_MODEL,
    }
