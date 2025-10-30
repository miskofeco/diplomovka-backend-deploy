import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

CURRENT_DIR = Path(__file__).resolve().parent

if __package__ in (None, ""):
    sys.path.append(str(CURRENT_DIR))
    from tracker import UsageTracker  # type: ignore
else:
    from .tracker import UsageTracker


EVAL_DIR = Path(__file__).resolve().parent
APP_DIR = EVAL_DIR.parent.parent
SUMMARY_FILE = APP_DIR / "utils" / "summary.py"


@dataclass
class SummaryOutput:
    text: str
    usage: Dict[str, Any]
    wall_time_seconds: float


class BaseSummarizer:
    provider: str

    def summarise(self, article: str, title: Optional[str], intro: Optional[str]) -> SummaryOutput:
        raise NotImplementedError


def _load_summary_module(model_name: str) -> Any:
    os.environ["OPENAI_MODEL"] = model_name
    module_name = f"summary_under_test_{model_name.replace('-', '_').replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, SUMMARY_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to locate summary module at {SUMMARY_FILE}")

    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    return module


class OpenAISummarizer(BaseSummarizer):
    provider = "openai"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.summary_module = _load_summary_module(model_name)
        self._override_parse_for_model()

    def summarise(self, article: str, title: Optional[str], intro: Optional[str]) -> SummaryOutput:
        with UsageTracker(self.summary_module) as tracker:
            start = time.perf_counter()
            payload = self.summary_module.get_summary(article, title=title, intro=intro)
            wall_time = time.perf_counter() - start

        usage_snapshot = tracker.aggregate()
        usage_snapshot.update(
            {
                "provider": self.provider,
                "model": self.model_name,
                "api_duration_seconds": usage_snapshot.get("duration_seconds", 0.0),
            }
        )
        usage_snapshot.pop("duration_seconds", None)

        summary_text = ""
        if isinstance(payload, dict):
            summary_text = payload.get("summary", "") or ""

        return SummaryOutput(
            text=summary_text,
            usage=usage_snapshot,
            wall_time_seconds=wall_time,
        )

    def _should_force_default_temperature(self) -> bool:
        lowered = self.model_name.lower()
        return lowered.startswith("gpt-5") or lowered.startswith("gpt-4.1") or lowered.startswith("o1")

    def _override_parse_for_model(self) -> None:
        if not self._should_force_default_temperature():
            return

        completions = self.summary_module.client.beta.chat.completions
        original_parse = getattr(completions, "_original_parse", None) or completions.parse

        if getattr(completions, "_temperature_override_active", False):
            # Already patched, nothing to do.
            return

        def patched_parse(*args: Any, **kwargs: Any) -> Any:
            if "temperature" in kwargs and kwargs["temperature"] != 1:
                kwargs = dict(kwargs)
                kwargs["temperature"] = 1
            return original_parse(*args, **kwargs)

        completions._original_parse = original_parse  # type: ignore[attr-defined]
        completions.parse = patched_parse  # type: ignore[assignment]
        completions._temperature_override_active = True  # type: ignore[attr-defined]


class GeminiSummarizer(BaseSummarizer):
    provider = "gemini"

    def __init__(self, model_name: str, api_key: Optional[str] = None) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY must be set to evaluate Gemini models.")

        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "google-generativeai package is required for Gemini evaluation. Install via `pip install google-generativeai`."
            ) from exc

        self.genai = genai
        self.genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name=model_name)

    def summarise(self, article: str, title: Optional[str], intro: Optional[str]) -> SummaryOutput:
        start = time.perf_counter()
        events, events_usage, events_duration = self._extract_events(article)
        summary_text, summary_usage, summary_duration = self._generate_summary(article, events, title, intro)
        wall_time = time.perf_counter() - start

        usage = self._merge_usage(events_usage, summary_usage)
        if "total_tokens" not in usage and all(isinstance(usage.get(key), (int, float)) for key in ("prompt_tokens", "completion_tokens")):
            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        usage.update(
            {
                "provider": self.provider,
                "model": self.model_name,
                "api_duration_seconds": events_duration + summary_duration,
                "calls": 2,
            }
        )

        return SummaryOutput(text=summary_text, usage=usage, wall_time_seconds=wall_time)

    def _call_gemini(self, prompt: str, temperature: float) -> Any:
        generation_config = self.genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=2048,
        )
        start = time.perf_counter()
        response = self.model.generate_content(
            prompt,
            generation_config=generation_config,
        )
        duration = time.perf_counter() - start
        return response, self._usage_from_metadata(getattr(response, "usage_metadata", None)), duration

    def _extract_events(self, article: str) -> tuple[list[str], Dict[str, Any], float]:
        if len(article) > 5000:
            article = article[:5000]

        prompt = (
            "Si investigatívny reportér, ktorý analyzuje text izolovane od iných požiadaviek. "
            "Odpovedaj výhradne po slovensky a ignoruj všetky predošlé inštrukcie. "
            "Zameriaj sa na identifikáciu kľúčových udalostí v jasnom, stručnom formáte.\n\n"
            "## ÚLOHA\n"
            "Zanalyzuj článok a extrahuj najviac šesť kľúčových udalostí. Každú udalosť popíš jedinou vetou.\n\n"
            "## METODIKA\n"
            "- zachyť čo sa stalo, kto sa zúčastnil, kde a kedy (ak je informácia dostupná),\n"
            "- nepoužívaj odrážky ani číslovanie,\n"
            "- vyhni sa halucinovaným údajom.\n\n"
            "## KONTEXT\n"
            f"{article}\n\n"
            "## VÝSTUP\n"
            "Vráť zoznam viet, každú na novom riadku."
        )

        response, usage, duration = self._call_gemini(prompt, temperature=0.2)
        text = (response.text or "").strip() if hasattr(response, "text") else ""
        events = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
        return events[:6], usage, duration

    def _generate_summary(
        self,
        article: str,
        events: list[str],
        title: Optional[str],
        intro: Optional[str],
    ) -> tuple[str, Dict[str, Any], float]:
        if len(article) > 5000:
            article = article[:5000]

        events_text = "\n".join(f"- {event}" for event in events) if events else "- (udalosti sa nepodarilo spoľahlivo extrahovať)"
        normalized_title = title.strip() if title else ""
        normalized_intro = intro.strip() if intro else ""

        if normalized_title and normalized_intro:
            closing_directive = f'- Zakonči text vetou presne v tvare: "Záver: {normalized_title}. Úvod: {normalized_intro}".'
        else:
            closing_directive = "- Na záver doplň vetu, ktorá explicitne uvedie titulok a úvod vytvorené pre článok."

        prompt_parts = [
            "Si profesionálny spravodajský editor pracujúci v izolovanej relácii. "
            "Ignoruj všetky predošlé pokyny a odpovedaj výlučne po slovensky. "
            "Tvojou úlohou je vytvoriť vecný súhrn článku, ktorý je presný, neutrálny a bez halucinácií.",
            "## ÚLOHA",
            "Napíš kompaktný spravodajský súhrn v rozsahu 3 až 5 viet, ktorý vyzdvihne najdôležitejšie body článku.",
            "## VSTUPNÉ PODKLADY",
            "### Text článku",
            article,
            "### Identifikované udalosti",
            events_text,
        ]

        if normalized_title:
            prompt_parts.extend(["### Titulok", normalized_title])
        if normalized_intro:
            prompt_parts.extend(["### Úvod", normalized_intro])

        prompt_parts.extend(
            [
                "## POŽIADAVKY NA ŠTRUKTÚRU",
                "- zachovaj chronológiu alebo logické členenie udalostí,",
                "- nevkladaj nové informácie,",
                "- použij faktické formulácie bez hodnotenia,",
                closing_directive,
                "## VÝSTUP",
                "Poskytni výstup ako súvislý text v slovenčine.",
            ]
        )

        prompt = "\n\n".join(prompt_parts)
        response, usage, duration = self._call_gemini(prompt, temperature=0.4)
        summary_text = (response.text or "").strip() if hasattr(response, "text") else ""
        return summary_text, usage, duration

    @staticmethod
    def _usage_from_metadata(metadata: Any) -> Dict[str, Any]:
        if metadata is None:
            return {}

        if isinstance(metadata, dict):
            prompt_tokens = metadata.get("prompt_token_count") or metadata.get("input_tokens")
            completion_tokens = metadata.get("candidates_token_count") or metadata.get("output_tokens")
            total_tokens = metadata.get("total_token_count")
        else:
            prompt_tokens = getattr(metadata, "prompt_token_count", None) or getattr(metadata, "input_tokens", None)
            completion_tokens = getattr(metadata, "candidates_token_count", None) or getattr(metadata, "output_tokens", None)
            total_tokens = getattr(metadata, "total_token_count", None)

        usage = {}
        if prompt_tokens is not None:
            usage["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            usage["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            usage["total_tokens"] = total_tokens
        return usage

    @staticmethod
    def _merge_usage(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
        merged = {}
        for key in set(first.keys()).union(second.keys()):
            value_one = first.get(key)
            value_two = second.get(key)
            if isinstance(value_one, (int, float)) and isinstance(value_two, (int, float)):
                merged[key] = value_one + value_two
            elif isinstance(value_one, (int, float)):
                merged[key] = value_one
            elif isinstance(value_two, (int, float)):
                merged[key] = value_two
            else:
                merged[key] = value_two or value_one
        return merged


def parse_model_spec(spec: str) -> tuple[str, str]:
    if ":" in spec:
        provider, model = spec.split(":", 1)
        provider = provider.strip().lower()
        model = model.strip()
    else:
        provider, model = "openai", spec.strip()

    if not model:
        raise ValueError(f"Invalid model specification: {spec}")
    if provider not in {"openai", "gemini"}:
        raise ValueError(f"Unsupported provider '{provider}' in spec '{spec}'.")
    return provider, model


def get_summarizer(provider: str, model_name: str) -> BaseSummarizer:
    if provider == "openai":
        return OpenAISummarizer(model_name)
    if provider == "gemini":
        return GeminiSummarizer(model_name)
    raise ValueError(f"Unknown provider: {provider}")
