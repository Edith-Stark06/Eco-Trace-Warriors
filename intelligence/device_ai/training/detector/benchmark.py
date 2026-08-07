"""Inference benchmark measurement for the trained detector (Sprint P4.1.3, PART 4).

The shared evaluator reserves an *inference benchmark* section on every
evaluation document but fills it with a clearly-labelled **placeholder**
(:func:`~device_ai.training.core.evaluator.build_benchmark_placeholder`) because
M1.3 trains no model. This module supplies the missing piece for P4.1.3: when a
model **is** available, it measures real latency / throughput (FPS) and model
size and assembles a ``status="measured"`` section of the *same shape*, so the
report contract is unchanged and only the numbers become real.

It is pure and dependency-light — it reuses
:class:`~device_ai.training.utils.timing.Timer` (``perf_counter``-based) and the
standard library. The model is called through a
tiny duck-typed surface (``predict`` preferred, ``__call__`` fallback — exactly
what :class:`~device_ai.inference.yolo_detector.YOLODetector` and Ultralytics
expose), so the whole path is unit-testable with an injected fake in the base
environment (no torch, no Ultralytics, no GPU).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.timing import Timer

#: Default number of warm-up iterations discarded before timing (the first
#: call is dominated by lazy graph/kernel initialisation, not steady-state
#: inference).
_DEFAULT_WARMUP = 2

#: Default number of timed iterations averaged into the latency measurement.
_DEFAULT_RUNS = 20


def measure_model_size(weights_path: Path | str | None) -> tuple[int, float]:
    """Return the on-disk model size as ``(bytes, megabytes)``.

    Args:
        weights_path: Path to the served weights file (``.pt``/``.onnx``), or
            ``None`` when no artifact is available.

    Returns:
        A ``(size_bytes, size_mb)`` tuple; ``(0, 0.0)`` when the path is absent
        or does not exist. ``size_mb`` is rounded to three decimals.
    """
    if weights_path is None:
        return 0, 0.0
    path = Path(weights_path)
    if not path.is_file():
        return 0, 0.0
    size_bytes = path.stat().st_size
    return size_bytes, round(size_bytes / (1024 * 1024), 3)


def _run_inference(model: Any, sample: Any, *, image_size: int) -> None:
    """Invoke one inference pass through the model's public surface.

    Prefers the Ultralytics/``YOLODetector`` ``predict(...)`` API, falling back
    to calling the model directly (``__call__``). The return value is discarded
    — only the wall-clock cost matters here.

    Args:
        model: The model object (real or an injected fake).
        sample: The input passed to the model (an image / batch / path).
        image_size: Square inference resolution forwarded as ``imgsz``.
    """
    predict = getattr(model, "predict", None)
    if callable(predict):
        predict(sample, imgsz=image_size, verbose=False)
        return
    model(sample)


def benchmark_inference(
    model: Any,
    sample: Any,
    *,
    device: str,
    batch_size: int = 1,
    image_size: int = 640,
    warmup: int = _DEFAULT_WARMUP,
    runs: int = _DEFAULT_RUNS,
    weights_path: Path | str | None = None,
) -> dict[str, Any]:
    """Measure inference latency / throughput and assemble a benchmark section.

    Runs ``warmup`` untimed passes, then ``runs`` timed passes, and reports the
    mean per-batch latency, the derived throughput in frames per second, the
    device, batch size and (optionally) the on-disk model size. The returned
    mapping matches the shape of
    :func:`~device_ai.training.core.evaluator.build_benchmark_placeholder` with
    ``status="measured"``, so it drops straight into ``build_evaluation_document(
    benchmark=...)`` without touching the report renderer.

    Args:
        model: The model exposing ``predict(...)`` or ``__call__`` (real or a
            fake injected for testing).
        sample: The input for a single inference call (image/batch/path).
        device: The resolved compute device string (e.g. ``"cpu"``/``"cuda"``).
        batch_size: Number of images represented by ``sample`` (used to derive
            per-image throughput). Must be >= 1.
        image_size: Square inference resolution forwarded to ``predict``.
        warmup: Untimed warm-up iterations (>= 0).
        runs: Timed iterations averaged into the latency (>= 1).
        weights_path: Optional path to the served weights, for the size fields.

    Returns:
        A primitive-only ``benchmark`` mapping with ``status="measured"``,
        ``latency_ms``, ``throughput_fps``, ``device``, ``batch_size``,
        ``model_size_bytes``, ``model_size_mb`` and ``runs``.

    Raises:
        ValueError: If ``runs`` < 1 or ``batch_size`` < 1.
    """
    if runs < 1:
        raise ValueError("runs must be >= 1 to measure a latency.")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1.")

    for _ in range(max(0, warmup)):
        _run_inference(model, sample, image_size=image_size)

    timer = Timer("yolo-inference").start()
    for _ in range(runs):
        _run_inference(model, sample, image_size=image_size)
    total_seconds = timer.stop()

    mean_batch_seconds = total_seconds / runs
    latency_ms = round(mean_batch_seconds * 1000.0, 3)
    # Throughput is per-image: batch_size images processed per batch call.
    throughput_fps = (
        round(batch_size / mean_batch_seconds, 3) if mean_batch_seconds > 0 else 0.0
    )
    size_bytes, size_mb = measure_model_size(weights_path)

    return {
        "status": "measured",
        "note": (
            f"Measured over {runs} timed run(s) after {max(0, warmup)} warm-up "
            f"iteration(s) on device '{device}'."
        ),
        "latency_ms": latency_ms,
        "throughput_fps": throughput_fps,
        "device": device,
        "batch_size": batch_size,
        "model_size_bytes": size_bytes,
        "model_size_mb": size_mb,
        "runs": runs,
    }
