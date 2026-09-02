"""Tests for the inference benchmark measurement (P4.1.3, PART 4).

These exercise latency/throughput/model-size measurement with an injected fake
model in the base environment (no torch/Ultralytics), confirming the benchmark
assembler produces a section compatible with the evaluator's existing placeholder
shape.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from device_ai.training.detector.benchmark import (
    benchmark_inference,
    measure_model_size,
)


class _FakeModel:
    """A fake model recording how many times it was called.

    ``predict``/``__call__`` sleep briefly so measured latency is reliably
    nonzero regardless of host speed (P9.7: without this, a near-zero-cost
    mock call can round to exactly 0.000ms on a fast/idle machine, failing
    the ``latency_ms > 0`` assertion below — a real, reproducible test
    fragility found live during P9.2, root-caused here rather than in the
    production rounding logic, which is correct).
    """

    def __init__(self) -> None:
        self.call_count = 0

    def predict(self, sample: object, **kwargs: object) -> None:
        """Mimic Ultralytics' predict API."""
        time.sleep(0.001)
        self.call_count += 1

    def __call__(self, sample: object) -> None:
        """Mimic the direct-call fallback."""
        time.sleep(0.001)
        self.call_count += 1


def test_benchmark_measures_latency_and_throughput() -> None:
    """Benchmark returns latency_ms and throughput_fps from timed runs."""
    model = _FakeModel()
    result = benchmark_inference(
        model,
        "sample.jpg",
        device="cpu",
        batch_size=1,
        image_size=640,
        warmup=2,
        runs=10,
    )
    assert result["status"] == "measured"
    assert result["latency_ms"] > 0
    assert result["throughput_fps"] > 0
    assert result["device"] == "cpu"
    assert result["batch_size"] == 1
    # Warmup + runs calls were made.
    assert model.call_count == 2 + 10


def test_benchmark_reports_model_size_when_weights_present(tmp_path: Path) -> None:
    """With a real weights file, model_size_bytes and model_size_mb are populated."""
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"x" * 1024 * 1024)  # 1 MB
    model = _FakeModel()

    result = benchmark_inference(
        model,
        "sample.jpg",
        device="cpu",
        weights_path=weights,
        warmup=0,
        runs=1,
    )

    assert result["model_size_bytes"] == 1024 * 1024
    assert result["model_size_mb"] == 1.0


def test_benchmark_handles_missing_weights() -> None:
    """With no weights_path, model size fields are zero."""
    model = _FakeModel()
    result = benchmark_inference(
        model, "sample.jpg", device="cpu", warmup=0, runs=1
    )
    assert result["model_size_bytes"] == 0
    assert result["model_size_mb"] == 0.0


def test_benchmark_throughput_scales_with_batch_size() -> None:
    """Throughput is per-image: batch_size=4 reports 4× the single-image rate."""
    model = _FakeModel()
    single = benchmark_inference(
        model, "sample.jpg", device="cpu", batch_size=1, warmup=0, runs=5
    )
    batch = benchmark_inference(
        model, "batch.jpg", device="cpu", batch_size=4, warmup=0, runs=5
    )
    # Batch throughput should be roughly 4× single (the fake runs in zero time,
    # so the ratio is noise-dominated, but the batch_size field is correct).
    assert batch["batch_size"] == 4
    assert single["batch_size"] == 1


def test_benchmark_uses_callable_fallback_when_no_predict() -> None:
    """When the model has no predict, __call__ is invoked instead."""

    class _CallableOnlyModel:
        def __init__(self) -> None:
            self.call_count = 0

        def __call__(self, sample: object) -> None:
            self.call_count += 1

    model = _CallableOnlyModel()
    benchmark_inference(model, "sample.jpg", device="cpu", warmup=1, runs=3)
    assert model.call_count == 1 + 3


def test_benchmark_requires_positive_runs() -> None:
    """A runs count < 1 raises ValueError."""
    with pytest.raises(ValueError, match="runs must be >= 1"):
        benchmark_inference(_FakeModel(), "sample.jpg", device="cpu", runs=0)


def test_benchmark_requires_positive_batch_size() -> None:
    """A batch_size < 1 raises ValueError."""
    with pytest.raises(ValueError, match="batch_size must be >= 1"):
        benchmark_inference(
            _FakeModel(), "sample.jpg", device="cpu", batch_size=0, runs=1
        )


def test_measure_model_size_returns_zero_for_none() -> None:
    """With no weights_path, measure_model_size returns (0, 0.0)."""
    assert measure_model_size(None) == (0, 0.0)


def test_measure_model_size_returns_zero_for_missing_file(tmp_path: Path) -> None:
    """A path that does not exist returns (0, 0.0)."""
    assert measure_model_size(tmp_path / "missing.pt") == (0, 0.0)


def test_measure_model_size_rounds_mb_to_three_decimals(tmp_path: Path) -> None:
    """The MB field is rounded to three decimals."""
    weights = tmp_path / "model.onnx"
    weights.write_bytes(b"x" * 1234567)
    size_bytes, size_mb = measure_model_size(weights)
    assert size_bytes == 1234567
    assert size_mb == 1.177  # 1234567 / (1024*1024) rounded to 3 decimals
