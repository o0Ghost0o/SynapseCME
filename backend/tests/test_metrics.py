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
    def test_with_openai_usage(self):
        usage = {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180}
        m = build_metrics(
            model="medpsy:q4_k_m",
            ttft_ms=4000,
            total_ms=6000,
            prompt_text="x" * 480,
            generated_text="y" * 240,
            usage=usage,
        )
        assert m.prompt_tokens == 120
        assert m.generation_tokens == 60
        assert m.throughput_tps == 30.0  # 60 tokens / 2 s wall clock
        assert m.model_load_ms is None  # no cold-start signal in OpenAI usage
        assert m.ttft_ms == 4000
        assert m.total_ms == 6000

    def test_no_load_time_without_cold_start(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        m = build_metrics(
            model="m", ttft_ms=300, total_ms=1300,
            prompt_text="p", generated_text="g", usage=usage, cold_start=False,
        )
        assert m.model_load_ms is None

    def test_estimated_when_usage_missing(self):
        m = build_metrics(
            model="m", ttft_ms=500, total_ms=2500,
            prompt_text="x" * 400, generated_text="y" * 800,
            usage=None,
        )
        assert m.prompt_tokens == 100
        assert m.generation_tokens == 200
        assert m.throughput_tps == 100.0  # 200 tokens / 2 s wall clock
        assert m.model_load_ms is None  # QVAC preloads models; always warm

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
