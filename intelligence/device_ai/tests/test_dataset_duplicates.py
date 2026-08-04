"""Tests for exact and near-duplicate detection."""

from __future__ import annotations

from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.records import (
    ImageRecord,
    PerceptualHashes,
    QualityMetrics,
)

_CLEAN = QualityMetrics(
    blur_score=500.0,
    brightness=128.0,
    is_blurry=False,
    is_dark=False,
    is_bright=False,
    is_low_resolution=False,
    is_corrupted=False,
    issues=(),
)

_FAR_A = "ffffffffffffffff"  # 64 bits from _FAR_B
_FAR_B = "0000000000000000"


def _record(
    path: str,
    *,
    sha: str,
    ahash: str,
    dhash: str,
    phash: str,
) -> ImageRecord:
    return ImageRecord(
        relative_path=path,
        filename=path,
        image_format="PNG",
        mode="RGB",
        width=64,
        height=64,
        size_bytes=100,
        hashes=PerceptualHashes(sha256=sha, ahash=ahash, dhash=dhash, phash=phash),
        quality=_CLEAN,
    )


def test_exact_duplicate_detected_by_sha():
    """Identical SHA-256 marks the later image as an exact duplicate."""
    records = [
        _record("a.png", sha="aa", ahash=_FAR_A, dhash=_FAR_A, phash=_FAR_A),
        _record("b.png", sha="aa", ahash=_FAR_B, dhash=_FAR_B, phash=_FAR_B),
    ]
    report = DuplicateDetector(hamming_threshold=0).detect(records)
    assert report.num_duplicates == 1
    assert report.duplicate_paths == ("b.png",)
    assert report.pairs[0].exact is True
    assert report.pairs[0].distance == 0


def test_near_duplicate_detected_within_threshold():
    """Perceptually close (but byte-different) images are near-duplicates.

    The aHash/dHash are set 64 bits apart so the reported distance is driven
    by the single-bit pHash match — exercising the "min across hashes" rule.
    """
    records = [
        _record(
            "a.png", sha="a1", ahash=_FAR_A, dhash=_FAR_A, phash="ffffffffffffffff"
        ),
        _record(
            "b.png", sha="b2", ahash=_FAR_B, dhash=_FAR_B, phash="fffffffffffffffe"
        ),
    ]
    report = DuplicateDetector(hamming_threshold=5).detect(records)
    assert report.num_duplicates == 1
    assert report.pairs[0].exact is False
    assert report.pairs[0].distance == 1


def test_distant_images_are_not_duplicates():
    """Images beyond the Hamming threshold on every hash stay unique."""
    records = [
        _record("a.png", sha="a1", ahash=_FAR_B, dhash=_FAR_B, phash=_FAR_B),
        _record("b.png", sha="b2", ahash=_FAR_A, dhash=_FAR_A, phash=_FAR_A),
    ]
    report = DuplicateDetector(hamming_threshold=5).detect(records)
    assert report.num_duplicates == 0
    assert report.num_unique == 2


def test_first_in_order_is_retained():
    """The earliest image of a duplicate group is the retained representative."""
    shared = "ffffffffffffffff"
    records = [
        _record("a.png", sha="a1", ahash=shared, dhash=shared, phash=shared),
        _record("b.png", sha="b2", ahash=shared, dhash=shared, phash=shared),
        _record("c.png", sha="c3", ahash=shared, dhash=shared, phash=shared),
    ]
    report = DuplicateDetector(hamming_threshold=2).detect(records)
    assert set(report.duplicate_paths) == {"b.png", "c.png"}
    assert all(pair.source == "a.png" for pair in report.pairs)


def test_corrupted_records_never_match_perceptually():
    """Empty perceptual hashes (corrupted) are not treated as near-duplicates."""
    records = [
        _record("a.png", sha="a1", ahash="", dhash="", phash=""),
        _record("b.png", sha="b2", ahash="", dhash="", phash=""),
    ]
    report = DuplicateDetector(hamming_threshold=5).detect(records)
    assert report.num_duplicates == 0


def test_from_settings_reads_threshold(dataset_settings):
    """The detector honours the configured Hamming threshold."""
    detector = DuplicateDetector.from_settings(dataset_settings)
    assert detector._threshold == dataset_settings.duplicate_hamming_threshold
