"""Integration tests for GET /model and ensemble inference pipeline integration.

Validates:
- GET /model returns correct metadata and canonical 8-class taxonomy.
- GET /model reflects inference_mode from settings.
- POST /predict succeeds end-to-end with EnsembleDetector wired in.
"""

from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.inference.class_map import CANONICAL_CLASSES
from device_ai.inference.ensemble_detector import EnsembleDetector
from device_ai.inference.pipeline import build_detection_pipeline


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


def _make_test_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(100, 150, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_get_model_endpoint_single_model() -> None:
    """GET /model returns single_model mode and complete 8-class taxonomy."""
    settings = Settings(
        environment="development",
        max_images=4,
        min_images=1,
        max_file_size=1024 * 1024,
        inference_mode="single_model",
        log_level="WARNING",
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        resp = client.get("/model")
        assert resp.status_code == 200
        data = resp.json()

        assert data["inference_mode"] == "single_model"
        assert "detector" in data
        assert data["detector"]["name"] == "detector"
        assert "class_map" in data
        assert len(data["class_map"]) == 8
        assert data["class_map"]["0"] == "laptop"
        assert data["class_map"]["7"] == "headphones"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_get_model_endpoint_ensemble_mode() -> None:
    """GET /model returns ensemble mode when configured."""
    settings = Settings(
        environment="development",
        inference_mode="ensemble",
        log_level="WARNING",
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        resp = client.get("/model")
        assert resp.status_code == 200
        data = resp.json()

        assert data["inference_mode"] == "ensemble"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


def test_predict_with_ensemble_detector() -> None:
    """POST /predict runs end-to-end when wired with an EnsembleDetector."""
    boxes_a = _FakeBoxes(
        xyxy=[[10.0, 10.0, 50.0, 50.0]],
        conf=[0.92],
        cls=[1],  # smartphone
    )
    boxes_b = _FakeBoxes(
        xyxy=[[12.0, 12.0, 52.0, 52.0]],
        conf=[0.88],
        cls=[1],  # smartphone
    )
    detector = EnsembleDetector(
        model_a=_FakeModel(boxes_a),
        model_b=_FakeModel(boxes_b),
    )

    pipeline = build_detection_pipeline(
        detector=detector,
        model_version="1.0.0",
        year=2026,
    )

    settings = Settings(
        environment="development",
        inference_mode="ensemble",
        log_level="WARNING",
    )
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[dependencies.get_pipeline] = lambda: pipeline

    with TestClient(app) as client:
        png_bytes = _make_test_png()
        resp = client.post(
            "/predict",
            files=[("images", ("phone.png", png_bytes, "image/png"))],
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["device_type"] == "Smartphone"
        assert body["confidence"] > 0.8
        assert body["eco_id"].startswith("ET-2026-")

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
