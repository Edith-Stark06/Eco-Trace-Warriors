"""Dataset intelligence API routes (milestone M1.2).

Six endpoints make up the ``/dataset`` surface:

* ``POST /dataset/import``   — ingest & de-duplicate source images.
* ``POST /dataset/validate`` — validate YOLO annotations against images.
* ``POST /dataset/augment``  — generate augmented image variants.
* ``POST /dataset/export``   — export to YOLO/COCO/Pascal VOC.
* ``GET  /dataset/stats``    — aggregate dataset statistics.
* ``GET  /dataset/report``   — combined JSON/HTML dataset report.

Routes are thin: they parse/validate input, delegate to the injected
:class:`~device_ai.dataset.service.DatasetService`, and serialise the result.
No business logic lives here, and the existing prediction endpoints are left
untouched (this router is mounted under a separate prefix).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger

from ..dataset.augmenter import DEFAULT_OPERATIONS
from ..dataset.service import DatasetService
from ..dataset.statistics import statistics_to_dict
from ..exceptions import DatasetNotFoundError
from .dataset_schemas import (
    AnnotationIssuePayload,
    AugmentRequest,
    AugmentResponse,
    ExportRequest,
    ExportResponse,
    ImportRequest,
    ImportResponse,
    ReportResponse,
    StatsResponse,
    ValidateRequest,
    ValidateResponse,
)
from .dependencies import get_dataset_service

router = APIRouter(prefix="/dataset", tags=["dataset"])


def _require_directory(path: Path, *, what: str) -> None:
    """Raise :class:`DatasetNotFoundError` if ``path`` is not a directory."""
    if not path.is_dir():
        raise DatasetNotFoundError(
            f"{what} directory not found.",
            details={"path": path.as_posix()},
        )


@router.post("/import", response_model=ImportResponse)
def import_dataset(
    payload: ImportRequest,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> ImportResponse:
    """Import and de-duplicate images from a server-side source directory.

    Args:
        payload: The import request (source directory + dedup flag).
        service: Injected dataset service.

    Returns:
        An :class:`ImportResponse` summarising the outcome.

    Raises:
        DatasetNotFoundError: If the source directory does not exist.
    """
    source = Path(payload.source)
    _require_directory(source, what="Source")
    summary = service.import_images(source, deduplicate=payload.deduplicate)
    logger.bind(num_imported=summary.num_imported).info("Dataset import complete")
    return ImportResponse(
        imported=list(summary.imported),
        skipped_duplicates=list(summary.skipped_duplicates),
        skipped_invalid=list(summary.skipped_invalid),
        destination=summary.destination,
        num_imported=summary.num_imported,
    )


@router.post("/validate", response_model=ValidateResponse)
def validate_dataset(
    payload: ValidateRequest,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> ValidateResponse:
    """Validate the dataset's YOLO annotations against its images.

    Args:
        payload: The validation request (optional class count).
        service: Injected dataset service.

    Returns:
        A :class:`ValidateResponse` with the annotation report.
    """
    report = service.validate_annotations(num_classes=payload.num_classes)
    logger.bind(is_valid=report.is_valid, issues=len(report.issues)).info(
        "Annotation validation complete"
    )
    return ValidateResponse(
        is_valid=report.is_valid,
        total_labels=report.total_labels,
        total_boxes=report.total_boxes,
        class_counts=report.class_counts,
        images_without_labels=list(report.images_without_labels),
        labels_without_images=list(report.labels_without_images),
        issues=[
            AnnotationIssuePayload(
                file=issue.file,
                line=issue.line,
                code=issue.code,
                message=issue.message,
            )
            for issue in report.issues
        ],
    )


@router.post("/augment", response_model=AugmentResponse)
def augment_dataset(
    payload: AugmentRequest,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> AugmentResponse:
    """Generate augmented image variants from the dataset's raw images.

    Args:
        payload: The augmentation request (optional operation list).
        service: Injected dataset service.

    Returns:
        An :class:`AugmentResponse` summarising generated variants.
    """
    operations = tuple(payload.operations) if payload.operations else DEFAULT_OPERATIONS
    result = service.augment(operations=operations)
    logger.bind(num_generated=result.num_generated).info("Augmentation complete")
    return AugmentResponse(
        generated=list(result.generated),
        source_count=result.source_count,
        operations=list(result.operations),
        destination=result.destination,
        num_generated=result.num_generated,
    )


@router.post("/export", response_model=ExportResponse)
def export_dataset(
    payload: ExportRequest,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> ExportResponse:
    """Export the dataset to a target annotation format.

    Args:
        payload: The export request (format + optional class names).
        service: Injected dataset service.

    Returns:
        An :class:`ExportResponse` describing the files written.
    """
    records = service.analyze()
    result = service.export(
        export_format=payload.format,
        records=records,
        class_names=payload.class_names,
    )
    logger.bind(format=result.export_format, files=result.file_count).info(
        "Dataset export complete"
    )
    return ExportResponse(
        format=result.export_format,
        destination=result.destination,
        files=list(result.files),
        file_count=result.file_count,
        image_count=result.image_count,
    )


@router.get("/stats", response_model=StatsResponse)
def dataset_stats(
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> StatsResponse:
    """Return aggregate statistics for the managed dataset.

    Args:
        service: Injected dataset service.

    Returns:
        A :class:`StatsResponse` snapshot.
    """
    records = service.analyze()
    duplicates = service.detect_duplicates(records)
    stats = service.statistics(records, duplicates=duplicates)
    return StatsResponse.model_validate(statistics_to_dict(stats))


@router.get("/report", response_model=ReportResponse)
def dataset_report(
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> ReportResponse:
    """Build and return the combined dataset report (JSON + HTML on disk).

    Args:
        service: Injected dataset service.

    Returns:
        A :class:`ReportResponse` with the document and artifact paths.

    Raises:
        EmptyDatasetError: If the dataset has no images to report on.
    """
    document, json_path, html_path = service.build_report()
    logger.info("Dataset report generated")
    return ReportResponse(
        report=document,
        json_path=json_path.as_posix(),
        html_path=html_path.as_posix(),
    )
