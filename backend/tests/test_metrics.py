from app.core.metrics import (
    build_metrics,
    compute_throughput,
    estimate_tokens,
    generation_seconds,
)


class TestEstimation:
    def test_estimate_tokens_scales_with_chars(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 400) == 100

    def test_generation_seconds(self):
        assert generation_seconds(200, 1200) == 1.0
        assert generation_seconds(0, 5) >= 0.001  # clamped to >= 1ms


class TestThroughput:
    def test_basic(self):
        assert compute_throughput(50, 2.0) == 25.0

    def test_zero_generation(self):
        assert compute_throughput(0, 2.0) == 0.0

    def test_zero_seconds(self):
        assert compute_throughput(10, 0.0) == 0.0


class TestBuildMetrics:
    def test_with_ollama_usage(self):
        usage = {
            "prompt_eval_count": 120,
            "eval_count": 60,
            "eval_duration": 2_000_000_000,  # 2 s
            "load_duration": 3_500_000_000,  # 3.5 s cold load
        }
        m = build_metrics(
            model="medpsy:q4_k_m",
            ttft_ms=4000,
            total_ms=6000,
            prompt_text="x" * 480,
            generated_text="y" * 240,
            usage=usage,
            cold_start=True,
        )
        assert m.prompt_tokens == 120
        assert m.generation_tokens == 60
        assert m.throughput_tps == 30.0  # 60 tokens / 2 s
        assert m.model_load_ms == 3500
        assert m.ttft_ms == 4000
        assert m.total_ms == 6000

    def test_warm_start_has_no_load_time(self):
        usage = {"prompt_eval_count": 10, "eval_count": 20, "eval_duration": 1_000_000_000}
        m = build_metrics(
            model="m", ttft_ms=300, total_ms=1300,
            prompt_text="p", generated_text="g", usage=usage, cold_start=False,
        )
        assert m.model_load_ms is None

    def test_estimated_when_usage_missing(self):
        m = build_metrics(
            model="m", ttft_ms=500, total_ms=2500,
            prompt_text="x" * 400, generated_text="y" * 800,
            usage=None, cold_start=True,
        )
        assert m.prompt_tokens == 100
        assert m.generation_tokens == 200
        assert m.throughput_tps == 100.0  # 200 tokens / 2 s
        assert m.model_load_ms == 500  # falls back to TTFT on cold start

    def test_perf_row_shape(self):
        m = build_metrics(
            model="m", ttft_ms=100, total_ms=500,
            prompt_text="aaaa", generated_text="bbbb", usage=None, cold_start=False,
        )
        row = m.as_perf_row("req-1")
        assert row["request_id"] == "req-1"
        assert set(row) == {
            "request_id", "model", "model_load_ms", "prompt_tokens",
            "generation_tokens", "ttft_ms", "total_ms", "throughput_tps",
            "created_at",
        }
