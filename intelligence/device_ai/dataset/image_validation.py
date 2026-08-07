"""Image-structural validation (Sprint P4.1.2, PART 2).

Complements the annotation-focused
:class:`~device_ai.dataset.validator.AnnotationValidator` with checks on the
*images themselves*: unsupported file extensions, corrupt/unreadable files,
out-of-range resolution, invalid aspect ratio, oversized files, duplicate
filenames, and duplicate content hashes.

The validator is pure composition: it reuses
:class:`~device_ai.dataset.metadata.MetadataGenerator` for decoding and quality
metrics and :class:`~device_ai.dataset.duplicates.DuplicateDetector` for exact
duplicate detection. It never mutates files and returns a structured,
JSON-serialisable :class:`ImageValidationReport`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..configs.settings import ALLOWED_IMAGE_EXTENSIONS
from .duplicates import DuplicateDetector
from .layout import relative_path
from .metadata import MetadataGenerator
from .records import ImageRecord

if TYPE_CHECKING:
    from ..configs.settings import Settings

# Aspect-ratio bounds (width / height). No settings field exists for these, so
# they default here and are injectable, keeping ``settings.py`` untouched.
# 0.25–4.0 admits portrait and landscape device photos while rejecting extreme
# slivers that usually signal a cropping or export error.
_DEFAULT_MIN_ASPECT_RATIO = 0.25
_DEFAULT_MAX_ASPECT_RATIO = 4.0


@dataclass(frozen=True, slots=True)
class ImageValidationIssue:
    """A single problem found while validating a dataset image.

    Attributes:
        file: ``relative_path`` of the offending file (relative to the scanned
            images root).
        code: Stable machine-readable issue code.
        message: Human-readable description.
    """

    file: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ImageValidationReport:
    """Aggregate result of validating a directory of dataset images.

    Attributes:
        total_files_scanned: Every file encountered under the images root,
            regardless of extension.
        total_images: Supported images that were decoded and inspected.
        unsupported_extensions: Files whose extension is not in
            :data:`ALLOWED_IMAGE_EXTENSIONS`.
        corrupted: Images that failed to decode.
        undersized: Images below the minimum dimension.
        oversized_resolution: Images above the maximum dimension.
        invalid_aspect_ratio: Images whose width/height ratio is out of bounds.
        oversized_files: Images whose byte size exceeds the configured maximum.
        duplicate_filenames: Bare filenames appearing at more than one path.
        duplicate_hashes: ``relative_path`` values sharing content with an
            earlier image (exact SHA-256 match).
        issues: Every validation issue found (empty when valid).
    """

    total_files_scanned: int
    total_images: int
    unsupported_extensions: tuple[str, ...]
    corrupted: tuple[str, ...]
    undersized: tuple[str, ...]
    oversized_resolution: tuple[str, ...]
    invalid_aspect_ratio: tuple[str, ...]
    oversized_files: tuple[str, ...]
    duplicate_filenames: tuple[str, ...]
    duplicate_hashes: tuple[str, ...]
    issues: tuple[ImageValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the image set is free of blocking issues."""
        return not self.issues


class ImageValidator:
    """Validate the structural integrity of a directory of dataset images.

    Composes existing pipeline components rather than re-implementing decoding
    or hashing:

    * :class:`~device_ai.dataset.metadata.MetadataGenerator` decodes each image
      and computes resolution + corruption flags.
    * :class:`~device_ai.dataset.duplicates.DuplicateDetector` surfaces exact
      content duplicates.

    Args:
        settings: Application settings (injected) supplying resolution and file
            size limits.
        min_aspect_ratio: Minimum acceptable width/height ratio.
        max_aspect_ratio: Maximum acceptable width/height ratio.
        metadata_generator: Optional pre-built generator (injected for testing);
            defaults to one built from ``settings``.
        duplicate_detector: Optional pre-built detector (injected for testing);
            defaults to one built from ``settings``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        min_aspect_ratio: float = _DEFAULT_MIN_ASPECT_RATIO,
        max_aspect_ratio: float = _DEFAULT_MAX_ASPECT_RATIO,
        metadata_generator: MetadataGenerator | None = None,
        duplicate_detector: DuplicateDetector | None = None,
    ) -> None:
        self._settings = settings
        self._min_aspect_ratio = min_aspect_ratio
        self._max_aspect_ratio = max_aspect_ratio
        self._metadata = metadata_generator or MetadataGenerator.from_settings(settings)
        self._duplicates = duplicate_detector or DuplicateDetector.from_settings(
            settings
        )

    def _scan_unsupported_extensions(self, images_root: Path) -> list[str]:
        """Return files under ``images_root`` with a non-image extension."""
        unsupported: list[str] = []
        if not images_root.exists():
            return unsupported
        for path in sorted(images_root.rglob("*")):
            if path.is_file() and path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
                unsupported.append(relative_path(path, images_root))
        return unsupported

    def _check_record(
        self, record: ImageRecord
    ) -> tuple[list[ImageValidationIssue], dict[str, bool]]:
        """Validate one image record; return issues and per-check flags."""
        issues: list[ImageValidationIssue] = []
        flags = {
            "corrupted": False,
            "undersized": False,
            "oversized_resolution": False,
            "invalid_aspect_ratio": False,
            "oversized_file": False,
        }
        rel = record.relative_path

        if record.quality.is_corrupted:
            flags["corrupted"] = True
            issues.append(
                ImageValidationIssue(
                    file=rel,
                    code="CORRUPTED_IMAGE",
                    message="image could not be decoded",
                )
            )
            # A corrupt image has no meaningful dimensions; skip metric checks.
            return issues, flags

        min_dim = self._settings.min_image_dimension
        max_dim = self._settings.max_image_dimension
        smallest = min(record.width, record.height)
        largest = max(record.width, record.height)

        if smallest < min_dim:
            flags["undersized"] = True
            issues.append(
                ImageValidationIssue(
                    file=rel,
                    code="RESOLUTION_TOO_SMALL",
                    message=(
                        f"{record.width}x{record.height} below minimum "
                        f"dimension {min_dim}px"
                    ),
                )
            )
        if largest > max_dim:
            flags["oversized_resolution"] = True
            issues.append(
                ImageValidationIssue(
                    file=rel,
                    code="RESOLUTION_TOO_LARGE",
                    message=(
                        f"{record.width}x{record.height} above maximum "
                        f"dimension {max_dim}px"
                    ),
                )
            )

        if record.height > 0:
            aspect = record.width / record.height
            if not self._min_aspect_ratio <= aspect <= self._max_aspect_ratio:
                flags["invalid_aspect_ratio"] = True
                issues.append(
                    ImageValidationIssue(
                        file=rel,
                        code="INVALID_ASPECT_RATIO",
                        message=(
                            f"aspect ratio {aspect:.3f} outside "
                            f"[{self._min_aspect_ratio}, {self._max_aspect_ratio}]"
                        ),
                    )
                )

        if record.size_bytes > self._settings.max_file_size:
            flags["oversized_file"] = True
            issues.append(
                ImageValidationIssue(
                    file=rel,
                    code="FILE_TOO_LARGE",
                    message=(
                        f"{record.size_bytes} bytes exceeds maximum "
                        f"{self._settings.max_file_size} bytes"
                    ),
                )
            )

        return issues, flags

    def _check_duplicate_filenames(
        self, records: list[ImageRecord]
    ) -> tuple[list[str], list[ImageValidationIssue]]:
        """Flag bare filenames that appear at more than one relative path."""
        by_name: dict[str, list[str]] = {}
        for record in records:
            by_name.setdefault(record.filename, []).append(record.relative_path)

        duplicate_names: list[str] = []
        issues: list[ImageValidationIssue] = []
        for name, paths in sorted(by_name.items()):
            if len(paths) > 1:
                duplicate_names.append(name)
                for path in sorted(paths):
                    issues.append(
                        ImageValidationIssue(
                            file=path,
                            code="DUPLICATE_FILENAME",
                            message=(f"filename '{name}' occurs at {len(paths)} paths"),
                        )
                    )
        return duplicate_names, issues

    def _check_duplicate_hashes(
        self, records: list[ImageRecord]
    ) -> tuple[list[str], list[ImageValidationIssue]]:
        """Flag images that share content (exact SHA-256) with an earlier one."""
        report = self._duplicates.detect(records)
        duplicate_hashes: list[str] = []
        issues: list[ImageValidationIssue] = []
        for pair in report.pairs:
            if not pair.exact:
                continue
            duplicate_hashes.append(pair.duplicate)
            issues.append(
                ImageValidationIssue(
                    file=pair.duplicate,
                    code="DUPLICATE_HASH",
                    message=(
                        f"identical content to '{pair.source}' (exact SHA-256 match)"
                    ),
                )
            )
        return sorted(set(duplicate_hashes)), issues

    def validate(self, *, images_root: Path) -> ImageValidationReport:
        """Validate every image under ``images_root``.

        Args:
            images_root: Directory containing the dataset images (scanned
                recursively).

        Returns:
            An aggregate :class:`ImageValidationReport`.
        """
        unsupported = self._scan_unsupported_extensions(images_root)
        total_files = (
            sum(1 for path in images_root.rglob("*") if path.is_file())
            if images_root.exists()
            else 0
        )

        records = self._metadata.analyze_directory(images_root)

        issues: list[ImageValidationIssue] = []
        corrupted: list[str] = []
        undersized: list[str] = []
        oversized_resolution: list[str] = []
        invalid_aspect_ratio: list[str] = []
        oversized_files: list[str] = []

        for record in records:
            record_issues, flags = self._check_record(record)
            issues.extend(record_issues)
            if flags["corrupted"]:
                corrupted.append(record.relative_path)
            if flags["undersized"]:
                undersized.append(record.relative_path)
            if flags["oversized_resolution"]:
                oversized_resolution.append(record.relative_path)
            if flags["invalid_aspect_ratio"]:
                invalid_aspect_ratio.append(record.relative_path)
            if flags["oversized_file"]:
                oversized_files.append(record.relative_path)

        duplicate_filenames, filename_issues = self._check_duplicate_filenames(records)
        duplicate_hashes, hash_issues = self._check_duplicate_hashes(records)

        for rel in unsupported:
            issues.append(
                ImageValidationIssue(
                    file=rel,
                    code="UNSUPPORTED_EXTENSION",
                    message="file extension is not a supported image type",
                )
            )
        issues.extend(filename_issues)
        issues.extend(hash_issues)

        return ImageValidationReport(
            total_files_scanned=total_files,
            total_images=len(records),
            unsupported_extensions=tuple(sorted(unsupported)),
            corrupted=tuple(sorted(corrupted)),
            undersized=tuple(sorted(undersized)),
            oversized_resolution=tuple(sorted(oversized_resolution)),
            invalid_aspect_ratio=tuple(sorted(invalid_aspect_ratio)),
            oversized_files=tuple(sorted(oversized_files)),
            duplicate_filenames=tuple(duplicate_filenames),
            duplicate_hashes=tuple(duplicate_hashes),
            issues=tuple(issues),
        )


def image_validation_to_dict(report: ImageValidationReport) -> dict[str, object]:
    """Convert an :class:`ImageValidationReport` to a JSON-serialisable dict.

    Args:
        report: The image-validation report.

    Returns:
        A primitive-only mapping.
    """
    return {
        "total_files_scanned": report.total_files_scanned,
        "total_images": report.total_images,
        "is_valid": report.is_valid,
        "summary": {
            "unsupported_extensions": len(report.unsupported_extensions),
            "corrupted": len(report.corrupted),
            "undersized": len(report.undersized),
            "oversized_resolution": len(report.oversized_resolution),
            "invalid_aspect_ratio": len(report.invalid_aspect_ratio),
            "oversized_files": len(report.oversized_files),
            "duplicate_filenames": len(report.duplicate_filenames),
            "duplicate_hashes": len(report.duplicate_hashes),
            "total_issues": len(report.issues),
        },
        "unsupported_extensions": list(report.unsupported_extensions),
        "corrupted": list(report.corrupted),
        "undersized": list(report.undersized),
        "oversized_resolution": list(report.oversized_resolution),
        "invalid_aspect_ratio": list(report.invalid_aspect_ratio),
        "oversized_files": list(report.oversized_files),
        "duplicate_filenames": list(report.duplicate_filenames),
        "duplicate_hashes": list(report.duplicate_hashes),
        "issues": [
            {"file": issue.file, "code": issue.code, "message": issue.message}
            for issue in report.issues
        ],
    }
