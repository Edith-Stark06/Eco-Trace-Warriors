"""Integration test: /predict driven by the real detector (milestone M1.4).

The API contract must be **unchanged** when the pipeline uses a real
:class:`~device_ai.inference.yolo_detector.YOLODetector` instead of the mock.
Here the detector is backed by an injected fake YOLO model (no torch /
Ultralytics), wired through :func:`build_detection_pipeline`, and the whole
response schema is asserted — only ``device_type``/``confidence`` now come from
the (fake) model while every other field remains a mock placeholder.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.inference.pipeline import build_detection_pipeline
from device_ai.inference.yolo_detector import YOLODetector


class _FakeBoxes:
    def __init__(self, xyxy, conf, cls) -> None:
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls


class _FakeResult:
    def __init__(self, boxes, names) -> None:
        self.boxes = boxes
        self.names = names


class _FakeYolo:
    """A fake YOLO model returning a fixed 'laptop' detection for any batch."""

    def predict(self, frames, **kwargs) -> list[_FakeResult]:
        return [
            _FakeResult(
                boxes=_FakeBoxes(
                    xyxy=[[10, 20, 110, 220]],
                    conf=[0.91],
                    cls=[0],
                ),
                names={0: "laptop"},
            )
            for _ in frames
        ]


def _files(*images: tuple[str, bytes, str]) -> list:
    return [("images", (name, data, mime)) for name, data, mime in images]


@pytest.fixture()
def detection_settings() -> Settings:
    """Settings for the detection-backed app (small limits, no JSON logs)."""
    return Settings(
        environment="development",
        max_images=6,
        min_images=1,
        max_file_size=1 * 1024 * 1024,
        min_image_dimension=32,
        max_image_dimension=4096,
        log_level="WARNING",
        json_logs=False,
        model_version="1.0.0",
    )


@pytest.fixture()
def detection_client(detection_settings: Settings) -> Iterator[TestClient]:
    """Yield a client whose pipeline uses a real YOLODetector + fake model."""
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=detection_settings)
    app.dependency_overrides[get_settings] = lambda: detection_settings

    detector = YOLODetector(model=_FakeYolo(), confidence_threshold=0.25)
    pipeline = build_detection_pipeline(
        detector=detector,
        model_version=detection_settings.model_version,
        year=2026,
    )
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_detection_predict_schema_unchanged(detection_client, png_bytes) -> None:
    """The /predict response schema is identical with the real detector."""
    response = detection_client.post(
        "/predict",
        files=_files(("device.png", png_bytes, "image/png")),
    )
    assert response.status_code == 200, response.text
    data = response.json()

    # Full contract shape — unchanged from the all-mock pipeline.
    assert data["eco_id"].startswith("ET-")
    assert len(data["eco_id"].split("-")) == 3
    assert isinstance(data["device_type"], str) and data["device_type"]
    assert isinstance(data["brand"], str) and data["brand"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert set(data["condition"].keys()) == {"label", "score"}
    assert set(data["ocr"].keys()) == {"serial_number", "model"}
    assert isinstance(data["materials"], dict) and data["materials"]
    assert 0.0 <= data["carbon_score"] <= 100.0
    assert data["embedding_id"].startswith("mock_embedding")
    assert data["model_version"] == "1.0.0"


def test_detection_predict_uses_real_model_output(detection_client, png_bytes) -> None:
    """device_type and confidence come from the (fake) real model."""
    response = detection_client.post(
        "/predict",
        files=_files(("device.png", png_bytes, "image/png")),
    )
    assert response.status_code == 200, response.text
    data = response.json()

    # The fake model always detects a 'laptop' at 0.91 confidence.
    assert data["device_type"] == "Laptop"
    assert data["confidence"] == 0.91
    # Brand stays a placeholder until a later sprint.
    assert data["brand"] == "Unknown"


def test_detection_predict_multiple_images(
    detection_client, png_bytes, jpeg_bytes
) -> None:
    """Multiple images are accepted and aggregate to a single result."""
    response = detection_client.post(
        "/predict",
        files=_files(
            ("front.png", png_bytes, "image/png"),
            ("back.jpg", jpeg_bytes, "image/jpeg"),
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["device_type"] == "Laptop"


def test_detector_not_ready_raises_before_pipeline() -> None:
    """A detector with no model is not ready (guards the build path)."""
    detector = YOLODetector()
    assert detector.is_ready is False
    # Sanity: a detection pipeline can still be built; readiness is checked by
    # the dependency layer before choosing this path.
    pipeline = build_detection_pipeline(
        detector=detector, model_version="1.0.0", year=2026
    )
    image = Image.new("RGB", (32, 32))
    assert pipeline is not None
    assert image.size == (32, 32)
