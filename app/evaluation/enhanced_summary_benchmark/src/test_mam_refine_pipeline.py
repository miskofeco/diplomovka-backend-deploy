import asyncio
import json
import unittest

from src.models import LLMClient
from src.pipelines import MamRefinePipeline
from src.types import MetricResult, PipelineResult, TokenUsage, LLMResponse


class FakeLLM(LLMClient):
    """
    Lightweight fake client to exercise the MAMM-REFINE pipeline without real API calls.
    """

    def __init__(self, model_name: str):
        super().__init__(model_name)

    async def generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> LLMResponse:
        # Baseline generator
        if "baseline" in self.model_name:
            content = (
                "The rail upgrade will finish in 1990. "
                "The project raises speed to 160 km/h with new signaling."
            )
            return LLMResponse(content=content, usage=TokenUsage(1, 1, 2), latency=0.01)

        # Detector models: mark 1990 as inconsistent
        if "detector" in self.model_name:
            answer = "no" if "1990" in user_prompt else "yes"
            payload = {"reasoning": "mock", "answer": answer}
            return LLMResponse(content=json.dumps(payload), usage=TokenUsage(1, 1, 2), latency=0.01)

        # Critique models: always point to the wrong year
        if "critique" in self.model_name:
            critique_text = "The error span: 1990. Replace with 2027 based on the document."
            return LLMResponse(content=critique_text, usage=TokenUsage(1, 1, 2), latency=0.01)

        # Refiners: generate a corrected summary
        if "refine" in self.model_name:
            refined = "The rail upgrade will finish in 2027 and will raise speeds to 160 km/h."
            return LLMResponse(content=refined, usage=TokenUsage(1, 1, 2), latency=0.01)

        # Reranker: choose options mentioning 2027
        if "rerank" in self.model_name:
            if "Critique 1" in user_prompt or "Kritika 1" in user_prompt:
                payload = {"reasoning": "prefer second critique", "answer": 2}
            else:
                if "Candidate Summary 2:" in user_prompt:
                    tail = user_prompt.split("Candidate Summary 2:")[-1]
                elif "Kandidátne zhrnutie 2:" in user_prompt:
                    tail = user_prompt.split("Kandidátne zhrnutie 2:")[-1]
                else:
                    tail = user_prompt
                answer = 2 if "2027" in tail else 1
                payload = {"reasoning": "prefer fixed date", "answer": answer}
            return LLMResponse(content=json.dumps(payload), usage=TokenUsage(1, 1, 2), latency=0.01)

        return LLMResponse(content="noop", usage=TokenUsage(0, 0, 0), latency=0.0)


class DummyMetrics:
    """Simplified metrics stub to avoid heavy scorers during unit tests."""

    def calculate(self, reference: str, hypothesis: str, usage: TokenUsage, latencies: dict) -> MetricResult:
        return MetricResult(
            bleu=0.0,
            rouge_1=0.0,
            rouge_l=0.0,
            bert_precision=0.0,
            bert_recall=0.0,
            bert_f1=0.0,
            token_usage=usage,
            latencies=latencies,
        )


class MamRefinePipelineTest(unittest.TestCase):
    def test_mam_refine_pipeline_runs_end_to_end(self):
        article = (
            "Železnice Slovenskej republiky začali modernizáciu s cieľom dokončiť prvé úseky v roku 2027, "
            "pričom rýchlosť vlakov má stúpnuť na 160 km/h."
        )
        reference = "Modernizácia má skončiť v roku 2027 a zrýchliť vlaky na 160 km/h."

        baseline = FakeLLM("fake-baseline")
        detectors = [FakeLLM("fake-detector-a"), FakeLLM("fake-detector-b")]
        critiques = [FakeLLM("fake-critique-a"), FakeLLM("fake-critique-b")]
        refiners = [FakeLLM("fake-refine-a"), FakeLLM("fake-refine-b")]
        reranker = FakeLLM("fake-rerank")

        pipeline = MamRefinePipeline(
            baseline_model=baseline,
            detector_models=detectors,
            critique_models=critiques,
            refine_models=refiners,
            rerank_model=reranker,
            metrics_engine=DummyMetrics(),  # type: ignore[arg-type]
        )

        result: PipelineResult = asyncio.run(pipeline.execute(article, reference, topic="Doprava"))

        detection_flags = result.intermediate_artifacts["detection"]["is_inconsistent"]
        best_critiques = result.intermediate_artifacts["critiques"]["best_critiques"]
        candidate_summaries = result.intermediate_artifacts["candidate_summaries"]

        self.assertTrue(detection_flags[0])
        self.assertTrue("0" in best_critiques or 0 in best_critiques)  # JSON serialization may coerce the key
        self.assertGreaterEqual(len(candidate_summaries), 2)
        self.assertIn("2027", result.final_summary)


if __name__ == "__main__":
    unittest.main()
