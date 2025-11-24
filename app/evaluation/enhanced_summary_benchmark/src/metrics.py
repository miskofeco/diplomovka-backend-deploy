import time
from typing import Tuple
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
from bert_score import score as bert_score
from src.types import TokenUsage, MetricResult

class MetricsEngine:
    def __init__(self, bert_model_type: str = "bert-base-multilingual-cased", bert_lang: str = "sk"):
        self.rouge = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
        self.smooth = SmoothingFunction().method1
        self.bert_model_type = bert_model_type
        self.bert_lang = bert_lang

    def calculate(self, 
                  reference: str, 
                  hypothesis: str, 
                  usage: TokenUsage, 
                  latencies: dict) -> MetricResult:
        
        # BLEU (Simple sentence level for this context)
        ref_tokens = reference.lower().split()
        hyp_tokens = hypothesis.lower().split()
        bleu = sentence_bleu([ref_tokens], hyp_tokens, smoothing_function=self.smooth)

        # ROUGE
        scores = self.rouge.score(reference, hypothesis)

        # BERTScore (multilingual)
        bert_p, bert_r, bert_f1 = self._calculate_bertscore(reference, hypothesis)
        
        return MetricResult(
            bleu=round(bleu, 4),
            rouge_1=round(scores['rouge1'].fmeasure, 4),
            rouge_l=round(scores['rougeL'].fmeasure, 4),
            bert_precision=bert_p,
            bert_recall=bert_r,
            bert_f1=bert_f1,
            token_usage=usage,
            latencies=latencies
        )

    def _calculate_bertscore(self, reference: str, hypothesis: str) -> Tuple[float, float, float]:
        try:
            P, R, F1 = bert_score(
                cands=[hypothesis],
                refs=[reference],
                lang=self.bert_lang,
                model_type=self.bert_model_type,
                verbose=False
            )
            bert_p = round(P.mean().item(), 4)
            bert_r = round(R.mean().item(), 4)
            bert_f = round(F1.mean().item(), 4)
            return bert_p, bert_r, bert_f
        except Exception:
            # Fallback in case the scorer fails; keeps pipeline running
            return 0.0, 0.0, 0.0

class Timer:
    def __init__(self):
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()

    @property
    def duration(self):
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0
