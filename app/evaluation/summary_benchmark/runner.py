import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = Path(__file__).resolve().parent

if __package__ in (None, ""):
    sys.path.append(str(CURRENT_DIR))
    from metrics import compute_bleu, compute_rouge_scores  # type: ignore
    from providers import SummaryOutput, get_summarizer, parse_model_spec  # type: ignore
else:
    from .metrics import compute_bleu, compute_rouge_scores
    from .providers import SummaryOutput, get_summarizer, parse_model_spec

EVAL_DIR = CURRENT_DIR
DEFAULT_DATASET = EVAL_DIR / "datasets" / "sample_dataset.json"


@dataclass
class SampleResult:
    article_id: str
    summary: str
    reference_summary: Optional[str]
    metrics: Dict[str, Any]
    usage: Dict[str, Any]
    wall_time_seconds: float
    meta: Optional[Dict[str, Any]] = None


@dataclass
class ModelResult:
    provider: str
    model: str
    samples: List[SampleResult] = field(default_factory=list)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)
    aggregate_usage: Dict[str, Any] = field(default_factory=dict)


def load_dataset(dataset_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("Dataset must be a list of objects.")

    if limit is not None:
        payload = payload[:limit]

    normalised = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Dataset item at index {idx} is not an object.")
        article = item.get("article") or item.get("text")
        if not article:
            raise ValueError(f"Dataset item at index {idx} is missing 'article' text.")
        normalised.append(
            {
                "id": str(item.get("id") or idx),
                "article": article,
                "reference_summary": item.get("reference_summary") or item.get("reference") or item.get("golden_summary"),
                "title": item.get("title"),
                "intro": item.get("intro"),
                "meta": _build_meta(item),
            }
        )
    return normalised


def _build_meta(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    meta = {"source": item.get("source"), "url": item.get("url")}
    if all(value in (None, "") for value in meta.values()):
        return None
    return meta


def _initial_usage(provider: str, model: str) -> Dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "api_duration_seconds": 0.0,
        "calls": 0,
        "wall_time_seconds": 0.0,
    }


def _accumulate_usage(aggregate: Dict[str, Any], usage: Dict[str, Any], wall_time: float) -> None:
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            aggregate[key] += value
    api_duration = usage.get("api_duration_seconds") or usage.get("duration_seconds") or 0.0
    if isinstance(api_duration, (int, float)):
        aggregate["api_duration_seconds"] += api_duration
    calls = usage.get("calls") or 0
    if isinstance(calls, (int, float)):
        aggregate["calls"] += int(calls)
    aggregate["wall_time_seconds"] += wall_time


def evaluate_model(provider: str, model_name: str, dataset: List[Dict[str, Any]]) -> ModelResult:
    summarizer = get_summarizer(provider, model_name)
    model_result = ModelResult(provider=provider, model=model_name)

    bleu_scores: List[float] = []
    rouge_scores: Dict[str, List[float]] = {"rouge-1": [], "rouge-2": [], "rouge-l": []}
    aggregate_usage = _initial_usage(provider, model_name)

    for item in dataset:
        article_id = item["id"]
        text = item["article"]
        reference = item.get("reference_summary")
        title = item.get("title")
        intro = item.get("intro")

        summary_output: SummaryOutput = summarizer.summarise(text, title=title, intro=intro)
        summary_text = summary_output.text
        usage_snapshot = summary_output.usage
        wall_clock = summary_output.wall_time_seconds

        _accumulate_usage(aggregate_usage, usage_snapshot, wall_clock)

        metric_payload: Dict[str, Any] = {}
        if reference:
            bleu = compute_bleu(summary_text, reference)
            rouge = compute_rouge_scores(summary_text, reference)
            metric_payload = {"bleu": bleu, "rouge": rouge}
            bleu_scores.append(bleu)
            for rouge_key, value in rouge.items():
                rouge_scores[rouge_key].append(value["f1"])

        model_result.samples.append(
            SampleResult(
                article_id=article_id,
                summary=summary_text,
                reference_summary=reference,
                metrics=metric_payload,
                usage=usage_snapshot,
                wall_time_seconds=wall_clock,
                meta=item.get("meta"),
            )
        )

    aggregate_metrics: Dict[str, Any] = {}
    if bleu_scores:
        aggregate_metrics["mean_bleu"] = sum(bleu_scores) / len(bleu_scores)
    if any(rouge_scores.values()):
        aggregate_metrics["mean_rouge_f1"] = {
            key: (sum(values) / len(values) if values else None) for key, values in rouge_scores.items()
        }

    model_result.aggregate_metrics = aggregate_metrics
    model_result.aggregate_usage = aggregate_usage
    return model_result


def print_model_report(result: ModelResult, verbose: bool = False) -> None:
    print(f"Provider: {result.provider} | Model: {result.model}")
    print(f"  Evaluated samples: {len(result.samples)}")
    if "mean_bleu" in result.aggregate_metrics:
        print(f"  Mean BLEU: {result.aggregate_metrics['mean_bleu']:.4f}")
    if "mean_rouge_f1" in result.aggregate_metrics:
        rouge_payload = result.aggregate_metrics["mean_rouge_f1"]
        for key, value in rouge_payload.items():
            if value is not None:
                print(f"  Mean {key.upper()} F1: {value:.4f}")
    agg = result.aggregate_usage
    print(
        "  Tokens -> prompt: {prompt}, completion: {completion}, total: {total}".format(
            prompt=int(agg.get("prompt_tokens", 0)),
            completion=int(agg.get("completion_tokens", 0)),
            total=int(agg.get("total_tokens", 0)),
        )
    )
    print(
        "  Time -> api: {api:.2f}s, wall: {wall:.2f}s across {calls} calls".format(
            api=float(agg.get("api_duration_seconds", 0.0)),
            wall=float(agg.get("wall_time_seconds", 0.0)),
            calls=int(agg.get("calls", 0)),
        )
    )

    if verbose:
        print("  Detailed samples:")
        for sample in result.samples:
            print(f"    - Article ID: {sample.article_id}")
            print(f"      Wall time: {sample.wall_time_seconds:.2f}s | Usage: {sample.usage}")
            if sample.meta:
                source = sample.meta.get("source")
                url = sample.meta.get("url")
                if source:
                    print(f"      Source: {source}")
                if url:
                    print(f"      URL: {url}")
            if sample.metrics:
                bleu = sample.metrics.get("bleu")
                if bleu is not None:
                    print(f"      BLEU: {bleu:.4f}")
                rouge = sample.metrics.get("rouge")
                if rouge:
                    rouge_desc = ", ".join(f"{k.upper()} F1={v['f1']:.4f}" for k, v in rouge.items())
                    print(f"      {rouge_desc}")
            print()


def serialise_results(results: List[ModelResult]) -> List[Dict[str, Any]]:
    payload = []
    for model_result in results:
        payload.append(
            {
                "provider": model_result.provider,
                "model": model_result.model,
                "aggregate_metrics": model_result.aggregate_metrics,
                "aggregate_usage": model_result.aggregate_usage,
                "samples": [
                    {
                        "article_id": sample.article_id,
                        "summary": sample.summary,
                        "reference_summary": sample.reference_summary,
                        "metrics": sample.metrics,
                        "usage": sample.usage,
                        "wall_time_seconds": sample.wall_time_seconds,
                        "meta": sample.meta,
                    }
                    for sample in model_result.samples
                ],
            }
        )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate article summarisation quality across multiple LLM models."
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="List of OpenAI model identifiers to evaluate. Example: gpt-4o-mini gpt-4.1-mini",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Path to dataset JSON file (default: {DEFAULT_DATASET}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on the number of samples to evaluate for quick experiments.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write detailed JSON results.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-sample metric and usage details.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset, limit=args.limit)

    results: List[ModelResult] = []
    model_specs: List[Tuple[str, str]] = [parse_model_spec(spec) for spec in args.models]
    for provider, model_name in model_specs:
        model_result = evaluate_model(provider, model_name, dataset)
        print_model_report(model_result, verbose=args.verbose)
        print()
        results.append(model_result)

    if args.output:
        serialised = serialise_results(results)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(serialised, handle, ensure_ascii=False, indent=2)
        print(f"Detailed results written to {args.output}")


if __name__ == "__main__":
    main()
