import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CallUsage:
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    duration_seconds: float
    model: Optional[str]
    response_format: Any


@dataclass
class UsageTracker:
    summary_module: Any
    calls: List[CallUsage] = field(default_factory=list)
    _original_parse: Optional[Any] = field(init=False, default=None)

    def __post_init__(self) -> None:
        try:
            self._completions = self.summary_module.client.beta.chat.completions
            self._original_parse = self._completions.parse
        except AttributeError as exc:
            raise RuntimeError(
                "The provided summary module does not expose the expected OpenAI client structure."
            ) from exc

    def __enter__(self) -> "UsageTracker":
        def wrapped_parse(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            response = self._original_parse(*args, **kwargs)
            duration = time.perf_counter() - start
            usage = getattr(response, "usage", None)
            self.calls.append(
                CallUsage(
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    duration_seconds=duration,
                    model=kwargs.get("model"),
                    response_format=kwargs.get("response_format"),
                )
            )
            return response

        self._completions.parse = wrapped_parse
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self._completions.parse = self._original_parse

    def aggregate(self) -> Dict[str, float]:
        prompt = sum(call.prompt_tokens or 0 for call in self.calls)
        completion = sum(call.completion_tokens or 0 for call in self.calls)
        total = sum(call.total_tokens or 0 for call in self.calls)
        duration = sum(call.duration_seconds for call in self.calls)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "duration_seconds": duration,
            "calls": len(self.calls),
        }

