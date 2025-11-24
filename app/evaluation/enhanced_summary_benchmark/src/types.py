from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: 'TokenUsage'):
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens

@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    latency: float

@dataclass
class MetricResult:
    bleu: float
    rouge_1: float
    rouge_l: float
    bert_precision: float
    bert_recall: float
    bert_f1: float
    token_usage: TokenUsage
    latencies: Dict[str, float]

@dataclass
class PipelineResult:
    model_name: str
    approach_name: str
    metrics: MetricResult
    intermediate_artifacts: Dict[str, Any]
    final_summary: str
