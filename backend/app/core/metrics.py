"""Track-02 inference metrics: pure math, no I/O.

Every QVAC chat call is wrapped by :func:`build_metrics`, which produces an
``InferenceMetrics`` record ready for ``perf_log``. Token counts come from the
OpenAI ``usage`` object (``prompt_tokens`` / ``completion_tokens``) when
present; otherwise they are estimated at ~4 chars/token.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

CHARS_PER_TOKEN = 4


@dataclass
class InferenceMetrics:
    model: str
    model_load_ms: int | None  # set only when the model had to be loaded (cold start)
    prompt_tokens: int
    generation_tokens: int
    ttft_ms: int
    total_ms: int
    throughput_tps: float
    created_at: float = field(default_factory=time.time)

    def as_perf_row(self, request_id: str) -> dict[str, Any]:
        from datetime import datetime, timezone

        return {
            "request_id": request_id,
            "model": self.model,
            "model_load_ms": self.model_load_ms,
            "prompt_tokens": self.prompt_tokens,
            "generation_tokens": self.generation_tokens,
            "ttft_ms": self.ttft_ms,
            "total_ms": self.total_ms,
            "throughput_tps": self.throughput_tps,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc),
        }


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), at least 1 for non-empty text."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def generation_seconds(ttft_ms: int, total_ms: int) -> float:
    """Wall-clock seconds spent generating tokens (after first token)."""
    return max(total_ms - ttft_ms, 1) / 1000.0


def compute_throughput(generation_tokens: int, gen_seconds: float) -> float:
    """Tokens per second; 0.0 when nothing was generated."""
    if generation_tokens <= 0 or gen_seconds <= 0:
        return 0.0
    return round(generation_tokens / gen_seconds, 2)


def build_metrics(
    model: str,
    ttft_ms: int,
    total_ms: int,
    prompt_text: str,
    generated_text: str,
    usage: dict[str, Any] | None = None,
    cold_start: bool = False,
) -> InferenceMetrics:
    """Build a perf record from a streamed chat call.

    ``usage`` is the OpenAI usage object from the final stream chunk:
    ``prompt_tokens`` / ``completion_tokens`` when available.
    """
    if usage:
        prompt_tokens = int(usage.get("prompt_tokens") or estimate_tokens(prompt_text))
        generation_tokens = int(usage.get("completion_tokens") or estimate_tokens(generated_text))
    else:
        prompt_tokens = estimate_tokens(prompt_text)
        generation_tokens = estimate_tokens(generated_text)
    gen_s = generation_seconds(ttft_ms, total_ms)

    throughput = compute_throughput(generation_tokens, gen_s)

    # The QVAC server preloads models at startup; there is no cold-start
    # signal in the OpenAI usage object, so model_load_ms stays None.
    model_load_ms = None

    return InferenceMetrics(
        model=model,
        model_load_ms=model_load_ms,
        prompt_tokens=prompt_tokens,
        generation_tokens=generation_tokens,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        throughput_tps=throughput,
    )
