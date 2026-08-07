"""Annotation-derived dataset statistics (Sprint P4.1.2, PART 4).

:class:`~device_ai.dataset.statistics.StatisticsCalculator` summarises the
*images*; this module summarises the *annotations*: class distribution, bounding
box counts and size distribution, orphan labels, annotation completeness, and
which taxonomy classes are missing from the dataset.

It composes existing components rather than re-parsing labels:

* :class:`~device_ai.dataset.validator.AnnotationValidator` supplies the class
  counts, orphan/missing-label sets and box totals.
* :class:`~device_ai.dataset.taxonomy.DeviceTaxonomy` supplies the canonical
  class names so distributions carry real names and missing classes are
  computed against the authoritative 19-class list.

Bounding-box size statistics require the box geometry (not just counts), so the
module re-reads label files through the validator's public
:func:`~device_ai.dataset.validator.parse_yolo_line` — the same parser the
validator uses — keeping a single parsing implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .layout import label_path_for, list_image_paths
from .records import AnnotationReport
from .validator import AnnotationValidator, parse_yolo_line

if TYPE_CHECKING:
    from .taxonomy import DeviceTaxonomy


@dataclass(frozen=True, slots=True)
class BoundingBoxStats:
    """Summary statistics of bounding-box geometry across a dataset.

    All values are in normalised YOLO units (``[0, 1]``); area is
    ``width * height``.

    Attributes:
        total_boxes: Number of bounding boxes measured.
        min_width: Smallest normalised box width.
        max_width: Largest normalised box width.
        mean_width: Mean normalised box width (rounded to 4 decimals).
        min_height: Smallest normalised box height.
        max_height: Largest normalised box height.
        mean_height: Mean normalised box height (rounded to 4 decimals).
        min_area: Smallest normalised box area.
        max_area: Largest normalised box area.
        mean_area: Mean normalised box area (rounded to 4 decimals).
    """

    total_boxes: int
    min_width: float
    max_width: float
    mean_width: float
    min_height: float
    max_height: float
    mean_height: float
    min_area: float
    max_area: float
    mean_area: float


@dataclass(frozen=True, slots=True)
class ClassDistributionEntry:
    """Per-class instance count within the dataset.

    Attributes:
        class_id: The YOLO integer class id.
        class_name: Canonical class name from the taxonomy.
        count: Number of annotated instances of this class.
    """

    class_id: int
    class_name: str
    count: int


@dataclass(frozen=True, slots=True)
class AnnotationStatistics:
    """Aggregate annotation-derived statistics for a dataset.

    Attributes:
        taxonomy_version: Version of the taxonomy the statistics were computed
            against.
        num_classes: Number of classes in the taxonomy.
        total_images: Images considered (with or without labels).
        total_labelled_images: Images that have a matching label file.
        total_boxes: Total bounding boxes across all labels.
        class_distribution: Per-class instance counts (all taxonomy classes,
            including zero-count classes).
        missing_classes: Class names present in the taxonomy but with zero
            annotated instances.
        images_without_labels: Images lacking a label file (annotation gaps).
        orphan_labels: Label files with no matching image.
        annotation_completeness: Fraction of images that have a label file, in
            ``[0, 1]`` (rounded to 4 decimals).
        bounding_box_stats: Bounding-box geometry summary, or ``None`` when
            there are no boxes.
    """

    taxonomy_version: str
    num_classes: int
    total_images: int
    total_labelled_images: int
    total_boxes: int
    class_distribution: tuple[ClassDistributionEntry, ...]
    missing_classes: tuple[str, ...]
    images_without_labels: tuple[str, ...]
    orphan_labels: tuple[str, ...]
    annotation_completeness: float
    bounding_box_stats: BoundingBoxStats | None


class AnnotationStatisticsCalculator:
    """Compute annotation-derived statistics by composing existing modules.

    Args:
        taxonomy: The canonical device taxonomy (injected) supplying class
            names and the authoritative class list.
        validator: Optional pre-built annotation validator (injected for
            testing); defaults to one bound to ``taxonomy.num_classes``.
    """

    def __init__(
        self,
        taxonomy: DeviceTaxonomy,
        *,
        validator: AnnotationValidator | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._validator = validator or AnnotationValidator(
            num_classes=taxonomy.num_classes
        )

    def _bounding_box_stats(
        self, *, images_root: Path, labels_root: Path
    ) -> BoundingBoxStats | None:
        """Measure bounding-box geometry across all label files.

        Re-reads each label file with the validator's own line parser so box
        widths/heights are available (the aggregate report only carries counts).
        Malformed lines are silently skipped here — the
        :class:`~device_ai.dataset.validator.AnnotationValidator` is the module
        that *reports* them; this pass only measures well-formed geometry.
        """
        widths: list[float] = []
        heights: list[float] = []
        areas: list[float] = []

        for image_path in list_image_paths(images_root):
            label_path = label_path_for(image_path, images_root, labels_root)
            if not label_path.exists():
                continue
            try:
                text = label_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for raw in text.splitlines():
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    box = parse_yolo_line(stripped)
                except ValueError:
                    continue
                widths.append(box.width)
                heights.append(box.height)
                areas.append(box.width * box.height)

        if not widths:
            return None

        return BoundingBoxStats(
            total_boxes=len(widths),
            min_width=round(min(widths), 4),
            max_width=round(max(widths), 4),
            mean_width=round(sum(widths) / len(widths), 4),
            min_height=round(min(heights), 4),
            max_height=round(max(heights), 4),
            mean_height=round(sum(heights) / len(heights), 4),
            min_area=round(min(areas), 4),
            max_area=round(max(areas), 4),
            mean_area=round(sum(areas) / len(areas), 4),
        )

    def _class_distribution(
        self, report: AnnotationReport
    ) -> tuple[tuple[ClassDistributionEntry, ...], tuple[str, ...]]:
        """Build the full-taxonomy class distribution and missing-class list."""
        entries: list[ClassDistributionEntry] = []
        missing: list[str] = []
        for class_id in range(self._taxonomy.num_classes):
            name = self._taxonomy.name_for(class_id)
            count = report.class_counts.get(class_id, 0)
            entries.append(
                ClassDistributionEntry(
                    class_id=class_id,
                    class_name=name,
                    count=count,
                )
            )
            if count == 0:
                missing.append(name)
        return tuple(entries), tuple(missing)

    def compute(self, *, images_root: Path, labels_root: Path) -> AnnotationStatistics:
        """Compute annotation statistics over an image/label directory pair.

        Args:
            images_root: Directory containing the dataset images.
            labels_root: Directory containing the YOLO ``.txt`` labels.

        Returns:
            The populated :class:`AnnotationStatistics`.
        """
        report = self._validator.validate(
            images_root=images_root, labels_root=labels_root
        )

        image_paths = list_image_paths(images_root)
        total_images = len(image_paths)
        total_labelled = total_images - len(report.images_without_labels)
        completeness = round(total_labelled / total_images, 4) if total_images else 0.0

        distribution, missing = self._class_distribution(report)
        bbox_stats = self._bounding_box_stats(
            images_root=images_root, labels_root=labels_root
        )

        return AnnotationStatistics(
            taxonomy_version=self._taxonomy.version,
            num_classes=self._taxonomy.num_classes,
            total_images=total_images,
            total_labelled_images=total_labelled,
            total_boxes=report.total_boxes,
            class_distribution=distribution,
            missing_classes=missing,
            images_without_labels=report.images_without_labels,
            orphan_labels=report.labels_without_images,
            annotation_completeness=completeness,
            bounding_box_stats=bbox_stats,
        )


def _bbox_stats_to_dict(stats: BoundingBoxStats | None) -> dict[str, object] | None:
    """Convert :class:`BoundingBoxStats` to a JSON-serialisable dict."""
    if stats is None:
        return None
    return {
        "total_boxes": stats.total_boxes,
        "width": {
            "min": stats.min_width,
            "max": stats.max_width,
            "mean": stats.mean_width,
        },
        "height": {
            "min": stats.min_height,
            "max": stats.max_height,
            "mean": stats.mean_height,
        },
        "area": {
            "min": stats.min_area,
            "max": stats.max_area,
            "mean": stats.mean_area,
        },
    }


def annotation_statistics_to_dict(
    stats: AnnotationStatistics,
) -> dict[str, object]:
    """Convert :class:`AnnotationStatistics` to a JSON-serialisable dict.

    Args:
        stats: The annotation statistics snapshot.

    Returns:
        A primitive-only mapping.
    """
    return {
        "taxonomy_version": stats.taxonomy_version,
        "num_classes": stats.num_classes,
        "total_images": stats.total_images,
        "total_labelled_images": stats.total_labelled_images,
        "total_boxes": stats.total_boxes,
        "annotation_completeness": stats.annotation_completeness,
        "class_distribution": [
            {
                "class_id": entry.class_id,
                "class_name": entry.class_name,
                "count": entry.count,
            }
            for entry in stats.class_distribution
        ],
        "missing_classes": list(stats.missing_classes),
        "images_without_labels": list(stats.images_without_labels),
        "orphan_labels": list(stats.orphan_labels),
        "bounding_box_stats": _bbox_stats_to_dict(stats.bounding_box_stats),
    }
