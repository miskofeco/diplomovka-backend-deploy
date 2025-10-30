# Summary Benchmark Harness

This utility lets you benchmark the existing summarisation pipeline against multiple OpenAI and Gemini models without altering any production code. It reuses the prompts and flow defined in `app/utils/summary.py` (for OpenAI) and mirrors the same instructions through the Gemini SDK, then records quality metrics, token usage, and latency for every run.

## Quick start
- Ensure `OPENAI_API_KEY` is available for OpenAI models; set `GEMINI_API_KEY` and install `google-generativeai` (`pip install google-generativeai`) when testing Gemini models.
- Optional: create a custom dataset following the extended format shown in `datasets/sample_dataset.json`.
- Run the evaluator from the project root (or directly from the backend folder):
  ```bash
  python3 backend/app/evaluation/summary_benchmark/runner.py \
    --models openai:gpt-4o-mini gemini:gemini-1.5-pro \
    --dataset backend/app/evaluation/summary_benchmark/datasets/sample_dataset.json \
    --verbose
  ```
  When no provider prefix is given (e.g. just `gpt-4o-mini`), the harness defaults to `openai`. Model family `gpt-4.1`, `gpt-5` a `o1` majú automaticky nastavenú teplotu na `1`, aby zodpovedali obmedzeniam API.

## Dataset format
Provide a JSON array where each object contains:
- `id` (string or number) – identifier used in reports.
- `article` – plný text článku; odporúčané sú rôzne slovenské zdroje (pozri pripravený dataset).
- `reference_summary` / `golden_summary` – zlatý štandard sumarizácie použitý pre BLEU/ROUGE.
- `title` / `intro` – voliteľné polia, ktoré sa prenášajú do summarizačného toku.
- `source` / `url` – nepovinné meta-informácie zobrazujúce pôvod článku; uchovávajú sa v reportoch pre spätnú kontrolu.
Priložený `sample_dataset.json` obsahuje tri slovenské články z denníkov Denník N, SME a Pravda s kurátorskými referenčnými sumármi.

## Metrics and telemetry
- **BLEU** (up to 4-grams) and **ROUGE-1/2/L F1** are computed per sample when a reference summary is available, then averaged per model.
- Token statistics and API call durations využívajú natívne metriky jednotlivých SDK (OpenAI `usage`, Gemini `usage_metadata`); ak poskytovateľ čísla nevráti, hodnoty zostanú nulové.
- Wall-clock timing captures the full end-to-end runtime for each generated summary.

## Output
- Results are printed to stdout. Use `--output path/to/results.json` to persist a structured JSON report containing per-sample details plus aggregated metrics and usage.
- `--limit N` evaluates only the first `N` samples, which is helpful when iterating on prompts or comparing many models.
