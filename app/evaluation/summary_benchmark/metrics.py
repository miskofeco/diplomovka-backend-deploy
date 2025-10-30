import math
import re
from collections import Counter
from typing import Dict, List, Tuple


TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Convert text into a list of lowercase tokens."""
    if not text:
        return []
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token.strip()]


def _ngrams(tokens: List[str], n: int) -> Counter:
    if n <= 0 or n > len(tokens):
        return Counter()
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def compute_bleu(candidate: str, reference: str, max_n: int = 4, smoothing: float = 1e-9) -> float:
    """Compute a simple BLEU score between candidate and reference summaries."""
    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)

    if not cand_tokens:
        return 0.0

    weights = [1.0 / max_n] * max_n
    log_precision_sum = 0.0

    for n in range(1, max_n + 1):
        ref_counts = _ngrams(ref_tokens, n)
        cand_counts = _ngrams(cand_tokens, n)

        if not cand_counts:
            return 0.0

        overlap = sum(min(count, ref_counts[ng]) for ng, count in cand_counts.items())
        total = sum(cand_counts.values())
        precision = (overlap + smoothing) / (total + smoothing)
        log_precision_sum += weights[n - 1] * math.log(precision)

    ref_len = len(ref_tokens)
    cand_len = len(cand_tokens)
    if cand_len == 0:
        return 0.0

    if cand_len > ref_len:
        brevity_penalty = 1.0
    else:
        brevity_penalty = math.exp(1 - ref_len / max(cand_len, 1))

    return brevity_penalty * math.exp(log_precision_sum)


def _precision_recall_f1(overlap: int, ref_total: int, cand_total: int) -> Tuple[float, float, float]:
    recall = overlap / ref_total if ref_total else 0.0
    precision = overlap / cand_total if cand_total else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def _rouge_n(candidate_tokens: List[str], reference_tokens: List[str], n: int) -> Dict[str, float]:
    ref_counts = _ngrams(reference_tokens, n)
    cand_counts = _ngrams(candidate_tokens, n)

    overlap = sum(min(count, cand_counts[ng]) for ng, count in ref_counts.items())
    ref_total = sum(ref_counts.values())
    cand_total = sum(cand_counts.values())

    precision, recall, f1 = _precision_recall_f1(overlap, ref_total, cand_total)
    return {"precision": precision, "recall": recall, "f1": f1}


def _lcs_length(x: List[str], y: List[str]) -> int:
    if not x or not y:
        return 0

    dp = [[0] * (len(y) + 1) for _ in range(len(x) + 1)]
    for i in range(len(x)):
        for j in range(len(y)):
            if x[i] == y[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]


def _rouge_l(candidate_tokens: List[str], reference_tokens: List[str]) -> Dict[str, float]:
    lcs = _lcs_length(candidate_tokens, reference_tokens)
    ref_total = len(reference_tokens)
    cand_total = len(candidate_tokens)

    precision, recall, f1 = _precision_recall_f1(lcs, ref_total, cand_total)
    return {"precision": precision, "recall": recall, "f1": f1}


def compute_rouge_scores(candidate: str, reference: str) -> Dict[str, Dict[str, float]]:
    """Compute ROUGE-1, ROUGE-2 and ROUGE-L scores."""
    candidate_tokens = tokenize(candidate)
    reference_tokens = tokenize(reference)

    if not candidate_tokens or not reference_tokens:
        return {
            "rouge-1": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "rouge-2": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "rouge-l": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        }

    rouge_1 = _rouge_n(candidate_tokens, reference_tokens, 1)
    rouge_2 = _rouge_n(candidate_tokens, reference_tokens, 2)
    rouge_l = _rouge_l(candidate_tokens, reference_tokens)

    return {"rouge-1": rouge_1, "rouge-2": rouge_2, "rouge-l": rouge_l}

