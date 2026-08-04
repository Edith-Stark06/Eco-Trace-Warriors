"""Dataset service: orchestration facade for the intelligence pipeline.

:class:`DatasetService` is the single collaborator the API layer depends on.
It wires together the importer, metadata generator, duplicate detector,
annotation validator, splitter, augmenter, exporter, statistics calculator,
versioning and reporting modules, and owns the (only) filesystem side-effects
— writing metadata, splits, quality reports and version manifests into the
managed :class:`~device_ai.dataset.layout.DatasetLayout`.

Timestamps are supplied by an injected clock (defaulting to UTC ``now``) so
tests can pin them for reproducible artifacts. No module reads configuration
globally: everything flows from the :class:`Settings` handed to the factory.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..configs.settings import Settings
from ..exceptions import EmptyDatasetError
from .augmenter import DEFAULT_OPERATIONS, ImageAugmenter
from .duplicates import DuplicateDetector
from .exporter import DatasetExporter
from .importer import DatasetImporter
from .layout import DatasetLayout
from .metadata import MetadataGenerator, build_metadata_document
from .records import (
    AnnotationReport,
    AugmentationResult,
    DatasetStatistics,
    DatasetVersion,
    DuplicateReport,
    ExportResult,
    ImageRecord,
    ImportSummary,
    SplitAssignment,
)
from .reporting import ReportBuilder
from .splitter import DatasetSplitter, split_to_dict
from .statistics import StatisticsCalculator
from .validator import AnnotationValidator
from .versioning import DatasetVersionManager


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class DatasetService:
    """High-level orchestration of the dataset intelligence pipeline.

    Args:
        settings: The active application settings (dependency injection).
        clock: Callable returning the current time; injected for
            reproducible timestamps in tests.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._layout = DatasetLayout.from_settings(settings).ensure()
        self._metadata = MetadataGenerator.from_settings(settings)
        self._duplicates = DuplicateDetector.from_settings(settings)
        self._statistics = StatisticsCalculator()
        self._reporting = ReportBuilder()
        self._importer = DatasetImporter()

    @property
    def layout(self) -> DatasetLayout:
        """The managed dataset directory layout."""
        return self._layout

    def _default_images_root(self) -> Path:
        """Return the preferred source of images for analysis.

        Prefers ``cleaned`` → ``processed`` → ``raw``, falling back to
        ``raw`` so a freshly initialised dataset still resolves.
        """
        for candidate in (self._layout.cleaned, self._layout.processed):
            if candidate.exists() and any(candidate.iterdir()):
                return candidate
        return self._layout.raw

    def analyze(self, images_root: Path | None = None) -> list[ImageRecord]:
        """Analyse every image beneath ``images_root`` into records.

        Args:
            images_root: Directory to analyse; defaults to the preferred
                managed image directory.

        Returns:
            The analysed :class:`ImageRecord` list.
        """
        root = images_root or self._default_images_root()
        return self._metadata.analyze_directory(root)

    def import_images(
        self,
        source_root: Path,
        *,
        deduplicate: bool = True,
    ) -> ImportSummary:
        """Import images from ``source_root`` into the managed ``raw`` dir.

        Args:
            source_root: Directory of source images.
            deduplicate: Whether to skip exact-duplicate bytes.

        Returns:
            The :class:`ImportSummary`.
        """
        return self._importer.import_directory(
            source_root, self._layout.raw, deduplicate=deduplicate
        )

    def detect_duplicates(self, records: list[ImageRecord]) -> DuplicateReport:
        """Detect duplicates among analysed records.

        Args:
            records: Analysed image records.

        Returns:
            The :class:`DuplicateReport`.
        """
        return self._duplicates.detect(records)

    def validate_annotations(
        self,
        *,
        images_root: Path | None = None,
        labels_root: Path | None = None,
        num_classes: int | None = None,
    ) -> AnnotationReport:
        """Validate YOLO annotations against images.

        Args:
            images_root: Image directory; defaults to the managed ``raw`` dir.
            labels_root: Label directory; defaults to the managed ``labels``
                dir.
            num_classes: Optional class count for range checks.

        Returns:
            The :class:`AnnotationReport`.
        """
        validator = AnnotationValidator(num_classes=num_classes)
        return validator.validate(
            images_root=images_root or self._layout.raw,
            labels_root=labels_root or self._layout.labels,
        )

    def generate_metadata(
        self,
        records: list[ImageRecord],
        *,
        source: str,
    ) -> Path:
        """Write a metadata JSON document for ``records``.

        Args:
            records: Analysed image records.
            source: Human-readable source identifier.

        Returns:
            The path of the written metadata document.
        """
        document = build_metadata_document(
            records, source=source, generated_at=self._clock()
        )
        out_path = self._layout.metadata / "metadata.json"
        self._write_json(out_path, document)
        return out_path

    def split(
        self,
        records: list[ImageRecord],
        *,
        ratios: tuple[float, float, float] | None = None,
        seed: int | None = None,
    ) -> SplitAssignment:
        """Split records into train/val/test and persist the manifest.

        Args:
            records: Analysed image records.
            ratios: Optional ratio override.
            seed: Optional seed override.

        Returns:
            The :class:`SplitAssignment`.
        """
        splitter = DatasetSplitter.from_settings(
            self._settings, ratios=ratios, seed=seed
        )
        assignment = splitter.split_records(records)
        self._write_json(self._layout.splits / "split.json", split_to_dict(assignment))
        return assignment

    def augment(
        self,
        *,
        source_root: Path | None = None,
        operations: tuple[str, ...] = DEFAULT_OPERATIONS,
    ) -> AugmentationResult:
        """Generate augmented variants into the managed ``augmented`` dir.

        Args:
            source_root: Source image directory; defaults to ``raw``.
            operations: Augmentation operations to apply.

        Returns:
            The :class:`AugmentationResult`.
        """
        augmenter = ImageAugmenter(operations)
        return augmenter.augment_directory(
            source_root or self._layout.raw, self._layout.augmented
        )

    def export(
        self,
        *,
        export_format: str,
        records: list[ImageRecord],
        images_root: Path | None = None,
        class_names: list[str] | None = None,
    ) -> ExportResult:
        """Export the dataset to a target annotation format.

        Args:
            export_format: ``yolo`` | ``coco`` | ``voc``.
            records: Analysed image records to export.
            images_root: Root the records are based on; defaults to ``raw``.
            class_names: Optional ordered class names.

        Returns:
            The :class:`ExportResult`.
        """
        exporter = DatasetExporter(class_names=class_names)
        destination = self._layout.exports / export_format.lower()
        return exporter.export(
            export_format=export_format,
            records=records,
            images_root=images_root or self._layout.raw,
            labels_root=self._layout.labels,
            destination=destination,
        )

    def statistics(
        self,
        records: list[ImageRecord],
        *,
        duplicates: DuplicateReport | None = None,
    ) -> DatasetStatistics:
        """Compute aggregate statistics for ``records``.

        Args:
            records: Analysed image records.
            duplicates: Optional duplicate report to fold in.

        Returns:
            The :class:`DatasetStatistics`.
        """
        return self._statistics.compute(records, duplicates=duplicates)

    def create_version(
        self, records: list[ImageRecord], *, note: str = ""
    ) -> DatasetVersion:
        """Record an immutable snapshot of ``records``.

        Args:
            records: Analysed image records.
            note: Optional human-readable description.

        Returns:
            The created :class:`DatasetVersion`.
        """
        manager = DatasetVersionManager(self._layout.metadata)
        return manager.create_version(records, created_at=self._clock(), note=note)

    def build_report(
        self,
        *,
        images_root: Path | None = None,
        include_annotations: bool = True,
    ) -> tuple[dict[str, object], Path, Path]:
        """Build and persist the combined dataset report (JSON + HTML).

        Args:
            images_root: Image directory to analyse; defaults to the
                preferred managed directory.
            include_annotations: Whether to fold in annotation validation.

        Returns:
            A ``(document, json_path, html_path)`` tuple.

        Raises:
            EmptyDatasetError: If no images are found to report on.
        """
        root = images_root or self._default_images_root()
        records = self.analyze(root)
        if not records:
            raise EmptyDatasetError(
                "No images found to report on.",
                details={"images_root": root.as_posix()},
            )

        duplicates = self.detect_duplicates(records)
        statistics = self.statistics(records, duplicates=duplicates)
        annotations = (
            self.validate_annotations(images_root=root) if include_annotations else None
        )

        document = self._reporting.build(
            statistics=statistics,
            duplicates=duplicates,
            annotations=annotations,
            generated_at=self._clock(),
            source=root.as_posix(),
        )
        json_path = self._layout.quality / "report.json"
        html_path = self._layout.quality / "report.html"
        self._write_json(json_path, document)
        html_path.write_text(self._reporting.to_html(document), encoding="utf-8")
        return document, json_path, html_path

    @staticmethod
    def _write_json(path: Path, document: dict[str, object]) -> None:
        """Serialise a document to ``path`` as pretty, sorted JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
        )
