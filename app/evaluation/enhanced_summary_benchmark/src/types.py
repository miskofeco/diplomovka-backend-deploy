from dataclasses import dataclass, field, asdict
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


@dataclass
class DetectionVote:
    model: str
    answer: str
    reasoning: str


@dataclass
class DetectionResult:
    sentences: List[str]
    is_inconsistent: List[bool]
    votes: Dict[int, List[DetectionVote]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentences": self.sentences,
            "is_inconsistent": self.is_inconsistent,
            "votes": {idx: [asdict(v) for v in vote_list] for idx, vote_list in self.votes.items()},
        }


@dataclass
class CritiqueCandidate:
    text: str
    model: str


@dataclass
class CritiqueResult:
    best_critiques: Dict[int, CritiqueCandidate] = field(default_factory=dict)
    all_critiques: Dict[int, List[CritiqueCandidate]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_critiques": {idx: asdict(c) for idx, c in self.best_critiques.items()},
            "all_critiques": {idx: [asdict(c) for c in lst] for idx, lst in self.all_critiques.items()},
        }
