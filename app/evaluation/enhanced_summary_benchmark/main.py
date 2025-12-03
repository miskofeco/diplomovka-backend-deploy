import asyncio
import argparse
import json
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from typing import List

from src.dataset import GOLD_STANDARD_DATASET
from src.models import get_client
from src.pipelines import (
    BasicPipeline,
    EnhancedPipeline,
    MamRefinePipeline,
    MultiStepPipeline,
    SelfRefinePipeline,
)
from src.metrics import MetricsEngine

# Load environment variables
load_dotenv()

MAM_REFINE_MODEL_CONFIG = {
    "detectors": ["gpt-4o-mini", "gemini-2.5-flash"],
    "critique": ["gpt-4o-mini", "gemini-2.5-flash"],
    "refine": ["gpt-4o", "gemini-2.5-flash","gpt-4o-mini","gemini-2.5-flash-lite"],
    "rerank": "gemini-2.5-flash",
}


def _safe_avg(values, precision=4):
    if not values:
        return 0.0
    return round(sum(values) / len(values), precision)


def _resolve_total_latency(latencies: dict) -> float:
    if not latencies:
        return 0.0
    if "total_runtime_s" in latencies:
        return latencies["total_runtime_s"]
    if "total_pipeline" in latencies:
        return latencies["total_pipeline"]
    if "total" in latencies:
        return latencies["total"]
    return sum(latencies.values())


def _normalize_inverse(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v - min_v == 0:
        return [1.0 for _ in values]
    return [1 - ((val - min_v) / (max_v - min_v)) for val in values]


async def run_experiment(models: list, approaches: list, dataset: list):
    results_data = []
    metrics_engine = MetricsEngine()

    # Judge model for Approach 4 (Hardcoded to a strong model or same model)
    judge_model = get_client("gpt-4o")

    async def _evaluate_pipeline(pipeline, article_id, topic, article, reference, model_name, approach_label):
        print(f"Spúšťam model {model_name} / prístup {approach_label} pre článok {article_id}...")
        try:
            result = await pipeline.execute(article, reference, topic)
        except Exception as e:
            print(f"!! Chyba pri {model_name} / prístup {approach_label}: {str(e)}")
            return None

        latency_total = _resolve_total_latency(result.metrics.latencies)
        result_dict = {
            "article_id": article_id,
            "article_topic": topic,
            "article_text": article,
            "model": result.model_name,
            "approach": result.approach_name,
            "reference_summary": reference,
            "article_length_chars": len(article),
            "metrics": {
                "bleu": result.metrics.bleu,
                "rouge": {
                    "rouge_1": result.metrics.rouge_1,
                    "rouge_l": result.metrics.rouge_l,
                },
                "bert_score": {
                    "precision": result.metrics.bert_precision,
                    "recall": result.metrics.bert_recall,
                    "f1": result.metrics.bert_f1,
                },
                "tokens": {
                    "input": result.metrics.token_usage.input_tokens,
                    "output": result.metrics.token_usage.output_tokens,
                    "total": result.metrics.token_usage.total_tokens,
                },
                "latencies": {
                    "total_runtime_s": latency_total,
                },
            },
            "intermediate": result.intermediate_artifacts,
            "final_summary": result.final_summary,
        }

        print(
            f"-> Hotovo {model_name}/{approach_label}. BLEU: {result.metrics.bleu:.4f}, "
            f"ROUGE-L: {result.metrics.rouge_l:.4f}, "
            f"BERT P/R/F1: {result.metrics.bert_precision:.4f} / "
            f"{result.metrics.bert_recall:.4f} / {result.metrics.bert_f1:.4f}, "
            f"Čas: {latency_total:.2f}s"
        )
        return result_dict

    for article_entry in dataset:
        article_id = article_entry["id"]
        topic = article_entry["topic"]
        article = article_entry["article"]
        reference = article_entry["reference_summary"]

        print(f"\n=== Článok {article_id} ({topic}) ===")

        article_tasks = []

        for model_name in models:
            print(f"\n--- Testujem model: {model_name} ---")
            client = get_client(model_name)

            pipelines_map = {
                "1": BasicPipeline(client, metrics_engine),
                "2": EnhancedPipeline(client, metrics_engine),
                "3": MultiStepPipeline(client, metrics_engine),
                "4": SelfRefinePipeline(client, judge_model, metrics_engine),
            }

            if "5" in approaches:
                mam_detectors = [get_client(name) for name in MAM_REFINE_MODEL_CONFIG["detectors"]]
                mam_critiques = [get_client(name) for name in MAM_REFINE_MODEL_CONFIG["critique"]]
                mam_refiners = [get_client(name) for name in MAM_REFINE_MODEL_CONFIG["refine"]]
                mam_rerank = get_client(MAM_REFINE_MODEL_CONFIG["rerank"])
                pipelines_map["5"] = MamRefinePipeline(
                    baseline_model=client,
                    detector_models=mam_detectors,
                    critique_models=mam_critiques,
                    refine_models=mam_refiners,
                    rerank_model=mam_rerank,
                    metrics_engine=metrics_engine,
                )

            for approach_id in approaches:
                if approach_id not in pipelines_map:
                    continue
                pipeline = pipelines_map[approach_id]
                article_tasks.append(
                    _evaluate_pipeline(
                        pipeline,
                        article_id,
                        topic,
                        article,
                        reference,
                        model_name,
                        approach_id,
                    )
                )

        task_results = await asyncio.gather(*article_tasks, return_exceptions=False)
        for res in task_results:
            if res:
                results_data.append(res)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_filename = f"evaluation_full_{timestamp}.json"
    summary_filename = f"evaluation_summary_{timestamp}.json"

    dataset_metadata = [
        {
            "id": entry["id"],
            "topic": entry["topic"],
            "article_length_chars": len(entry["article"]),
            "reference_length_chars": len(entry["reference_summary"]),
        }
        for entry in dataset
    ]

    full_report = {
        "evaluation_metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "models_tested": models,
            "approaches_tested": approaches,
            "dataset_size": len(dataset),
            "dataset_articles": dataset_metadata,
        },
        "results": results_data,
    }

    with open(full_filename, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    # Aggregate Summary
    aggregate = defaultdict(lambda: {
        "bleu": [],
        "rouge_1": [],
        "rouge_l": [],
        "bert_precision": [],
        "bert_recall": [],
        "bert_f1": [],
        "input_tokens": [],
        "output_tokens": [],
        "total_tokens": [],
        "latencies": [],
    })

    for item in results_data:
        key = (item["model"], item["approach"])
        metrics = item["metrics"]
        aggregate[key]["bleu"].append(metrics["bleu"])
        aggregate[key]["rouge_1"].append(metrics["rouge"]["rouge_1"])
        aggregate[key]["rouge_l"].append(metrics["rouge"]["rouge_l"])
        aggregate[key]["bert_precision"].append(metrics["bert_score"]["precision"])
        aggregate[key]["bert_recall"].append(metrics["bert_score"]["recall"])
        aggregate[key]["bert_f1"].append(metrics["bert_score"]["f1"])
        aggregate[key]["input_tokens"].append(metrics["tokens"]["input"])
        aggregate[key]["output_tokens"].append(metrics["tokens"]["output"])
        aggregate[key]["total_tokens"].append(metrics["tokens"]["total"])
        aggregate[key]["latencies"].append(metrics["latencies"].get("total_runtime_s", 0.0))

    aggregate_rows = []
    for (model_name, approach_name), stats in aggregate.items():
        entries = len(stats["bleu"])
        aggregate_rows.append({
            "model": model_name,
            "approach": approach_name,
            "num_samples": entries,
            "mean_bleu": _safe_avg(stats["bleu"]),
            "mean_rouge_1": _safe_avg(stats["rouge_1"]),
            "mean_rouge_l": _safe_avg(stats["rouge_l"]),
            "mean_bert_precision": _safe_avg(stats["bert_precision"]),
            "mean_bert_recall": _safe_avg(stats["bert_recall"]),
            "mean_bert_f1": _safe_avg(stats["bert_f1"]),
            "mean_input_tokens": _safe_avg(stats["input_tokens"], precision=2),
            "mean_output_tokens": _safe_avg(stats["output_tokens"], precision=2),
            "mean_total_tokens": _safe_avg(stats["total_tokens"], precision=2),
            "mean_total_latency_s": _safe_avg(stats["latencies"], precision=2),
        })

    time_values = [row["mean_total_latency_s"] for row in aggregate_rows]
    token_values = [row["mean_total_tokens"] for row in aggregate_rows]
    time_scores = _normalize_inverse(time_values)
    token_scores = _normalize_inverse(token_values)

    for idx, row in enumerate(aggregate_rows):
        rouge_avg = (row["mean_bleu"] + row["mean_rouge_l"]) / 2 if row["num_samples"] else 0.0
        time_score = time_scores[idx] if idx < len(time_scores) else 0.0
        token_score = token_scores[idx] if idx < len(token_scores) else 0.0
        efficiency_component = (time_score + token_score) / 2
        performance = 10 * (
            0.75 * row["mean_bert_f1"]
            + 0.15 * rouge_avg
            + 0.10 * efficiency_component
        )
        row["performance_score"] = round(performance, 2)
        row["efficiency_score"] = round(efficiency_component, 4)
        row["mean_rouge_avg"] = round(((row["mean_rouge_1"] + row["mean_rouge_l"]) / 2), 4)

    approach_results = defaultdict(list)
    for row in aggregate_rows:
        approach_results[row["approach"]].append({
            "model": row["model"],
            "mean_bleu": row["mean_bleu"],
            "mean_rouge_1": row["mean_rouge_1"],
            "mean_rouge_l": row["mean_rouge_l"],
             "mean_bert_f1": row["mean_bert_f1"],
            "mean_total_tokens": row["mean_total_tokens"],
            "mean_total_latency_s": row["mean_total_latency_s"],
            "performance_score": row.get("performance_score"),
        })

    best_combination = max(aggregate_rows, key=lambda x: x.get("performance_score", 0.0), default=None)

    summary_report = {
        "summary_generated_at": datetime.utcnow().isoformat(),
        "dataset_size": len(dataset),
        "models_tested": models,
        "approaches_tested": approaches,
        "best_combination": best_combination,
        "approach_results": {
            approach: sorted(entries, key=lambda x: x["model"])
            for approach, entries in approach_results.items()
        },
    }

    with open(summary_filename, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2, ensure_ascii=False)

    print(
        f"\nHotovo! Kompletný report: {full_filename}\n"
        f"Sprievodný prehľad metrik: {summary_filename}"
    )
    if best_combination:
        print(
            f"Najefektívnejšia kombinácia: {best_combination['model']} / {best_combination['approach']} "
            f"(skóre {best_combination['performance_score']})"
        )


def main():
    parser = argparse.ArgumentParser(description="LLM Slovak Summarization Evaluator")
    parser.add_argument("--models", type=str, required=True, help="Comma-separated models (e.g. gpt-4o,gemini-1.5-flash)")
    parser.add_argument("--approaches", type=str, default="1,2,3,4", help="Comma-separated approach IDs (1-5)")

    args = parser.parse_args()

    model_list = [m.strip() for m in args.models.split(",")]
    approach_list = [a.strip() for a in args.approaches.split(",")]

    # Ensure NLTK data
    import nltk
    nltk.download('punkt_tab')
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)

    asyncio.run(run_experiment(model_list, approach_list, GOLD_STANDARD_DATASET))


if __name__ == "__main__":
    main()
