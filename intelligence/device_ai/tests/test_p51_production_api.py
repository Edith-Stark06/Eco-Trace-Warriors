"""Comprehensive integration and unit tests for P5.1 Device Intelligence API Productionization.

Covers:
- Enhanced prediction payload with request IDs, inference mode, detections, and timing breakdown.
- Request ID correlation across client headers, response headers, and response payloads.
- Request validation for invalid/corrupted/empty/oversized/unsupported inputs.
- Detector readiness guards and graceful inference failure handling.
- /health and /model endpoint hardening.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.exceptions import ModelNotLoadedError
from device_ai.inference.class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID
from device_ai.inference.ensemble_detector import EnsembleDetector
from device_ai.inference.pipeline import PredictionPipeline, build_detection_pipeline
from device_ai.inference.predictor import (
    Detection,
    DetectionResult,
    Detector,
    MockConditionAssessor,
    MockEmbeddingEncoder,
    MockMaterialEstimator,
    MockOCREngine,
)
from device_ai.inference.ecoid import EcoIDGenerator
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

    def predict(self, frame: object, **kwargs: object) -> list[_FakeResult]:
        return [_FakeResult(self._boxes)]


class _CrashingDetector(Detector):
    """A detector that simulates an unexpected runtime inference error."""

    version = "crashing-1.0.0"

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        raise RuntimeError("GPU Out Of Memory Simulation")


class _NotReadyDetector(Detector):
    """A detector that reports ready=False and raises ModelNotLoadedError."""

    version = "notready-1.0.0"

    @property
    def is_ready(self) -> bool:
        return False

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        raise ModelNotLoadedError("Detector artifact is missing.")


def _make_png_bytes(w: int = 128, h: int = 128, color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def p51_settings() -> Settings:
    return Settings(
        environment="development",
        max_images=4,
        min_images=1,
        max_file_size=1 * 1024 * 1024,
        min_image_dimension=32,
        max_image_dimension=4096,
        inference_mode="single_model",
        log_level="WARNING",
    )


def test_predict_production_response_schema(p51_settings: Settings) -> None:
    """POST /predict returns the complete P5.1 schema with detections and timing."""
    boxes = _FakeBoxes(
        xyxy=[[20.0, 20.0, 100.0, 100.0]],
        conf=[0.94],
        cls=[0],  # laptop
    )
    detector = EnsembleDetector(
        model_a=_FakeModel(boxes),
        model_b=_FakeModel(boxes),
    )
    pipeline = build_detection_pipeline(
        detector=detector,
        model_version="1.0.0",
        year=2026,
    )

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        png_bytes = _make_png_bytes()
        resp = client.post(
            "/predict",
            files=[("images", ("test_device.png", png_bytes, "image/png"))],
            headers={"X-Request-ID": "req-trace-p51-001"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.headers.get("X-Request-ID") == "req-trace-p51-001"

        data = resp.json()

        # Core backward-compatible fields
        assert data["eco_id"].startswith("ET-2026-")
        assert data["device_type"] == "Laptop"
        assert data["brand"] == "Unknown"
        assert pytest.approx(data["confidence"], 1e-2) == 0.94
        assert "condition" in data
        assert "ocr" in data
        assert "materials" in data
        assert 0.0 <= data["carbon_score"] <= 100.0
        assert data["model_version"] == "1.0.0"

        # P5.1 enhanced metadata
        assert data["request_id"] == "req-trace-p51-001"
        assert data["inference_mode"] == "single_model"

        # Detailed detections array
        assert isinstance(data["detections"], list)
        assert len(data["detections"]) == 1
        det = data["detections"][0]
        assert det["class_id"] == 0
        assert det["class_name"] == "laptop"
        assert pytest.approx(det["confidence"], 1e-2) == 0.94
        assert len(det["bounding_box"]) == 4

        # Latency breakdown
        assert "timing" in data
        timing = data["timing"]
        assert timing["preprocessing_ms"] >= 0.0
        assert timing["inference_ms"] >= 0.0
        assert timing["postprocessing_ms"] >= 0.0
        assert timing["total_ms"] >= 0.0

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_generates_request_id_when_omitted(p51_settings: Settings) -> None:
    """When client omits X-Request-ID, a unique ID is generated and returned in headers & body."""
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        png_bytes = _make_png_bytes()
        resp = client.post(
            "/predict",
            files=[("images", ("device.png", png_bytes, "image/png"))],
        )

        assert resp.status_code == 200
        header_id = resp.headers.get("X-Request-ID")
        assert header_id is not None
        assert len(header_id) > 0
        assert resp.json()["request_id"] == header_id

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_rejects_empty_file(p51_settings: Settings) -> None:
    """Zero-byte file upload returns a 413 FILE_TOO_LARGE controlled error envelope."""
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            files=[("images", ("empty.png", b"", "image/png"))],
        )
        assert resp.status_code == 413
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "FILE_TOO_LARGE"
        assert "empty" in data["error"]["message"].lower()

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_rejects_corrupted_image(p51_settings: Settings) -> None:
    """Corrupt image returns a 422 CORRUPTED_IMAGE controlled error envelope."""
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            files=[("images", ("corrupt.jpg", b"invalid-garbage-bytes", "image/jpeg"))],
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "CORRUPTED_IMAGE"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_rejects_unsupported_media_type(p51_settings: Settings) -> None:
    """Unsupported MIME/extension returns 415 UNSUPPORTED_MEDIA_TYPE."""
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            files=[("images", ("document.pdf", b"%PDF-1.4...", "application/pdf"))],
        )
        assert resp.status_code == 415
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_detector_not_ready_returns_503(p51_settings: Settings) -> None:
    """When detector is not ready, POST /predict returns 503 MODEL_NOT_LOADED error."""
    pipeline = PredictionPipeline(
        detector=_NotReadyDetector(),
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=2026),
        model_version="1.0.0",
    )

    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            files=[("images", ("device.png", _make_png_bytes(), "image/png"))],
        )
        assert resp.status_code == 503
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "MODEL_NOT_LOADED"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_handles_inference_exception_gracefully(p51_settings: Settings) -> None:
    """When model crashes unexpectedly during forward pass, returns controlled 500 INFERENCE_ERROR."""
    pipeline = PredictionPipeline(
        detector=_CrashingDetector(),
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=2026),
        model_version="1.0.0",
    )

    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            files=[("images", ("device.png", _make_png_bytes(), "image/png"))],
        )
        assert resp.status_code == 500
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INFERENCE_ERROR"
        assert "failed" in data["error"]["message"].lower()

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_health_endpoint_hardened(p51_settings: Settings) -> None:
    """GET /health returns healthy status, inference_mode, and per-component readiness."""
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["inference_mode"] == "single_model"
        assert isinstance(data["components"], list)
        assert len(data["components"]) >= 5

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_model_endpoint_hardened(p51_settings: Settings) -> None:
    """GET /model returns detector metadata and complete canonical class taxonomy."""
    app = create_app(p51_settings)
    app.dependency_overrides[get_settings] = lambda: p51_settings

    with TestClient(app) as client:
        resp = client.get("/model")
        assert resp.status_code == 200
        data = resp.json()

        assert data["inference_mode"] == "single_model"
        assert "detector" in data
        assert "class_map" in data
        assert len(data["class_map"]) == 8
        assert data["class_map"]["0"] == "laptop"
        assert data["class_map"]["1"] == "smartphone"
        assert data["class_map"]["2"] == "tablet"
        assert data["class_map"]["3"] == "monitor"
        assert data["class_map"]["4"] == "printer"
        assert data["class_map"]["5"] == "mouse"
        assert data["class_map"]["6"] == "camera"
        assert data["class_map"]["7"] == "headphones"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
