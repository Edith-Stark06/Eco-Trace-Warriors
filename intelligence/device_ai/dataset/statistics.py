"""Aggregate dataset statistics.

:class:`StatisticsCalculator` folds a list of analysed
:class:`~device_ai.dataset.records.ImageRecord` objects (and an optional
:class:`~device_ai.dataset.records.DuplicateReport`) into a single
:class:`~device_ai.dataset.records.DatasetStatistics` snapshot: counts by
format and colour mode, resolution bounds/means, aggregate quality flags and
duplicate totals.

The calculator is pure (no I/O) so it is trivial to unit-test and reuse from
both the statistics endpoint and the reporting module.
"""

from __future__ import annotations

from .records import (
    DatasetStatistics,
    DuplicateReport,
    ImageRecord,
    QualitySummary,
    ResolutionStats,
)


def _count_by(records: list[ImageRecord], key: str) -> dict[str, int]:
    """Return a sorted frequency mapping over a string attribute."""
    counts: dict[str, int] = {}
    for record in records:
        value = getattr(record, key) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _resolution_stats(records: list[ImageRecord]) -> ResolutionStats | None:
    """Return resolution summary statistics over decodable images."""
    widths = [r.width for r in records if not r.quality.is_corrupted and r.width > 0]
    heights = [r.height for r in records if not r.quality.is_corrupted and r.height > 0]
    if not widths or not heights:
        return None
    return ResolutionStats(
        min_width=min(widths),
        max_width=max(widths),
        min_height=min(heights),
        max_height=max(heights),
        mean_width=round(sum(widths) / len(widths), 1),
        mean_height=round(sum(heights) / len(heights), 1),
    )


def _quality_summary(records: list[ImageRecord]) -> QualitySummary:
    """Return the aggregate quality summary over all records."""
    decodable = [r for r in records if not r.quality.is_corrupted]
    blur_scores = [r.quality.blur_score for r in decodable]
    brightness = [r.quality.brightness for r in decodable]
    return QualitySummary(
        blurry=sum(1 for r in records if r.quality.is_blurry),
        dark=sum(1 for r in records if r.quality.is_dark),
        bright=sum(1 for r in records if r.quality.is_bright),
        low_resolution=sum(1 for r in records if r.quality.is_low_resolution),
        corrupted=sum(1 for r in records if r.quality.is_corrupted),
        mean_blur_score=(
            round(sum(blur_scores) / len(blur_scores), 2) if blur_scores else 0.0
        ),
        mean_brightness=(
            round(sum(brightness) / len(brightness), 2) if brightness else 0.0
        ),
    )


class StatisticsCalculator:
    """Compute :class:`DatasetStatistics` from analysed records."""

    def compute(
        self,
        records: list[ImageRecord],
        *,
        duplicates: DuplicateReport | None = None,
    ) -> DatasetStatistics:
        """Fold records (and optional duplicates) into a statistics snapshot.

        Args:
            records: Analysed image records.
            duplicates: Optional duplicate-detection result to fold in.

        Returns:
            The populated :class:`DatasetStatistics`.
        """
        return DatasetStatistics(
            total_images=len(records),
            total_size_bytes=sum(r.size_bytes for r in records),
            format_counts=_count_by(records, "image_format"),
            mode_counts=_count_by(records, "mode"),
            resolution=_resolution_stats(records),
            quality=_quality_summary(records),
            duplicate_groups=len(duplicates.pairs) if duplicates else 0,
            duplicate_images=duplicates.num_duplicates if duplicates else 0,
        )


def statistics_to_dict(stats: DatasetStatistics) -> dict[str, object]:
    """Convert :class:`DatasetStatistics` into a JSON-serialisable dict.

    Args:
        stats: The statistics snapshot.

    Returns:
        A primitive-only mapping.
    """
    resolution: dict[str, float] | None = None
    if stats.resolution is not None:
        resolution = {
            "min_width": stats.resolution.min_width,
            "max_width": stats.resolution.max_width,
            "min_height": stats.resolution.min_height,
            "max_height": stats.resolution.max_height,
            "mean_width": stats.resolution.mean_width,
            "mean_height": stats.resolution.mean_height,
        }
    return {
        "total_images": stats.total_images,
        "total_size_bytes": stats.total_size_bytes,
        "total_size_mb": stats.total_size_mb,
        "format_counts": stats.format_counts,
        "mode_counts": stats.mode_counts,
        "resolution": resolution,
        "quality": {
            "blurry": stats.quality.blurry,
            "dark": stats.quality.dark,
            "bright": stats.quality.bright,
            "low_resolution": stats.quality.low_resolution,
            "corrupted": stats.quality.corrupted,
            "mean_blur_score": stats.quality.mean_blur_score,
            "mean_brightness": stats.quality.mean_brightness,
        },
        "duplicates": {
            "groups": stats.duplicate_groups,
            "images": stats.duplicate_images,
        },
    }
