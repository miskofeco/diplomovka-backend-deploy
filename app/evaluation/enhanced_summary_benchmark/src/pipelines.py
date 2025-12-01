import abc
import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from nltk.tokenize import sent_tokenize

from src.metrics import MetricsEngine, Timer
from src.models import LLMClient
from src.prompts import SlovakPrompts, MammRefinePrompts
from src.types import (
    CritiqueCandidate,
    CritiqueResult,
    DetectionResult,
    DetectionVote,
    PipelineResult,
    TokenUsage,
)

class SummarizationPipeline(abc.ABC):
    def __init__(self, model: LLMClient, metrics_engine: MetricsEngine):
        self.model = model
        self.metrics = metrics_engine

    @abc.abstractmethod
    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        pass

class BasicPipeline(SummarizationPipeline):
    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        total_usage = TokenUsage()
        
        with Timer() as t:
            resp = await self.model.generate(SlovakPrompts.BASIC_SYSTEM, 
                                             SlovakPrompts.BASIC_USER.format(article=article))
        
        total_usage.add(resp.usage)
        
        metrics = self.metrics.calculate(
            reference,
            resp.content,
            total_usage,
            {"total_runtime_s": t.duration}
        )
        
        return PipelineResult(
            model_name=self.model.model_name,
            approach_name="1_basic",
            metrics=metrics,
            intermediate_artifacts={},
            final_summary=resp.content
        )

class EnhancedPipeline(SummarizationPipeline):
    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        total_usage = TokenUsage()
        
        with Timer() as t:
            resp = await self.model.generate(SlovakPrompts.ENHANCED_SYSTEM, 
                                             SlovakPrompts.ENHANCED_USER.format(article=article))
        
        total_usage.add(resp.usage)
        metrics = self.metrics.calculate(
            reference,
            resp.content,
            total_usage,
            {"total_runtime_s": t.duration}
        )
        
        return PipelineResult(
            model_name=self.model.model_name,
            approach_name="2_enhanced",
            metrics=metrics,
            intermediate_artifacts={},
            final_summary=resp.content
        )

class MultiStepPipeline(SummarizationPipeline):
    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        usage = TokenUsage()

        # Step 1: Events
        with Timer() as t1:
            events_resp = await self.model.generate(
                SlovakPrompts.EVENT_EXTRACTION_SYSTEM,
                SlovakPrompts.EVENT_EXTRACTION_USER.format(article=article)
            )
        usage.add(events_resp.usage)

        # Step 2: Synthesis
        with Timer() as t2:
            summary_resp = await self.model.generate(
                SlovakPrompts.ENHANCED_SYSTEM,
                SlovakPrompts.SYNTHESIS_USER.format(events=events_resp.content, article=article)
            )
        usage.add(summary_resp.usage)
        total_runtime = t1.duration + t2.duration

        metrics = self.metrics.calculate(
            reference,
            summary_resp.content,
            usage,
            {"total_runtime_s": total_runtime}
        )

        return PipelineResult(
            model_name=self.model.model_name,
            approach_name="3_multistep",
            metrics=metrics,
            intermediate_artifacts={"events": events_resp.content},
            final_summary=summary_resp.content
        )

class SelfRefinePipeline(SummarizationPipeline):
    def __init__(self, model: LLMClient, evaluator: LLMClient, metrics_engine: MetricsEngine):
        super().__init__(model, metrics_engine)
        self.evaluator = evaluator

    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        usage = TokenUsage()
        artifacts = {}
        
        start_total = Timer()
        with start_total:
            # 1. Initial Synthesis (Reusing logic from multi-step roughly)
            with Timer() as t1:
                events_resp = await self.model.generate(
                    SlovakPrompts.EVENT_EXTRACTION_SYSTEM,
                    SlovakPrompts.EVENT_EXTRACTION_USER.format(article=article)
                )
                initial_sum_resp = await self.model.generate(
                    SlovakPrompts.ENHANCED_SYSTEM,
                    SlovakPrompts.SYNTHESIS_USER.format(events=events_resp.content, article=article)
                )
            
            usage.add(events_resp.usage)
            usage.add(initial_sum_resp.usage)
            
            current_summary = initial_sum_resp.content
            artifacts["initial_summary"] = current_summary

            # 2. Evaluation Loop (Max 1 refinement for cost control in this demo)
            with Timer() as t_eval:
                eval_resp = await self.evaluator.generate(
                    SlovakPrompts.EVALUATOR_SYSTEM,
                    SlovakPrompts.EVALUATOR_USER.format(article=article, summary=current_summary),
                    json_mode=True
                )
            usage.add(eval_resp.usage)
            
            try:
                eval_json = json.loads(eval_resp.content)
                artifacts["feedback"] = eval_json
                
                if not eval_json.get("passed", False):
                    # 3. Refine
                    with Timer() as t_refine:
                        refine_resp = await self.model.generate(
                            SlovakPrompts.ENHANCED_SYSTEM,
                            SlovakPrompts.REFINE_USER.format(
                                article=article, 
                                summary=current_summary,
                                feedback=eval_json.get("feedback", "")
                            )
                        )
                    usage.add(refine_resp.usage)
                    current_summary = refine_resp.content
            except json.JSONDecodeError:
                # Fallback if JSON fails
                artifacts["feedback_error"] = "Failed to parse evaluation JSON"

        metrics = self.metrics.calculate(
            reference,
            current_summary,
            usage,
            {"total_runtime_s": start_total.duration}
        )

        return PipelineResult(
            model_name=self.model.model_name,
            approach_name="4_self_refine",
            metrics=metrics,
            intermediate_artifacts=artifacts,
            final_summary=current_summary
        )


class MamRefinePipeline(SummarizationPipeline):
    """
    Multi-agent factual refinement inspired by MAMM-REFINE.
    Stages: baseline -> detect -> critique -> refine -> rerank.
    """

    def __init__(
        self,
        baseline_model: LLMClient,
        detector_models: List[LLMClient],
        critique_models: List[LLMClient],
        refine_models: List[LLMClient],
        rerank_model: LLMClient,
        metrics_engine: MetricsEngine,
        prefer_consistent_on_tie: bool = True,
    ):
        super().__init__(baseline_model, metrics_engine)
        self.detector_models = detector_models
        self.critique_models = critique_models
        self.refine_models = refine_models
        self.rerank_model = rerank_model
        self.prefer_consistent_on_tie = prefer_consistent_on_tie
        self.model_label = f"{self.model.model_name}+{self.rerank_model.model_name}_mam_refine"

    async def execute(self, article: str, reference: str, topic: Optional[str] = None) -> PipelineResult:
        usage = TokenUsage()
        artifacts: Dict[str, Any] = {}

        with Timer() as total_timer:
            artifacts["model_roles"] = {
                "baseline": self.model.model_name,
                "detectors": [m.model_name for m in self.detector_models],
                "critique": [m.model_name for m in self.critique_models],
                "refine": [m.model_name for m in self.refine_models],
                "rerank": self.rerank_model.model_name,
            }
            baseline_summary, base_usage = await self.generate_baseline_summary(article, topic)
            usage.add(base_usage)
            artifacts["baseline_summary"] = baseline_summary

            detection_result, detect_usage = await self.detect_inconsistencies_multi_llm(article, baseline_summary)
            usage.add(detect_usage)
            artifacts["detection"] = detection_result.to_dict()

            critique_result, critique_usage = await self.critique_sentences_multi_agent(
                article, topic, baseline_summary, detection_result
            )
            usage.add(critique_usage)
            artifacts["critiques"] = critique_result.to_dict()

            final_summary, refine_usage, refine_artifacts = await self.refine_summary_multi_agent_rerank(
                article, topic, baseline_summary, critique_result
            )
            usage.add(refine_usage)
            artifacts.update(refine_artifacts)

        metrics = self.metrics.calculate(
            reference,
            final_summary,
            usage,
            {"total_runtime_s": total_timer.duration}
        )

        return PipelineResult(
            model_name=self.model_label,
            approach_name="5_mam_refine",
            metrics=metrics,
            intermediate_artifacts=artifacts,
            final_summary=final_summary
        )

    async def generate_baseline_summary(self, article: str, topic: Optional[str]) -> Tuple[str, TokenUsage]:
        system_prompt = MammRefinePrompts.BASELINE_SYSTEM
        user_prompt = (
            MammRefinePrompts.BASELINE_USER_WITH_TOPIC.format(topic=topic, document=article)
            if topic
            else MammRefinePrompts.BASELINE_USER_NO_TOPIC.format(document=article)
        )
        resp = await self.model.generate(system_prompt, user_prompt)
        usage = TokenUsage()
        usage.add(resp.usage)
        return resp.content, usage

    async def detect_inconsistencies_multi_llm(
        self, article: str, summary: str
    ) -> Tuple[DetectionResult, TokenUsage]:
        sentences = self._split_sentences(summary)
        votes: Dict[int, List[DetectionVote]] = {}
        inconsistency_flags: List[bool] = []
        usage = TokenUsage()

        for idx, sentence in enumerate(sentences):
            try:
                tasks = [
                    model.generate(
                        MammRefinePrompts.DETECT_SYSTEM,
                        MammRefinePrompts.DETECT_USER.format(document=article, sentence=sentence),
                        json_mode=True,
                    )
                    for model in self.detector_models
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                # If detector call fails, mark as consistent to avoid hard failures.
                votes[idx] = []
                inconsistency_flags.append(False)
                continue

            sentence_votes: List[DetectionVote] = []
            yes_count = 0
            no_count = 0

            for resp, model in zip(responses, self.detector_models):
                if isinstance(resp, Exception):
                    continue
                usage.add(resp.usage)
                parsed = self._safe_json(resp.content)
                answer_raw = self._extract_answer(parsed)
                reasoning = self._extract_reasoning(parsed, resp.content)

                answer = self._normalize_yes_no(answer_raw, resp.content)
                if answer == "yes":
                    yes_count += 1
                elif answer == "no":
                    no_count += 1

                sentence_votes.append(
                    DetectionVote(model=model.model_name, answer=answer, reasoning=reasoning)
                )

            votes[idx] = sentence_votes
            inconsistent = no_count > yes_count
            if no_count == yes_count:
                inconsistent = not self.prefer_consistent_on_tie
            inconsistency_flags.append(inconsistent)

        return DetectionResult(sentences=sentences, is_inconsistent=inconsistency_flags, votes=votes), usage

    async def critique_sentences_multi_agent(
        self,
        article: str,
        topic: Optional[str],
        summary: str,
        detection_result: DetectionResult,
    ) -> Tuple[CritiqueResult, TokenUsage]:
        usage = TokenUsage()
        best_critiques: Dict[int, CritiqueCandidate] = {}
        all_critiques: Dict[int, List[CritiqueCandidate]] = {}

        for idx, inconsistent in enumerate(detection_result.is_inconsistent):
            if not inconsistent:
                continue

            sentence = detection_result.sentences[idx]
            topic_clause = f" on the topic '{topic}'" if topic else ""
            tasks = []
            critique_models_used: List[LLMClient] = []
            for model in self.critique_models:
                try:
                    tasks.append(
                        model.generate(
                            MammRefinePrompts.CRITIQUE_SYSTEM,
                            MammRefinePrompts.CRITIQUE_USER.format(
                                topic_clause=topic_clause,
                                document=article,
                                summary=summary,
                                sentence=sentence,
                            ),
                        )
                    )
                    critique_models_used.append(model)
                except Exception:
                    continue

            responses = await asyncio.gather(*tasks, return_exceptions=True)
            candidates = []
            for resp, model in zip(responses, critique_models_used):
                if isinstance(resp, Exception):
                    continue
                usage.add(resp.usage)
                candidates.append(CritiqueCandidate(text=resp.content, model=model.model_name))

            if not candidates:
                continue

            all_critiques[idx] = candidates
            best_candidate, rerank_usage = await self._select_best_critique(
                article, summary, candidates
            )
            usage.add(rerank_usage)
            best_critiques[idx] = best_candidate

        return CritiqueResult(best_critiques=best_critiques, all_critiques=all_critiques), usage

    async def refine_summary_multi_agent_rerank(
        self,
        article: str,
        topic: Optional[str],
        baseline_summary: str,
        critique_result: CritiqueResult,
    ) -> Tuple[str, TokenUsage, Dict[str, Any]]:
        usage = TokenUsage()
        artifacts: Dict[str, Any] = {}

        if not critique_result.best_critiques:
            artifacts["feedback"] = "No inconsistencies detected by DETECT stage."
            artifacts["candidate_summaries"] = [{"model": self.model.model_name, "summary": baseline_summary}]
            artifacts["rerank_winner_model"] = self.model.model_name
            return baseline_summary, usage, artifacts

        feedback_lines = [
            f"Sentence {idx + 1}: {critique.text.strip()}"
            for idx, critique in sorted(critique_result.best_critiques.items())
        ]
        feedback_text = "\n\n".join(feedback_lines)
        artifacts["feedback"] = feedback_text

        topic_clause = f" on the topic '{topic}'" if topic else ""
        tasks = []
        refine_models_used: List[LLMClient] = []
        for model in self.refine_models:
            try:
                tasks.append(
                    model.generate(
                        MammRefinePrompts.REFINE_SYSTEM,
                        MammRefinePrompts.REFINE_USER.format(
                            topic_clause=topic_clause,
                            document=article,
                            summary=baseline_summary,
                            feedback=feedback_text,
                        ),
                    )
                )
                refine_models_used.append(model)
            except Exception:
                continue

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        candidate_summaries = [{"model": self.model.model_name, "summary": baseline_summary}]
        for resp, model in zip(responses, refine_models_used):
            if isinstance(resp, Exception):
                continue
            usage.add(resp.usage)
            candidate_summaries.append({"model": model.model_name, "summary": resp.content})
        artifacts["candidate_summaries"] = candidate_summaries

        final_summary, rerank_usage, rerank_trace = await self._rerank_summaries(
            article, topic, candidate_summaries
        )
        usage.add(rerank_usage)
        artifacts.update(rerank_trace)
        return final_summary, usage, artifacts

    async def _select_best_critique(
        self,
        article: str,
        summary: str,
        candidates: List[CritiqueCandidate],
    ) -> Tuple[CritiqueCandidate, TokenUsage]:
        usage = TokenUsage()
        if len(candidates) == 1:
            return candidates[0], usage

        best = candidates[0]
        for contender in candidates[1:]:
            try:
                resp = await self.rerank_model.generate(
                    MammRefinePrompts.CRITIQUE_RERANK_SYSTEM,
                    MammRefinePrompts.CRITIQUE_RERANK_USER.format(
                        document=article,
                        summary=summary,
                        critique1=best.text,
                        critique2=contender.text,
                    ),
                    json_mode=True,
                )
                usage.add(resp.usage)
                parsed = self._safe_json(resp.content)
                answer = self._normalize_rerank_answer(parsed, resp.content)
                if answer == "2":
                    best = contender
            except Exception:
                continue
        return best, usage

    async def _rerank_summaries(
        self,
        article: str,
        topic: Optional[str],
        candidates: List[Dict[str, str]],
    ) -> Tuple[str, TokenUsage, Dict[str, Any]]:
        usage = TokenUsage()
        trace: List[Dict[str, str]] = []

        if len(candidates) == 1:
            return candidates[0]["summary"], usage, {"rerank_winner_model": candidates[0]["model"]}

        best = candidates[0]
        topic_value = topic if topic is not None else ""
        for contender in candidates[1:]:
            try:
                resp = await self.rerank_model.generate(
                    MammRefinePrompts.SUMMARY_RERANK_SYSTEM,
                    MammRefinePrompts.SUMMARY_RERANK_USER.format(
                        document=article,
                        topic=topic_value,
                        summary1=best["summary"],
                        summary2=contender["summary"],
                    ),
                    json_mode=True,
                )
                usage.add(resp.usage)
                parsed = self._safe_json(resp.content)
                answer = self._normalize_rerank_answer(parsed, resp.content)
                reasoning = self._extract_reasoning(parsed, resp.content)
                trace.append(
                    {
                        "candidate_a_model": best["model"],
                        "candidate_b_model": contender["model"],
                        "reasoning": reasoning,
                        "winner": "b" if answer == "2" else "a",
                    }
                )
                if answer == "2":
                    best = contender
            except Exception:
                continue

        return best["summary"], usage, {"rerank_trace": trace, "rerank_winner_model": best["model"]}

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        return [s.strip() for s in sent_tokenize(text) if s.strip()]

    @staticmethod
    def _safe_json(content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            # If OpenAI returns content parts, try to pull text from them
            try:
                combined = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
                return json.loads(combined)
            except Exception:
                return {}
        try:
            return json.loads(content)
        except Exception:
            return {}

    @staticmethod
    def _extract_answer(parsed: Any) -> str:
        if isinstance(parsed, dict):
            for key in ("answer", "choice", "selected", "result"):
                if key in parsed:
                    return str(parsed.get(key, "")).strip()
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return str(parsed[0].get("answer", "")).strip()
        return ""

    @staticmethod
    def _extract_reasoning(parsed: Any, fallback: Any) -> str:
        if isinstance(parsed, dict):
            for key in ("reasoning", "reason", "rationale", "explanation"):
                if key in parsed and parsed.get(key):
                    return str(parsed.get(key))
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            val = parsed[0].get("reasoning") or parsed[0].get("reason") or parsed[0].get("rationale")
            if val:
                return str(val)
        return str(fallback)

    @staticmethod
    def _normalize_yes_no(answer_raw: str, content: Any) -> str:
        normalized = answer_raw.lower()
        if normalized in {"yes", "true", "ano", "áno", "consistent"}:
            return "yes"
        if normalized in {"no", "false", "nie", "inconsistent"}:
            return "no"
        text = str(content).lower()
        if "no" in text or "nie" in text:
            return "no"
        if "yes" in text or "ano" in text or "áno" in text:
            return "yes"
        return "no"

    @staticmethod
    def _normalize_rerank_answer(parsed: Any, content: Any) -> str:
        raw = ""
        if isinstance(parsed, dict):
            raw = str(parsed.get("answer", parsed.get("choice", ""))).strip()
        elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            raw = str(parsed[0].get("answer", "")).strip()
        if raw not in {"1", "2"}:
            text = str(content)
            raw = "2" if "2" in text and "1" not in text[-5:] else "1"
        return raw
