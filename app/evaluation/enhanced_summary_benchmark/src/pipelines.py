import json
import abc
from src.models import LLMClient
from src.prompts import SlovakPrompts
from src.types import PipelineResult, TokenUsage
from src.metrics import MetricsEngine, Timer

class SummarizationPipeline(abc.ABC):
    def __init__(self, model: LLMClient, metrics_engine: MetricsEngine):
        self.model = model
        self.metrics = metrics_engine

    @abc.abstractmethod
    async def execute(self, article: str, reference: str) -> PipelineResult:
        pass

class BasicPipeline(SummarizationPipeline):
    async def execute(self, article: str, reference: str) -> PipelineResult:
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
    async def execute(self, article: str, reference: str) -> PipelineResult:
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
    async def execute(self, article: str, reference: str) -> PipelineResult:
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

    async def execute(self, article: str, reference: str) -> PipelineResult:
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
