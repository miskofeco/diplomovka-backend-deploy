import json
import re
from typing import List, Tuple

from .config import (
    MAM_CRITIQUE_PASSES,
    MAM_DETECTOR_PASSES,
    MAM_PREFER_CONSISTENT_ON_TIE,
    MAM_REFINE_PASSES,
    generate_json,
    generate_text,
)
from .prompts import (
    MAM_BASELINE_EVENTS_SYSTEM,
    MAM_BASELINE_EVENTS_USER,
    MAM_BASELINE_FROM_EVENTS_ASSISTANT,
    MAM_BASELINE_FROM_EVENTS_SYSTEM,
    MAM_BASELINE_FROM_EVENTS_USER,
    MAM_CRITIQUE_RERANK_SYSTEM,
    MAM_CRITIQUE_RERANK_USER,
    MAM_CRITIQUE_SYSTEM,
    MAM_CRITIQUE_USER,
    MAM_DETECT_SYSTEM,
    MAM_DETECT_USER,
    MAM_REFINE_SYSTEM,
    MAM_REFINE_USER,
    MAM_SUMMARY_RERANK_SYSTEM,
    MAM_SUMMARY_RERANK_USER,
)


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _normalize_yes_no(answer_raw: str, fallback: str) -> str:
    normalized = (answer_raw or "").lower().strip()
    if normalized in {"yes", "true", "ano", "áno", "consistent"}:
        return "yes"
    if normalized in {"no", "false", "nie", "inconsistent"}:
        return "no"
    text = (fallback or "").lower()
    if "no" in text or "nie" in text:
        return "no"
    if "yes" in text or "ano" in text or "áno" in text:
        return "yes"
    return "no"


def _normalize_rerank_answer(parsed: dict, fallback: str) -> str:
    raw = ""
    if isinstance(parsed, dict):
        raw = str(parsed.get("answer", parsed.get("choice", ""))).strip()
    if raw not in {"1", "2"}:
        text = fallback or ""
        raw = "2" if "2" in text and "1" not in text[-5:] else "1"
    return raw


def generate_baseline_summary(text: str) -> Tuple[str, str]:
    events = generate_text(
        MAM_BASELINE_EVENTS_SYSTEM,
        MAM_BASELINE_EVENTS_USER.format(document=text),
        temperature=0.2,
    )
    summary = generate_text(
        MAM_BASELINE_FROM_EVENTS_SYSTEM,
        MAM_BASELINE_FROM_EVENTS_USER.format(events=events, document=text),
        temperature=0.4,
        assistant_message=MAM_BASELINE_FROM_EVENTS_ASSISTANT,
    )
    return summary.strip(), events.strip()


def detect_inconsistencies(text: str, summary: str) -> Tuple[List[str], List[bool]]:
    sentences = _split_sentences(summary)
    flags: List[bool] = []

    for sentence in sentences:
        yes_count = 0
        no_count = 0
        for _ in range(max(1, MAM_DETECTOR_PASSES)):
            payload = generate_json(
                MAM_DETECT_SYSTEM,
                MAM_DETECT_USER.format(document=text, sentence=sentence),
                temperature=0.1,
            )
            answer_raw = ""
            if isinstance(payload, dict):
                answer_raw = str(payload.get("answer", "")).strip()
            answer = _normalize_yes_no(answer_raw, json.dumps(payload))
            if answer == "yes":
                yes_count += 1
            elif answer == "no":
                no_count += 1
        inconsistent = no_count > yes_count
        if no_count == yes_count:
            inconsistent = not MAM_PREFER_CONSISTENT_ON_TIE
        flags.append(inconsistent)

    return sentences, flags


def _select_best_critique(text: str, summary: str, candidates: List[str]) -> str:
    best = candidates[0]
    for contender in candidates[1:]:
        payload = generate_json(
            MAM_CRITIQUE_RERANK_SYSTEM,
            MAM_CRITIQUE_RERANK_USER.format(
                document=text,
                summary=summary,
                critique1=best,
                critique2=contender,
            ),
            temperature=0.1,
        )
        answer = _normalize_rerank_answer(payload, json.dumps(payload))
        if answer == "2":
            best = contender
    return best


def collect_critiques(text: str, summary: str, sentences: List[str], flags: List[bool]) -> List[str]:
    feedback_lines: List[str] = []
    for idx, inconsistent in enumerate(flags):
        if not inconsistent:
            continue
        sentence = sentences[idx]
        candidates: List[str] = []
        for _ in range(max(1, MAM_CRITIQUE_PASSES)):
            critique = generate_text(
                MAM_CRITIQUE_SYSTEM,
                MAM_CRITIQUE_USER.format(document=text, summary=summary, sentence=sentence),
                temperature=0.3,
            )
            if critique.strip():
                candidates.append(critique.strip())
        if not candidates:
            continue
        best = _select_best_critique(text, summary, candidates)
        feedback_lines.append(f"Sentence {idx + 1}: {best}")
    return feedback_lines


def refine_summary(text: str, baseline_summary: str, feedback: str) -> List[str]:
    candidates = [baseline_summary]
    for _ in range(max(1, MAM_REFINE_PASSES)):
        refined = generate_text(
            MAM_REFINE_SYSTEM,
            MAM_REFINE_USER.format(document=text, summary=baseline_summary, feedback=feedback),
            temperature=0.4,
        )
        if refined.strip():
            candidates.append(refined.strip())
    return candidates


def rerank_summaries(text: str, candidates: List[str]) -> str:
    if len(candidates) == 1:
        return candidates[0]
    best = candidates[0]
    for contender in candidates[1:]:
        payload = generate_json(
            MAM_SUMMARY_RERANK_SYSTEM,
            MAM_SUMMARY_RERANK_USER.format(document=text, summary1=best, summary2=contender),
            temperature=0.1,
        )
        answer = _normalize_rerank_answer(payload, json.dumps(payload))
        if answer == "2":
            best = contender
    return best
