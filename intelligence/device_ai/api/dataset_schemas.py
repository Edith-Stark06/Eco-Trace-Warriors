"""Pydantic v2 schemas for the dataset intelligence endpoints.

These models define the public contract of the ``/dataset`` surface
(milestone M1.2). They convert the dataset value objects into serialisable
payloads and validate request bodies at the transport boundary, keeping the
domain layer free of HTTP concerns.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class ImportRequest(BaseModel):
    """Request body for ``POST /dataset/import``."""

    source: str = Field(
        description="Server-side directory of source images to import.",
    )
    deduplicate: bool = Field(
        default=True,
        description="Skip images whose exact bytes were already imported.",
    )


class ValidateRequest(BaseModel):
    """Request body for ``POST /dataset/validate``."""

    num_classes: int | None = Field(
        default=None,
        ge=1,
        description="Optional class count; enables class-id range checks.",
    )


class AugmentRequest(BaseModel):
    """Request body for ``POST /dataset/augment``."""

    operations: list[str] | None = Field(
        default=None,
        description="Augmentation operations to apply; defaults to the "
        "label-preserving set.",
    )


class ExportRequest(BaseModel):
    """Request body for ``POST /dataset/export``."""

    format: Literal["yolo", "coco", "voc"] = Field(
        description="Target annotation format.",
    )
    class_names: list[str] | None = Field(
        default=None,
        description="Optional ordered class names for the export.",
    )


# ---------------------------------------------------------------------------
# Response fragments
# ---------------------------------------------------------------------------


class ImportResponse(BaseModel):
    """Response body for ``POST /dataset/import``."""

    imported: list[str] = Field(description="Relative paths of imported images.")
    skipped_duplicates: list[str] = Field(
        description="Source paths skipped as exact duplicates."
    )
    skipped_invalid: list[str] = Field(
        description="Source paths skipped as unreadable/unsupported."
    )
    destination: str = Field(description="Destination directory (POSIX path).")
    num_imported: int = Field(description="Count of imported images.")


class AnnotationIssuePayload(BaseModel):
    """A single annotation validation issue."""

    file: str = Field(description="Offending annotation/image path.")
    line: int = Field(description="1-based line, or 0 when file-scoped.")
    code: str = Field(description="Stable machine-readable issue code.")
    message: str = Field(description="Human-readable description.")


class ValidateResponse(BaseModel):
    """Response body for ``POST /dataset/validate``."""

    is_valid: bool = Field(description="Whether the annotation set is valid.")
    total_labels: int = Field(description="Number of label files inspected.")
    total_boxes: int = Field(description="Number of bounding boxes parsed.")
    class_counts: dict[int, int] = Field(description="Class id → occurrences.")
    images_without_labels: list[str] = Field(description="Images missing labels.")
    labels_without_images: list[str] = Field(description="Orphan label files.")
    issues: list[AnnotationIssuePayload] = Field(description="Validation issues.")


class AugmentResponse(BaseModel):
    """Response body for ``POST /dataset/augment``."""

    generated: list[str] = Field(description="Relative paths of generated images.")
    source_count: int = Field(description="Number of source images processed.")
    operations: list[str] = Field(description="Operations applied.")
    destination: str = Field(description="Destination directory (POSIX path).")
    num_generated: int = Field(description="Count of generated images.")


class ExportResponse(BaseModel):
    """Response body for ``POST /dataset/export``."""

    format: str = Field(description="Format written.")
    destination: str = Field(description="Export directory (POSIX path).")
    files: list[str] = Field(description="Relative paths of files written.")
    file_count: int = Field(description="Number of files written.")
    image_count: int = Field(description="Number of images referenced.")


class ResolutionPayload(BaseModel):
    """Resolution summary statistics."""

    min_width: int
    max_width: int
    min_height: int
    max_height: int
    mean_width: float
    mean_height: float


class QualityPayload(BaseModel):
    """Aggregate quality summary."""

    blurry: int
    dark: int
    bright: int
    low_resolution: int
    corrupted: int
    mean_blur_score: float
    mean_brightness: float


class DuplicateSummaryPayload(BaseModel):
    """Duplicate totals folded into statistics."""

    groups: int = Field(description="Number of duplicate relationships.")
    images: int = Field(description="Number of images flagged as duplicates.")


class StatsResponse(BaseModel):
    """Response body for ``GET /dataset/stats``."""

    total_images: int = Field(description="Number of images analysed.")
    total_size_bytes: int = Field(description="Combined size of all images.")
    total_size_mb: float = Field(description="Combined size in megabytes.")
    format_counts: dict[str, int] = Field(description="Image format → count.")
    mode_counts: dict[str, int] = Field(description="Colour mode → count.")
    resolution: ResolutionPayload | None = Field(
        default=None, description="Resolution summary (null when empty)."
    )
    quality: QualityPayload = Field(description="Aggregate quality summary.")
    duplicates: DuplicateSummaryPayload = Field(description="Duplicate totals.")


class ReportResponse(BaseModel):
    """Response body for ``GET /dataset/report``.

    The full combined document is returned as-is under ``report`` alongside
    the on-disk artifact locations.
    """

    report: dict[str, object] = Field(description="Combined report document.")
    json_path: str = Field(description="Path of the written JSON report.")
    html_path: str = Field(description="Path of the written HTML report.")
