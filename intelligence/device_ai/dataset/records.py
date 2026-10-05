"""Shared value objects for the dataset intelligence pipeline.

These immutable dataclasses are the common vocabulary passed between the
dataset modules (importer, metadata, duplicates, splitter, exporter,
statistics, versioning). Keeping them free of I/O and framework imports lets
every stage stay independently testable and trivially serialisable.

All value objects expose :func:`dataclasses.asdict`-friendly, primitive-only
fields so a report or metadata document is a one-line JSON conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    """Thresholds that classify image-quality metrics into flags.

    Injected (from :class:`~device_ai.configs.settings.Settings`) rather than
    read globally, so callers and tests can supply their own limits.

    Attributes:
        blur: Variance-of-Laplacian below which an image is *blurry*.
        dark: Mean luminance below which an image is *too dark*.
        bright: Mean luminance above which an image is *too bright*.
        min_dimension: Minimum width/height (px) before an image is
            considered *low resolution*.
    """

    blur: float
    dark: float
    bright: float
    min_dimension: int


@dataclass(frozen=True, slots=True)
class PerceptualHashes:
    """Content and perceptual fingerprints of a single image.

    Attributes:
        sha256: Cryptographic hash of the raw file bytes (exact duplicates).
        ahash: 64-bit average hash, hex encoded (near-duplicates).
        dhash: 64-bit difference hash, hex encoded (near-duplicates).
        phash: 64-bit perceptual (DCT) hash, hex encoded (near-duplicates).
    """

    sha256: str
    ahash: str
    dhash: str
    phash: str


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Objective image-quality measurements and derived flags.

    Attributes:
        blur_score: Variance of the Laplacian; higher is sharper.
        brightness: Mean luminance in ``[0, 255]``.
        is_blurry: Whether ``blur_score`` is below the blur threshold.
        is_dark: Whether ``brightness`` is below the dark threshold.
        is_bright: Whether ``brightness`` is above the bright threshold.
        is_low_resolution: Whether either side is below the minimum dimension.
        is_corrupted: Whether the image failed to decode.
        issues: Sorted tuple of flagged issue codes (empty when clean).
    """

    blur_score: float
    brightness: float
    is_blurry: bool
    is_dark: bool
    is_bright: bool
    is_low_resolution: bool
    is_corrupted: bool
    issues: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        """Whether the image tripped no quality flags."""
        return not self.issues


@dataclass(frozen=True, slots=True)
class ImageRecord:
    """Full metadata for one dataset image.

    Attributes:
        relative_path: POSIX path relative to the scanned source root; the
            stable identity used across reports and exports.
        filename: Bare file name.
        image_format: Pillow format name (e.g. ``"PNG"``); empty if unknown.
        mode: Pillow colour mode (e.g. ``"RGB"``); empty if unknown.
        width: Decoded width in pixels (0 when corrupted).
        height: Decoded height in pixels (0 when corrupted).
        size_bytes: File size on disk in bytes.
        hashes: Content and perceptual fingerprints.
        quality: Quality metrics and flags.
    """

    relative_path: str
    filename: str
    image_format: str
    mode: str
    width: int
    height: int
    size_bytes: int
    hashes: PerceptualHashes
    quality: QualityMetrics

    @property
    def megapixels(self) -> float:
        """Resolution expressed in megapixels, rounded to three decimals."""
        return round((self.width * self.height) / 1_000_000, 3)


@dataclass(frozen=True, slots=True)
class DuplicatePair:
    """A near-duplicate relationship between two images.

    Attributes:
        source: ``relative_path`` of the retained representative image.
        duplicate: ``relative_path`` of the image judged a duplicate.
        distance: Hamming distance between the two perceptual hashes.
        exact: Whether the two share an identical SHA-256 (byte-for-byte).
    """

    source: str
    duplicate: str
    distance: int
    exact: bool


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    """Result of duplicate detection over a set of images.

    Attributes:
        pairs: Every detected duplicate relationship.
        duplicate_paths: Sorted unique paths judged duplicates (removal set).
        total_images: Number of images scanned.
    """

    pairs: tuple[DuplicatePair, ...]
    duplicate_paths: tuple[str, ...]
    total_images: int

    @property
    def num_duplicates(self) -> int:
        """Count of images flagged as duplicates."""
        return len(self.duplicate_paths)

    @property
    def num_unique(self) -> int:
        """Count of images that remain after duplicate removal."""
        return self.total_images - self.num_duplicates


@dataclass(frozen=True, slots=True)
class AnnotationIssue:
    """A single problem found while validating an annotation file.

    Attributes:
        file: ``relative_path`` of the annotation (or image) at fault.
        line: 1-based line number, or 0 when file-scoped.
        code: Stable machine-readable issue code.
        message: Human-readable description.
    """

    file: str
    line: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AnnotationReport:
    """Aggregate result of validating a set of YOLO annotations.

    Attributes:
        total_labels: Number of label files inspected.
        total_boxes: Number of bounding boxes parsed across all files.
        images_without_labels: Images that have no matching label file.
        labels_without_images: Label files with no matching image.
        class_counts: Mapping of class id → occurrence count.
        issues: Every validation issue found (empty when valid).
    """

    total_labels: int
    total_boxes: int
    images_without_labels: tuple[str, ...]
    labels_without_images: tuple[str, ...]
    class_counts: dict[int, int]
    issues: tuple[AnnotationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the annotation set is free of blocking issues."""
        return not self.issues


@dataclass(frozen=True, slots=True)
class SplitAssignment:
    """The train/val/test partitioning of a dataset.

    Attributes:
        train: ``relative_path`` values assigned to the training split.
        val: ``relative_path`` values assigned to the validation split.
        test: ``relative_path`` values assigned to the test split.
        ratios: The ``(train, val, test)`` ratios used.
        seed: The RNG seed used for the deterministic shuffle.
    """

    train: tuple[str, ...]
    val: tuple[str, ...]
    test: tuple[str, ...]
    ratios: tuple[float, float, float]
    seed: int

    @property
    def counts(self) -> dict[str, int]:
        """Per-split image counts."""
        return {
            "train": len(self.train),
            "val": len(self.val),
            "test": len(self.test),
        }


@dataclass(frozen=True, slots=True)
class ResolutionStats:
    """Summary statistics of image resolutions.

    Attributes:
        min_width: Smallest width observed.
        max_width: Largest width observed.
        min_height: Smallest height observed.
        max_height: Largest height observed.
        mean_width: Mean width, rounded to one decimal.
        mean_height: Mean height, rounded to one decimal.
    """

    min_width: int
    max_width: int
    min_height: int
    max_height: int
    mean_width: float
    mean_height: float


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Aggregate view of quality flags across a dataset.

    Attributes:
        blurry: Number of blurry images.
        dark: Number of too-dark images.
        bright: Number of too-bright images.
        low_resolution: Number of low-resolution images.
        corrupted: Number of undecodable images.
        mean_blur_score: Mean variance-of-Laplacian, rounded to two decimals.
        mean_brightness: Mean luminance, rounded to two decimals.
    """

    blurry: int
    dark: int
    bright: int
    low_resolution: int
    corrupted: int
    mean_blur_score: float
    mean_brightness: float


@dataclass(frozen=True, slots=True)
class DatasetStatistics:
    """A complete statistical snapshot of a dataset.

    Attributes:
        total_images: Number of images analysed.
        total_size_bytes: Combined size of all image files.
        format_counts: Mapping of image format → count.
        mode_counts: Mapping of colour mode → count.
        resolution: Resolution summary statistics.
        quality: Aggregate quality summary.
        duplicate_groups: Number of near-duplicate relationships found.
        duplicate_images: Number of images flagged as duplicates.
    """

    total_images: int
    total_size_bytes: int
    format_counts: dict[str, int]
    mode_counts: dict[str, int]
    resolution: ResolutionStats | None
    quality: QualitySummary
    duplicate_groups: int
    duplicate_images: int

    @property
    def total_size_mb(self) -> float:
        """Combined dataset size in megabytes, rounded to three decimals."""
        return round(self.total_size_bytes / (1024 * 1024), 3)


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """Result of importing images into the managed dataset tree.

    Attributes:
        imported: ``relative_path`` values written into the destination.
        skipped_duplicates: Source paths skipped as exact duplicates.
        skipped_invalid: Source paths skipped as unreadable/unsupported.
        destination: POSIX path of the destination directory.
    """

    imported: tuple[str, ...]
    skipped_duplicates: tuple[str, ...]
    skipped_invalid: tuple[str, ...]
    destination: str

    @property
    def num_imported(self) -> int:
        """Count of successfully imported images."""
        return len(self.imported)


@dataclass(frozen=True, slots=True)
class AugmentationResult:
    """Result of generating augmented image variants.

    Attributes:
        generated: ``relative_path`` values of the created variants.
        source_count: Number of source images processed.
        operations: Names of the augmentation operations applied.
        destination: POSIX path of the destination directory.
    """

    generated: tuple[str, ...]
    source_count: int
    operations: tuple[str, ...]
    destination: str

    @property
    def num_generated(self) -> int:
        """Count of generated augmented images."""
        return len(self.generated)


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Result of exporting a dataset to a target annotation format.

    Attributes:
        export_format: The format written (``yolo`` | ``coco`` | ``voc``).
        destination: POSIX path of the export directory.
        files: ``relative_path`` values of every file written.
        image_count: Number of images referenced by the export.
    """

    export_format: str
    destination: str
    files: tuple[str, ...]
    image_count: int

    @property
    def file_count(self) -> int:
        """Number of files written by the export."""
        return len(self.files)


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    """An immutable, content-addressed snapshot of a dataset.

    Attributes:
        version: Monotonic version label (e.g. ``"v1"``).
        created_at: ISO-8601 UTC timestamp of creation.
        image_count: Number of images captured in the snapshot.
        content_hash: Aggregate SHA-256 over the sorted per-image hashes.
        note: Optional human-supplied description.
        manifest: Sorted ``relative_path`` → ``sha256`` mapping.
    """

    version: str
    created_at: str
    image_count: int
    content_hash: str
    note: str = ""
    manifest: dict[str, str] = field(default_factory=dict)
