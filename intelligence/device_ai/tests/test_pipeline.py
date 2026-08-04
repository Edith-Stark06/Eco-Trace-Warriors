"""Unit tests for EcoID generation and the mock prediction pipeline."""

import re

import pytest

from device_ai.inference.ecoid import EcoIDGenerator
from device_ai.inference.pipeline import build_mock_pipeline
from device_ai.preprocessing.image_loader import load_image
from tests.conftest import make_image_bytes

_ECOID_PATTERN = re.compile(r"^ET-\d{4}-[0-9A-F]{8}$")
_ECOID_SEQ_PATTERN = re.compile(r"^ET-\d{4}-\d{8}$")


def test_ecoid_format():
    """Generated EcoIDs match the ET-YYYY-XXXXXXXX format."""
    generator = EcoIDGenerator(year=2026)
    eco_id = generator.generate()
    assert _ECOID_PATTERN.match(eco_id), eco_id


def test_ecoid_uniqueness():
    """Generated EcoIDs are unique across many calls."""
    generator = EcoIDGenerator(year=2026)
    ids = {generator.generate() for _ in range(1000)}
    assert len(ids) == 1000


def test_ecoid_sequential():
    """Sequential EcoIDs increment and are zero-padded."""
    generator = EcoIDGenerator(year=2026, sequence_start=1)
    first = generator.generate_sequential()
    second = generator.generate_sequential()
    assert first == "ET-2026-00000001"
    assert second == "ET-2026-00000002"
    assert _ECOID_SEQ_PATTERN.match(first)


def test_ecoid_rejects_bad_year():
    """A non four-digit year is rejected."""
    with pytest.raises(ValueError):
        EcoIDGenerator(year=26)


def _load(images_bytes):
    return [
        load_image(b, filename="d.png", content_type="image/png") for b in images_bytes
    ]


def test_pipeline_produces_full_result():
    """The mock pipeline returns a complete, well-formed result."""
    pipeline = build_mock_pipeline(model_version="1.0.0", year=2026)
    images = _load([make_image_bytes()])
    result = pipeline.predict(images)

    assert _ECOID_PATTERN.match(result.eco_id)
    assert result.detection.device_type
    assert result.detection.brand
    assert 0.0 <= result.detection.confidence <= 1.0
    assert 0.0 <= result.condition.score <= 1.0
    assert result.materials.composition
    assert 0.0 <= result.carbon_score <= 100.0
    assert result.embedding.embedding_id.startswith("mock_embedding")
    assert result.model_version == "1.0.0"


def test_pipeline_deterministic_for_same_input():
    """Same images → same detection/materials (EcoID excluded)."""
    pipeline = build_mock_pipeline(model_version="1.0.0", year=2026)
    images = _load([make_image_bytes(color=(10, 20, 30))])

    r1 = pipeline.predict(images)
    r2 = pipeline.predict(images)

    assert r1.detection.device_type == r2.detection.device_type
    assert r1.detection.brand == r2.detection.brand
    assert r1.materials.composition == r2.materials.composition
    assert r1.embedding.embedding_id == r2.embedding.embedding_id


def test_pipeline_health_reports_components():
    """Pipeline health reports each component as ready."""
    pipeline = build_mock_pipeline(model_version="1.0.0", year=2026)
    health = pipeline.health()
    assert set(health.keys()) == {
        "detector",
        "condition",
        "ocr",
        "material",
        "clip",
    }
    assert all(health.values())


def test_material_fractions_reasonable():
    """Mock material fractions are positive and sum to about 1.0."""
    pipeline = build_mock_pipeline(model_version="1.0.0", year=2026)
    images = _load([make_image_bytes()])
    result = pipeline.predict(images)
    fractions = result.materials.composition.values()
    assert all(f >= 0.0 for f in fractions)
    assert abs(sum(fractions) - 1.0) < 0.05
