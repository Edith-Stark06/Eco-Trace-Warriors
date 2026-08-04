"""Tests for statistics, versioning and report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.records import (
    ImageRecord,
    PerceptualHashes,
    QualityMetrics,
)
from device_ai.dataset.reporting import ReportBuilder
from device_ai.dataset.statistics import StatisticsCalculator, statistics_to_dict
from device_ai.dataset.versioning import (
    DatasetVersionManager,
    compute_content_hash,
)


def _metrics(**overrides) -> QualityMetrics:
    base = {
        "blur_score": 500.0,
        "brightness": 128.0,
        "is_blurry": False,
        "is_dark": False,
        "is_bright": False,
        "is_low_resolution": False,
        "is_corrupted": False,
        "issues": (),
    }
    base.update(overrides)
    return QualityMetrics(**base)


def _record(
    path: str, *, sha: str, width: int = 64, height: int = 48, **q
) -> ImageRecord:
    return ImageRecord(
        relative_path=path,
        filename=path,
        image_format="PNG",
        mode="RGB",
        width=width,
        height=height,
        size_bytes=1024,
        hashes=PerceptualHashes(
            sha256=sha,
            ahash="0000000000000000",
            dhash="0000000000000000",
            phash="0000000000000000",
        ),
        quality=_metrics(**q),
    )


# --- Statistics ------------------------------------------------------------


def test_statistics_counts_and_sizes():
    """Totals, format counts and resolution bounds are computed correctly."""
    records = [
        _record("a.png", sha="a"),
        _record("b.png", sha="b", width=128, height=96),
    ]
    stats = StatisticsCalculator().compute(records)
    assert stats.total_images == 2
    assert stats.total_size_bytes == 2048
    assert stats.format_counts == {"PNG": 2}
    assert stats.resolution is not None
    assert stats.resolution.min_width == 64
    assert stats.resolution.max_width == 128


def test_statistics_folds_in_duplicates():
    """Duplicate totals are folded into the statistics snapshot."""
    records = [
        _record("a.png", sha="same"),
        _record("b.png", sha="same"),
    ]
    duplicates = DuplicateDetector(hamming_threshold=0).detect(records)
    stats = StatisticsCalculator().compute(records, duplicates=duplicates)
    assert stats.duplicate_images == 1
    assert stats.duplicate_groups == 1


def test_statistics_quality_summary_counts_flags():
    """Aggregate quality counts reflect the per-record flags."""
    records = [
        _record("a.png", sha="a", is_blurry=True, issues=("blurry",)),
        _record("b.png", sha="b", is_dark=True, issues=("dark",)),
        _record("c.png", sha="c"),
    ]
    stats = StatisticsCalculator().compute(records)
    assert stats.quality.blurry == 1
    assert stats.quality.dark == 1


def test_statistics_to_dict_shape():
    """The serialised statistics match the API response contract."""
    stats = StatisticsCalculator().compute([_record("a.png", sha="a")])
    payload = statistics_to_dict(stats)
    assert set(payload) >= {
        "total_images",
        "total_size_bytes",
        "total_size_mb",
        "format_counts",
        "mode_counts",
        "resolution",
        "quality",
        "duplicates",
    }
    assert payload["duplicates"] == {"groups": 0, "images": 0}


def test_statistics_empty_dataset_has_no_resolution():
    """An empty dataset produces a null resolution summary."""
    stats = StatisticsCalculator().compute([])
    assert stats.resolution is None
    assert statistics_to_dict(stats)["resolution"] is None


# --- Versioning ------------------------------------------------------------


def test_compute_content_hash_is_order_independent():
    """The aggregate content hash ignores manifest insertion order."""
    a = compute_content_hash({"a.png": "1", "b.png": "2"})
    b = compute_content_hash({"b.png": "2", "a.png": "1"})
    assert a == b


def test_version_manager_is_monotonic(tmp_path: Path):
    """Successive snapshots receive monotonically increasing labels."""
    manager = DatasetVersionManager(tmp_path)
    when = datetime(2026, 1, 1, tzinfo=UTC)
    v1 = manager.create_version([_record("a.png", sha="a")], created_at=when)
    v2 = manager.create_version([_record("a.png", sha="a")], created_at=when)
    assert v1.version == "v1"
    assert v2.version == "v2"
    assert manager.latest().version == "v2"
    assert len(manager.list_versions()) == 2


def test_identical_content_yields_identical_hash(tmp_path: Path):
    """Two snapshots of the same content share a content hash."""
    manager = DatasetVersionManager(tmp_path)
    when = datetime(2026, 1, 1, tzinfo=UTC)
    records = [_record("a.png", sha="a"), _record("b.png", sha="b")]
    v1 = manager.create_version(records, created_at=when)
    v2 = manager.create_version(records, created_at=when)
    assert v1.content_hash == v2.content_hash


def test_versions_persist_across_managers(tmp_path: Path):
    """Versions written by one manager are visible to a fresh instance."""
    when = datetime(2026, 1, 1, tzinfo=UTC)
    DatasetVersionManager(tmp_path).create_version(
        [_record("a.png", sha="a")], created_at=when, note="first"
    )
    reloaded = DatasetVersionManager(tmp_path).latest()
    assert reloaded is not None
    assert reloaded.note == "first"


# --- Reporting -------------------------------------------------------------


def test_report_document_includes_all_sections():
    """The JSON report carries statistics, duplicates and annotations."""
    records = [_record("a.png", sha="a"), _record("b.png", sha="a")]
    duplicates = DuplicateDetector(hamming_threshold=0).detect(records)
    stats = StatisticsCalculator().compute(records, duplicates=duplicates)
    document = ReportBuilder().build(
        statistics=stats,
        duplicates=duplicates,
        annotations=None,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="raw",
    )
    assert document["source"] == "raw"
    assert "statistics" in document
    assert document["duplicates"]["num_duplicates"] == 1


def test_report_html_is_self_contained():
    """The HTML rendering embeds styling and the key metrics, no JS."""
    stats = StatisticsCalculator().compute([_record("a.png", sha="a")])
    builder = ReportBuilder()
    document = builder.build(
        statistics=stats,
        duplicates=None,
        annotations=None,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="raw",
    )
    html = builder.to_html(document)
    assert html.startswith("<!DOCTYPE html>")
    assert "Dataset Intelligence Report" in html
    assert "<script" not in html.lower()
