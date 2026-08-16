"""Local ingestion — stage verified router boxes with full provenance.

This is the single code path every source funnels through: a remote adapter
downloads to local disk, then ingestion runs identically for local and remote
origins (spec §5).

Per source image:

1. **Bbox presence** — an image with no boxes is rejected (``NO_BBOX``).
   Classification-only data never becomes detection data.
2. **Per-box semantic gate** — every box's *source* label is evaluated by
   :func:`device_ai.acquisition.semantics.evaluate_source_label`. Only boxes
   whose label explicitly denotes ``router`` survive; the rest are dropped with
   their exact rejection category. An image left with no surviving box is
   rejected (``SEMANTIC_REJECTED``).
3. **Image readability** — the file must exist and decode (``IMAGE_UNREADABLE``).
4. **Geometry validation** — each surviving box must parse as a YOLO line via the
   frozen :func:`device_ai.dataset.validator.parse_yolo_line`, carry coordinates
   in ``[0, 1]``, have strictly positive width/height, and lie fully inside the
   image. Invalid boxes are dropped; an image left with none is rejected
   (``INVALID_GEOMETRY``).
5. **Staging + provenance** — the image bytes are copied verbatim into the
   git-ignored staging tree, a YOLO label is written at the **taxonomy id
   resolved at runtime** (never a hardcoded 11), and a full
   :class:`~device_ai.acquisition.provenance_model.AcquisitionProvenanceRecord`
   is captured (SHA-256, original filename, source dataset/identifier/class,
   taxonomy class + id, license evidence, import timestamp).

Nothing here writes outside ``config.staging_root``. Image bytes are copied, never
re-encoded, so the staged SHA-256 equals the source SHA-256 and provenance stays
verifiable.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .formats import DetectedFormat, SourceAnnotation, SourceBox
from .licenses import LicenseDecision
from .provenance_model import AcquisitionProvenanceRecord, compute_sha256, is_complete
from .semantics import evaluate_source_label

# Rejection codes (stable, machine-readable).
REJECT_NO_BBOX = "NO_BBOX"
REJECT_SEMANTIC = "SEMANTIC_REJECTED"
REJECT_IMAGE_UNREADABLE = "IMAGE_UNREADABLE"
REJECT_INVALID_GEOMETRY = "INVALID_GEOMETRY"
REJECT_NAME_COLLISION = "NAME_COLLISION"

#: Coordinate tolerance for containment checks (guards float round-tripping in
#: sources that store absolute pixels and normalise to exactly 1.0).
_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class Rejection:
    """One rejected source image, with the exact reason.

    Attributes:
        source_identifier: The image's identifier within the source.
        code: One of the ``REJECT_*`` codes.
        reason: Exact, human-readable explanation.
        detail: Optional structured evidence (e.g. per-label decisions).
    """

    source_identifier: str
    code: str
    reason: str
    detail: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "source_identifier": self.source_identifier,
            "code": self.code,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class StagedImage:
    """One image staged into the batch tree.

    Attributes:
        relative_path: POSIX path relative to the staged images root.
        label_relative_path: POSIX path relative to the staged labels root.
        box_count: Number of router boxes written for this image.
        source_identifier: Identifier within the source dataset.
        source_labels: Distinct source labels that survived the semantic gate.
    """

    relative_path: str
    label_relative_path: str
    box_count: int
    source_identifier: str
    source_labels: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "relative_path": self.relative_path,
            "label_relative_path": self.label_relative_path,
            "box_count": self.box_count,
            "source_identifier": self.source_identifier,
            "source_labels": list(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """Aggregate result of ingesting one verified source.

    Attributes:
        staged: Every staged image.
        provenance: One provenance record per staged image.
        rejections: Every rejected source image with its exact reason.
        images_discovered: Source images seen (whether staged or not).
        boxes_discovered: Source boxes seen across those images.
        boxes_semantically_rejected: Boxes dropped by the per-box semantic gate.
        boxes_geometry_rejected: Boxes dropped by geometry validation.
        boxes_staged: Boxes written into the staged labels.
        source_format: Detected source annotation format the boxes came from.
        dry_run: Whether the outcome was computed without writing anything.
    """

    staged: list[StagedImage] = field(default_factory=list)
    provenance: list[AcquisitionProvenanceRecord] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    images_discovered: int = 0
    boxes_discovered: int = 0
    boxes_semantically_rejected: int = 0
    boxes_geometry_rejected: int = 0
    boxes_staged: int = 0
    source_format: str = ""
    dry_run: bool = False

    @property
    def images_retained(self) -> int:
        """Number of images staged."""
        return len(self.staged)

    @property
    def images_rejected(self) -> int:
        """Number of source images rejected."""
        return len(self.rejections)

    @property
    def provenance_complete(self) -> int:
        """Number of provenance records with every mandatory field populated."""
        return sum(1 for record in self.provenance if is_complete(record))

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        rejection_counts: dict[str, int] = {}
        for rejection in self.rejections:
            rejection_counts[rejection.code] = rejection_counts.get(rejection.code, 0) + 1
        return {
            "dry_run": self.dry_run,
            "source_format": self.source_format,
            "images_discovered": self.images_discovered,
            "images_retained": self.images_retained,
            "images_rejected": self.images_rejected,
            "boxes_discovered": self.boxes_discovered,
            "boxes_semantically_rejected": self.boxes_semantically_rejected,
            "boxes_geometry_rejected": self.boxes_geometry_rejected,
            "boxes_staged": self.boxes_staged,
            "provenance_records": len(self.provenance),
            "provenance_complete": self.provenance_complete,
            "provenance_incomplete": len(self.provenance) - self.provenance_complete,
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "rejections": [r.to_dict() for r in self.rejections],
            "staged": [s.to_dict() for s in self.staged],
        }


def validate_box_geometry(box: SourceBox) -> str:
    """Return an empty string when a box is valid, else the exact failure.

    The structural contract (five numeric fields, coordinates in ``[0, 1]``,
    positive size) is asserted through the **frozen** YOLO parser so this check
    can never diverge from the frozen validator. Containment inside the image is
    an additional acquisition-time check: a box extending past an edge is a
    source defect, not something to clip silently.

    Args:
        box: One parsed source box (already normalised).

    Returns:
        ``""`` when valid, otherwise the exact reason it was rejected.
    """
    from ..dataset.validator import parse_yolo_line

    line = f"0 {box.x_center} {box.y_center} {box.width} {box.height}"
    try:
        parsed = parse_yolo_line(line)
    except ValueError as exc:
        return f"box does not parse as a YOLO line: {exc}"

    for name, value in (
        ("x_center", parsed.x_center),
        ("y_center", parsed.y_center),
        ("width", parsed.width),
        ("height", parsed.height),
    ):
        if not 0.0 <= value <= 1.0:
            return f"{name}={value} outside [0, 1]"
    if parsed.width <= 0.0 or parsed.height <= 0.0:
        return "box width/height must be strictly positive"

    left = parsed.x_center - parsed.width / 2
    right = parsed.x_center + parsed.width / 2
    top = parsed.y_center - parsed.height / 2
    bottom = parsed.y_center + parsed.height / 2
    if left < -_EPSILON or top < -_EPSILON or right > 1 + _EPSILON or bottom > 1 + _EPSILON:
        return (
            "box extends outside the image bounds "
            f"(x:[{left:.6f}, {right:.6f}], y:[{top:.6f}, {bottom:.6f}])"
        )
    return ""


def _image_opens(path: Path) -> str:
    """Return ``""`` when an image decodes, else the exact failure reason."""
    if not path.is_file():
        return f"image file not found: {path.as_posix()}"
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a project dependency
        return "Pillow unavailable; cannot verify the image opens"
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:  # noqa: BLE001 - any decode failure is a rejection
        return f"image failed to decode ({type(exc).__name__}: {exc})"
    return ""


def _staged_name(source_identifier: str, index: int, suffix: str) -> str:
    """Return a flat, collision-free staged filename.

    The staged tree is intentionally flat (``images/<name>`` +
    ``labels/<name>.txt``) so the frozen validator's mirrored-path pairing is
    unambiguous. The index prefix keeps ordering deterministic and prevents two
    source sub-directories with same-named files from colliding.
    """
    stem = Path(source_identifier).stem or "image"
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in stem)
    return f"router_{index:05d}_{safe}{suffix.lower()}"


def _gate_boxes(
    annotation: SourceAnnotation,
) -> tuple[list[SourceBox], list[dict[str, object]], int]:
    """Apply the per-box semantic gate.

    Returns:
        ``(surviving_boxes, rejected_decisions, rejected_count)``.
    """
    surviving: list[SourceBox] = []
    rejected: list[dict[str, object]] = []
    for box in annotation.boxes:
        decision = evaluate_source_label(box.source_class_name)
        if decision.accepted:
            surviving.append(box)
        else:
            rejected.append(decision.to_dict())
    return surviving, rejected, len(rejected)


def ingest_source(
    annotations: list[SourceAnnotation],
    *,
    detected: DetectedFormat,
    images_root: Path,
    labels_root: Path,
    source_dataset: str,
    source_url: str,
    publisher: str,
    license_decision: LicenseDecision,
    taxonomy_class: str,
    taxonomy_id: int,
    import_timestamp: str,
    dry_run: bool = False,
) -> IngestOutcome:
    """Stage every image whose boxes explicitly denote the target class.

    Args:
        annotations: Parsed source annotations (already normalised to YOLO).
        detected: The detected source format (recorded on provenance detail).
        images_root: Destination directory for staged images.
        labels_root: Destination directory for staged YOLO labels.
        source_dataset: Human-readable source dataset name.
        source_url: Source URL, if known (recorded verbatim).
        publisher: Source publisher/contributor, if known.
        license_decision: The **accepted** license decision for this source. Its
            normalised id is recorded on every provenance record.
        taxonomy_class: Canonical EcoTrace class name.
        taxonomy_id: Taxonomy id resolved at runtime from ``load_taxonomy``.
        import_timestamp: ISO-8601 UTC timestamp for the batch.
        dry_run: When ``True`` nothing is written; counts and rejections are
            still computed so a dry run reports the real shape of the work.

    Returns:
        An :class:`IngestOutcome`.

    Raises:
        ValueError: If ``license_decision`` was not accepted — staging data under
            an unverified license is never permitted.
    """
    if not license_decision.accepted:
        raise ValueError(
            "refusing to ingest under a non-accepted license "
            f"({license_decision.verdict}: {license_decision.reason})"
        )

    staged: list[StagedImage] = []
    provenance: list[AcquisitionProvenanceRecord] = []
    rejections: list[Rejection] = []
    boxes_discovered = 0
    boxes_semantic_rejected = 0
    boxes_geometry_rejected = 0
    boxes_staged = 0
    used_names: set[str] = set()

    if not dry_run:
        images_root.mkdir(parents=True, exist_ok=True)
        labels_root.mkdir(parents=True, exist_ok=True)

    for index, annotation in enumerate(annotations):
        identifier = annotation.image_rel
        boxes_discovered += len(annotation.boxes)

        if not annotation.boxes:
            rejections.append(
                Rejection(
                    source_identifier=identifier,
                    code=REJECT_NO_BBOX,
                    reason=(
                        "source image carries no bounding box; classification-only "
                        "data is never promoted to a detection label"
                    ),
                )
            )
            continue

        surviving, rejected_decisions, rejected_count = _gate_boxes(annotation)
        boxes_semantic_rejected += rejected_count
        if not surviving:
            rejections.append(
                Rejection(
                    source_identifier=identifier,
                    code=REJECT_SEMANTIC,
                    reason=(
                        "no box label explicitly denotes the target class; "
                        "ambiguous or class-distinct labels are never accepted"
                    ),
                    detail={"rejected_labels": rejected_decisions},
                )
            )
            continue

        readable = _image_opens(annotation.image_path)
        if readable:
            rejections.append(
                Rejection(
                    source_identifier=identifier,
                    code=REJECT_IMAGE_UNREADABLE,
                    reason=readable,
                )
            )
            continue

        valid_boxes: list[SourceBox] = []
        geometry_failures: list[str] = []
        for box in surviving:
            failure = validate_box_geometry(box)
            if failure:
                geometry_failures.append(failure)
                boxes_geometry_rejected += 1
            else:
                valid_boxes.append(box)
        if not valid_boxes:
            rejections.append(
                Rejection(
                    source_identifier=identifier,
                    code=REJECT_INVALID_GEOMETRY,
                    reason="every router box failed geometry validation",
                    detail={"failures": geometry_failures},
                )
            )
            continue

        name = _staged_name(identifier, index, annotation.image_path.suffix or ".jpg")
        if name in used_names:
            rejections.append(
                Rejection(
                    source_identifier=identifier,
                    code=REJECT_NAME_COLLISION,
                    reason=f"staged filename '{name}' already used by another image",
                )
            )
            continue
        used_names.add(name)

        label_name = str(Path(name).with_suffix(".txt"))
        label_text = (
            "\n".join(
                f"{taxonomy_id} {box.x_center:.6f} {box.y_center:.6f} "
                f"{box.width:.6f} {box.height:.6f}"
                for box in valid_boxes
            )
            + "\n"
        )

        if dry_run:
            checksum = compute_sha256(annotation.image_path)
        else:
            destination = images_root / name
            shutil.copy2(annotation.image_path, destination)
            (labels_root / label_name).write_text(label_text, encoding="utf-8")
            checksum = compute_sha256(destination)

        staged.append(
            StagedImage(
                relative_path=name,
                label_relative_path=label_name,
                box_count=len(valid_boxes),
                source_identifier=identifier,
                source_labels=tuple(
                    sorted({box.source_class_name for box in valid_boxes})
                ),
            )
        )
        provenance.append(
            AcquisitionProvenanceRecord(
                relative_path=name,
                original_filename=annotation.image_path.name,
                source_dataset=source_dataset,
                source_identifier=identifier,
                source_class=", ".join(
                    sorted({box.source_class_name for box in valid_boxes})
                ),
                taxonomy_class=taxonomy_class,
                taxonomy_id=taxonomy_id,
                license_id=license_decision.normalized_id,
                license_raw=license_decision.raw,
                license_url=license_decision.license_url,
                checksum_sha256=checksum,
                import_timestamp=import_timestamp,
                publisher=publisher,
                source_url=source_url,
            )
        )
        boxes_staged += len(valid_boxes)

    return IngestOutcome(
        staged=staged,
        provenance=provenance,
        rejections=rejections,
        images_discovered=len(annotations),
        boxes_discovered=boxes_discovered,
        boxes_semantically_rejected=boxes_semantic_rejected,
        boxes_geometry_rejected=boxes_geometry_rejected,
        boxes_staged=boxes_staged,
        source_format=detected.format_name,
        dry_run=dry_run,
    )
