"""Shared pytest fixtures for the Device Intelligence Engine test suite.

Fixtures build in-memory test images and a FastAPI test client wired to a
fresh application with test-friendly settings, so no network, filesystem or
trained models are required.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings


def make_image_bytes(
    *,
    size: tuple[int, int] = (256, 256),
    fmt: str = "PNG",
    color: tuple[int, int, int] = (120, 160, 200),
    noise: bool = False,
) -> bytes:
    """Return encoded image bytes for use in upload tests.

    Args:
        size: ``(width, height)`` of the generated image.
        fmt: Pillow format name (``"PNG"``, ``"JPEG"``, ``"WEBP"``).
        color: Solid fill colour (ignored when ``noise`` is True).
        noise: When True, fill with deterministic pseudo-random pixels so the
            encoded output does not compress to a trivial size (used by
            large-file tests).

    Returns:
        Encoded image bytes.
    """
    buffer = BytesIO()
    if noise:
        # Seeded RNG keeps the bytes deterministic across test runs while
        # producing an incompressible image large enough to exceed limits.
        rng = np.random.default_rng(seed=size[0] * size[1])
        pixels = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
        image = Image.fromarray(pixels, mode="RGB")
    else:
        image = Image.new("RGB", size, color)
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture()
def test_settings() -> Settings:
    """Return settings suitable for tests (small limits, no JSON logs)."""
    return Settings(
        environment="development",
        max_images=6,
        min_images=1,
        max_file_size=1 * 1024 * 1024,  # 1 MB keeps large-file tests fast
        min_image_dimension=32,
        max_image_dimension=4096,
        log_level="WARNING",
        json_logs=False,
        model_version="1.0.0",
    )


@pytest.fixture()
def dataset_settings(tmp_path: Path) -> Settings:
    """Return settings whose dataset root is an isolated temp directory."""
    return Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        dataset_dir=tmp_path / "datasets",
        blur_threshold=100.0,
    )


@pytest.fixture()
def dataset_client(dataset_settings: Settings) -> Iterator[TestClient]:
    """Yield a TestClient whose dataset service uses ``dataset_settings``."""
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=dataset_settings)
    app.dependency_overrides[get_settings] = lambda: dataset_settings
    app.dependency_overrides[dependencies.get_dataset_service] = (
        lambda: dependencies.get_dataset_service(dataset_settings)
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


@pytest.fixture()
def client(test_settings: Settings) -> Iterator[TestClient]:
    """Yield a TestClient bound to a fresh app using ``test_settings``."""
    # Point the settings singleton at the test settings so dependencies and
    # the app factory observe the same configuration.
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=test_settings)
    # Override the settings provider so routes receive the test settings.
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


@pytest.fixture()
def png_bytes() -> bytes:
    """A small valid PNG image."""
    return make_image_bytes(fmt="PNG")


@pytest.fixture()
def jpeg_bytes() -> bytes:
    """A small valid JPEG image."""
    return make_image_bytes(fmt="JPEG")


def write_image(
    path: Path,
    *,
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (120, 160, 200),
    noise: bool = False,
    seed: int = 1,
    fmt: str = "PNG",
) -> Path:
    """Write an image file to ``path`` and return it.

    Args:
        path: Destination file path (parent directories are created).
        size: ``(width, height)`` of the image.
        color: Solid fill colour (ignored when ``noise`` is True).
        noise: When True, fill with seeded pseudo-random pixels so the
            content (and hashes) are non-trivial and unique per seed.
        seed: RNG seed used when ``noise`` is True.
        fmt: Pillow format name.

    Returns:
        The written path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if noise:
        rng = np.random.default_rng(seed)
        pixels = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
        image = Image.fromarray(pixels, mode="RGB")
    else:
        image = Image.new("RGB", size, color)
    image.save(path, format=fmt)
    return path


@pytest.fixture()
def training_settings(tmp_path: Path) -> Settings:
    """Return settings whose artifact/mlruns roots are isolated temp dirs."""
    return Settings(
        environment="development",
        log_level="WARNING",
        json_logs=False,
        artifact_dir=tmp_path / "artifacts",
        mlruns_dir=tmp_path / "mlruns",
        experiment_tracker="json",
        training_seed=7,
    )


@pytest.fixture()
def run_config():
    """Return a small, fully-specified run configuration for training tests."""
    from device_ai.training.config import OptimizerConfig, RunConfig, TrainingConfig

    return RunConfig(
        model_name="device-detector",
        trainer="mock",
        experiment_name="test-exp",
        training=TrainingConfig(
            epochs=3,
            batch_size=4,
            seed=7,
            device="cpu",
            model_version="1.0.0",
            early_stopping_patience=0,
        ),
        optimizer=OptimizerConfig(learning_rate=0.01, warmup_epochs=1),
        tags={"suite": "unit"},
    )


@pytest.fixture()
def mock_trainer_cls() -> type:
    """Return a concrete ``BaseTrainer`` subclass for lifecycle tests.

    The trainer trains a trivial in-memory model over fixed batches, producing
    deterministic decreasing losses so early-stopping/checkpoint behaviour is
    predictable.
    """
    from device_ai.training.core.trainer import BaseTrainer

    class MockTrainer(BaseTrainer):
        """A tiny deterministic trainer used only in tests."""

        framework = "mock"
        monitor_metric = "val_loss"
        monitor_mode = "min"

        def build_model(self) -> dict[str, float]:
            return {"weight": 0.0}

        def train_loader(self) -> list[int]:
            return [0, 1, 2, 3]

        def val_loader(self) -> list[int]:
            return [0, 1]

        def train_step(self, model: dict[str, float], batch: int) -> dict[str, float]:
            return {"loss": 1.0 / (batch + 1)}

        def validation_step(
            self, model: dict[str, float], batch: int
        ) -> dict[str, float]:
            return {"loss": 0.5 / (batch + 1)}

    return MockTrainer


@pytest.fixture()
def fingerprint_settings() -> Settings:
    """Return settings for fingerprint tests (mock encoder + in-memory store)."""
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
        fingerprint_metric="cosine",
        fingerprint_match_threshold=0.85,
        fingerprint_backend="memory",
    )


@pytest.fixture()
def fingerprint_client(fingerprint_settings: Settings) -> Iterator[TestClient]:
    """Yield a TestClient whose fingerprint service uses ``fingerprint_settings``.

    The encoder/repository come from the (reset) cached singletons — in the
    base environment that is the deterministic mock encoder and the in-memory
    repository, so no torch/OpenCLIP is required.
    """
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=fingerprint_settings)
    app.dependency_overrides[get_settings] = lambda: fingerprint_settings
    app.dependency_overrides[dependencies.get_fingerprint_service] = (
        lambda: dependencies.get_fingerprint_service(fingerprint_settings)
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


@pytest.fixture()
def fake_encoder():  # noqa: ANN201 - test fixture returns a concrete encoder
    """Return a deterministic mock embedding encoder (no torch required)."""
    from device_ai.inference.predictor import MockEmbeddingEncoder

    return MockEmbeddingEncoder()


@pytest.fixture()
def sample_fingerprint():  # noqa: ANN201 - test fixture returns a DeviceFingerprint
    """Return a small, deterministic ``DeviceFingerprint`` for unit tests."""
    from datetime import UTC, datetime

    from device_ai.fingerprint.models import DeviceFingerprint, compute_fingerprint
    from device_ai.inference.predictor import l2_normalize

    embedding = l2_normalize((0.1, 0.2, 0.3, 0.4))
    return DeviceFingerprint(
        eco_id="ET-2026-0000ABCD",
        fingerprint=compute_fingerprint(embedding),
        embedding=embedding,
        dimension=len(embedding),
        encoder_name="clip",
        encoder_version="mock-clip-1.0.0",
        metric="cosine",
        created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
        source_hashes=("a" * 64,),
        device_type="Laptop",
        brand="Dell",
    )


@pytest.fixture()
def populated_dataset(dataset_settings: Settings) -> Settings:
    """Populate the dataset ``raw`` and ``labels`` dirs with sample data.

    Creates four raw images (one an exact duplicate, one dark) plus matching
    YOLO labels for two of them, then returns the settings pointing at that
    dataset root.
    """
    raw = dataset_settings.dataset_dir / "raw"
    labels = dataset_settings.dataset_dir / "labels"
    write_image(raw / "a.png", noise=True, seed=1)
    write_image(raw / "b.png", color=(8, 8, 8))  # dark
    write_image(raw / "c.png", noise=True, seed=1)  # exact duplicate of a
    write_image(raw / "d.png", noise=True, seed=2)
    labels.mkdir(parents=True, exist_ok=True)
    (labels / "a.txt").write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
    (labels / "b.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    return dataset_settings


@pytest.fixture()
def ocr_settings() -> Settings:
    """Return settings for OCR tests (mock backend + barcode reader enabled)."""
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
        ocr_backend="mock",
        ocr_languages=("en",),
        ocr_min_confidence=0.30,
        barcode_enabled=True,
    )


@pytest.fixture()
def ocr_client(ocr_settings: Settings) -> Iterator[TestClient]:
    """Yield a TestClient whose OCR service uses ``ocr_settings``.

    The backend/barcode reader come from the (reset) cached singletons — in the
    base environment those are the deterministic mocks, so no easyocr/OpenCV is
    required.
    """
    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(settings=ocr_settings)
    app.dependency_overrides[get_settings] = lambda: ocr_settings
    app.dependency_overrides[dependencies.get_ocr_service] = (
        lambda: dependencies.get_ocr_service(ocr_settings)
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()


@pytest.fixture()
def fake_ocr_backend():  # noqa: ANN201 - test fixture returns an OCR backend
    """Return an ``EasyOCRBackend`` with an injected recognize function.

    The injected function returns fixed ``(bbox, text, confidence)`` rows so the
    real adapter's row-mapping path is exercised without easyocr installed.
    """
    from device_ai.ocr.backends import EasyOCRBackend

    def recognize(images):  # noqa: ANN001, ANN202 - local test stub
        rows = [
            ([[0, 0], [10, 0], [10, 5], [0, 5]], "Dell", 0.95),
            ([[0, 6], [20, 6], [20, 11], [0, 11]], "S/N: ABC12345", 0.90),
        ]
        return [rows for _ in images]

    return EasyOCRBackend(recognize_fn=recognize)


@pytest.fixture()
def sample_spans():  # noqa: ANN201 - test fixture returns a list of TextSpan
    """Return a deterministic list of raw spans covering every field type."""
    from device_ai.ocr.models import TextSpan

    return [
        TextSpan(text="Dell", confidence=0.95),
        TextSpan(text="Model: XPS 15", confidence=0.9),
        TextSpan(text="S/N: ABC12345", confidence=0.92),
        TextSpan(text="IMEI: 490154203237518", confidence=0.88),
        TextSpan(text="MAC: 00:1A:2B:3C:4D:5E", confidence=0.85),
    ]
