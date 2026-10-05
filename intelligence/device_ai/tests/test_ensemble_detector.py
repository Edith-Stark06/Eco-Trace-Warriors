"""Unit tests for the EnsembleDetector using injected fakes.

Validates:
- Readiness check (both models required).
- Exception raised when not ready.
- End-to-end detection aggregation with WBF fusion.
- Canonical class mapping.
- Empty detection fallback.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from device_ai.exceptions import ModelNotLoadedError
from device_ai.inference.class_map import CANONICAL_CLASSES
from device_ai.inference.ensemble_detector import EnsembleDetector
from device_ai.inference.predictor import DetectionResult
from device_ai.preprocessing.image_loader import LoadedImage


class _FakeBoxes:
    def __init__(self, xyxy: list[list[float]], conf: list[float], cls: list[int]) -> None:
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls

    def __len__(self) -> int:
        return len(self.xyxy)


class _FakeResult:
    def __init__(self, boxes: _FakeBoxes | None) -> None:
        self.boxes = boxes


class _FakeModel:
    def __init__(self, boxes: _FakeBoxes | None) -> None:
        self._boxes = boxes
        self.predict_kwargs: dict[str, object] = {}

    def predict(self, frame: object, **kwargs: object) -> list[_FakeResult]:
        self.predict_kwargs = kwargs
        return [_FakeResult(self._boxes)]


def _make_loaded_image(w: int = 640, h: int = 480) -> LoadedImage:
    image = Image.new("RGB", (w, h), color=(128, 128, 128))
    return LoadedImage(
        filename="test.jpg",
        content_type="image/jpeg",
        raw=b"dummy_raw_bytes",
        image=image,
        sha256="sha256_dummy",
    )


def test_ensemble_not_ready_when_missing_models() -> None:
    """Detector is not ready if either model is missing."""
    d1 = EnsembleDetector(model_a=None, model_b=None)
    assert not d1.is_ready

    d2 = EnsembleDetector(model_a=_FakeModel(None), model_b=None)
    assert not d2.is_ready

    d3 = EnsembleDetector(model_a=None, model_b=_FakeModel(None))
    assert not d3.is_ready


def test_ensemble_ready_when_both_models_present() -> None:
    """Detector is ready when both models are supplied."""
    detector = EnsembleDetector(
        model_a=_FakeModel(None),
        model_b=_FakeModel(None),
    )
    assert detector.is_ready
    assert detector.name == "detector"
    assert "ensemble" in detector.version


def test_detect_raises_when_not_ready() -> None:
    """Calling detect() without loaded models raises ModelNotLoadedError."""
    detector = EnsembleDetector(model_a=None, model_b=None)
    with pytest.raises(ModelNotLoadedError):
        detector.detect([_make_loaded_image()])


def test_detect_fuses_two_models_concordantly() -> None:
    """Two models detecting the same object produce a single fused detection."""
    # Model A detects class 0 (laptop) at [100, 100, 300, 300] with conf=0.85
    boxes_a = _FakeBoxes(
        xyxy=[[100.0, 100.0, 300.0, 300.0]],
        conf=[0.85],
        cls=[0],
    )
    # Model B detects class 0 (laptop) at [104, 104, 304, 304] with conf=0.85
    boxes_b = _FakeBoxes(
        xyxy=[[104.0, 104.0, 304.0, 304.0]],
        conf=[0.85],
        cls=[0],
    )

    detector = EnsembleDetector(
        model_a=_FakeModel(boxes_a),
        model_b=_FakeModel(boxes_b),
        weights=(0.5, 0.5),
        confidence_threshold=0.25,
    )

    result = detector.detect([_make_loaded_image(w=640, h=480)])

    assert isinstance(result, DetectionResult)
    assert result.device_type == "Laptop"
    assert result.brand == "Unknown"
    assert len(result.detections) == 1
    assert result.detections[0].label == "laptop"
    assert pytest.approx(result.confidence, 1e-3) == 0.85
    # Bounding box should be close to (102, 102, 302, 302)
    bx1, by1, bx2, by2 = result.detections[0].bounding_box
    assert 100 <= bx1 <= 104
    assert 100 <= by1 <= 104
    assert 300 <= bx2 <= 304
    assert 300 <= by2 <= 304


def test_detect_empty_results_returns_unknown() -> None:
    """When both models return empty boxes, result is Unknown."""
    detector = EnsembleDetector(
        model_a=_FakeModel(None),
        model_b=_FakeModel(None),
    )
    result = detector.detect([_make_loaded_image()])

    assert result.device_type == "Unknown"
    assert result.confidence == 0.0
    assert len(result.detections) == 0
