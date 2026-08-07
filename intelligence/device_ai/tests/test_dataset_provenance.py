"""Tests for dataset-collection provenance tracking (Sprint P4.1.2, PART 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from device_ai.configs.settings import Settings
from device_ai.dataset.provenance import (
    ProvenanceCollector,
    ProvenanceRecord,
    manifest_to_dict,
    provenance_to_dict,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _make_image(path: Path, colour: tuple[int, int, int] = (120, 120, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), colour).save(path)


def _collector() -> ProvenanceCollector:
    return ProvenanceCollector(Settings(), clock=_fixed_clock)


def test_import_with_provenance_stamps_every_image(tmp_path: Path):
    """Every imported image receives a provenance record."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg", (10, 20, 30))
    _make_image(src / "mouse_field_000001.jpg", (200, 180, 160))
    dst = tmp_path / "raw"

    summary, manifest = _collector().import_with_provenance(
        src,
        dst,
        source="field_collection_2026",
        license_id="CC-BY-4.0",
        contributor="team_ecotrace",
    )

    assert summary.num_imported == 2
    assert len(manifest.records) == 2
    for record in manifest.records.values():
        assert isinstance(record, ProvenanceRecord)
        assert record.source == "field_collection_2026"
        assert record.license == "CC-BY-4.0"
        assert record.contributor == "team_ecotrace"
        assert record.checksum  # non-empty SHA-256


def test_collection_date_falls_back_to_import_timestamp(tmp_path: Path):
    """When no collection date is supplied, the import timestamp is used."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg")
    dst = tmp_path / "raw"

    _, manifest = _collector().import_with_provenance(src, dst, source="field")

    record = next(iter(manifest.records.values()))
    assert record.collection_date == "2026-01-01T00:00:00+00:00"
    assert manifest.import_timestamp == "2026-01-01T00:00:00+00:00"


def test_explicit_collection_date_is_preserved(tmp_path: Path):
    """An explicit collection date overrides the import-timestamp fallback."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg")
    dst = tmp_path / "raw"

    _, manifest = _collector().import_with_provenance(
        src,
        dst,
        source="field",
        collection_date="2025-12-24T09:30:00+00:00",
    )

    record = next(iter(manifest.records.values()))
    assert record.collection_date == "2025-12-24T09:30:00+00:00"


def test_per_image_metadata_overrides_bulk_defaults(tmp_path: Path):
    """Per-image overrides take precedence over the batch defaults."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg", (10, 20, 30))
    _make_image(src / "mouse_field_000001.jpg", (200, 180, 160))
    dst = tmp_path / "raw"

    _, manifest = _collector().import_with_provenance(
        src,
        dst,
        source="field",
        license_id="CC-BY-4.0",
        per_image_metadata={
            "mouse_field_000001.jpg": {
                "source": "donor",
                "license": "public_domain",
            }
        },
    )

    mouse = manifest.records["mouse_field_000001.jpg"]
    laptop = manifest.records["laptop_field_000001.jpg"]
    assert mouse.source == "donor"
    assert mouse.license == "public_domain"
    # The un-overridden image keeps the batch defaults.
    assert laptop.source == "field"
    assert laptop.license == "CC-BY-4.0"


def test_checksum_matches_file_content(tmp_path: Path):
    """The recorded checksum is the SHA-256 of the imported file bytes."""
    from device_ai.dataset.hashing import sha256_hash

    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg")
    dst = tmp_path / "raw"

    _, manifest = _collector().import_with_provenance(src, dst, source="field")

    record = manifest.records["laptop_field_000001.jpg"]
    expected = sha256_hash((dst / "laptop_field_000001.jpg").read_bytes())
    assert record.checksum == expected


def test_manifest_to_dict_is_serialisable(tmp_path: Path):
    """The manifest serialises to a primitive-only dict with a records list."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg")
    dst = tmp_path / "raw"

    _, manifest = _collector().import_with_provenance(
        src, dst, source="field", contributor="alice"
    )
    payload = manifest_to_dict(manifest)

    assert payload["total_images"] == 1
    assert payload["default_source"] == "field"
    assert payload["default_contributor"] == "alice"
    assert isinstance(payload["records"], list)
    assert payload["records"][0]["relative_path"] == "laptop_field_000001.jpg"


def test_provenance_to_dict_shape():
    """A single record serialises to the expected key set."""
    record = ProvenanceRecord(
        relative_path="laptop_field_000001.jpg",
        source="field",
        license="CC-BY-4.0",
        contributor="alice",
        collection_date="2026-01-01T00:00:00+00:00",
        checksum="deadbeef",
    )
    payload = provenance_to_dict(record)
    assert set(payload) == {
        "relative_path",
        "source",
        "license",
        "contributor",
        "collection_date",
        "checksum",
    }


def test_from_settings_builds_collector_with_clock(tmp_path: Path):
    """The from_settings factory accepts an injected clock."""
    src = tmp_path / "src"
    _make_image(src / "laptop_field_000001.jpg")
    dst = tmp_path / "raw"

    collector = ProvenanceCollector.from_settings(Settings(), clock=_fixed_clock)
    _, manifest = collector.import_with_provenance(src, dst, source="field")
    assert manifest.import_timestamp == "2026-01-01T00:00:00+00:00"
