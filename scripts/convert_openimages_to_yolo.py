"""Convert an Open Images V7 pilot into EcoTrace YOLO format (Laptop pilot).

Phase 4 dataset acquisition — controlled, provenance-preserving conversion of a
single-class Open Images pilot (Laptop) into the EcoTrace YOLO annotation format.

The Open Images / OIDv4 Toolkit source annotation is one box per line in
**pixel-space XYXY**::

    <SourceClass> x1 y1 x2 y2          e.g.  Laptop 195.84 0.0 766.72 432.64

This script converts each box to the normalised YOLO form the EcoTrace pipeline
consumes::

    <class_id> x_center y_center width height     (all in [0, 1])

using the sprint-mandated formulas::

    x_center = (x1 + x2) / 2 / image_width
    y_center = (y1 + y2) / 2 / image_height
    width    = (x2 - x1)     / image_width
    height   = (y2 - y1)     / image_height

Design guarantees (Phase 4 acquisition-pilot rules):

* **No frozen code is modified.** The EcoTrace taxonomy id is discovered at
  runtime through :func:`device_ai.dataset.taxonomy.load_taxonomy` (the source
  class id is never assumed) and the SHA-256 checksum reuses the frozen
  :func:`device_ai.dataset.hashing.sha256_hash`.
* **Source is read-only.** The OID images and labels are never written to; every
  output lands under a separate staging directory.
* **Reject, never clip.** A box whose normalised coordinates fall outside
  ``[0, 1]`` (i.e. the source box exceeds the image frame) is reported as an
  error, not silently clamped. File-level atomicity: if *any* line of a label
  fails, the whole image is skipped so staging only ever holds clean conversions.
* **Deterministic.** Identical source inputs + identical ``--conversion-version``
  produce byte-identical labels and provenance; the only wall-clock-like value,
  ``conversion_timestamp``, is *injected* via ``--created-at`` (never read from
  the clock).
* **No fabrication.** No dataset statistics or quality scores are invented, and
  nothing here marks the data as Dataset v1.0 READY or RELEASED. This is a
  Laptop acquisition pilot only.

Exit codes:
    0: every discovered image converted with no errors.
    1: one or more conversion errors were recorded.
    2: usage error (missing directories, unknown class, invalid timestamp).

Examples:
    # Convert the default 21-image Laptop pilot with injected defaults:
    python scripts/convert_openimages_to_yolo.py

    # Override any input explicitly (paths relative to the repo root):
    python scripts/convert_openimages_to_yolo.py \
        --source-images-root <oid>/train/Laptop \
        --source-labels-root <oid>/train/Laptop/Label \
        --staging-root dataset_acquisition/staging/openimages_laptop_v1 \
        --source-class Laptop --ecotrace-class laptop \
        --conversion-version openimages-laptop-v1 \
        --created-at 2026-08-08T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT
from PIL import Image, UnidentifiedImageError

from device_ai.dataset.hashing import sha256_hash
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_ERRORS = 1
_EXIT_USAGE = 2

# Number of decimal places kept in the normalised YOLO output. Six places is the
# de-facto YOLO precision and keeps output deterministic across platforms.
_PRECISION = 6

# Deterministic defaults for the 21-image Laptop pilot. Paths resolve relative to
# the repository root so the script works when launched from anywhere.
_DEFAULT_SOURCE_IMAGES = (
    REPO_ROOT / "dataset_acquisition/OIDv4_ToolKit/OID/Dataset/train/Laptop"
)
_DEFAULT_SOURCE_LABELS = _DEFAULT_SOURCE_IMAGES / "Label"
_DEFAULT_STAGING = REPO_ROOT / "dataset_acquisition/staging/openimages_laptop_v1"
_DEFAULT_SOURCE_NAME = "Open Images V7"
_DEFAULT_SOURCE_CLASS = "Laptop"
_DEFAULT_ECOTRACE_CLASS = "laptop"
_DEFAULT_CONVERSION_VERSION = "openimages-laptop-v1"
_DEFAULT_CREATED_AT = "2026-08-08T00:00:00+00:00"

# Source images carry the OID download extension; kept explicit so the pilot's
# discovery never accidentally pulls in the sibling ``Label/*.txt`` files.
_SOURCE_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


class ConversionError(Exception):
    """A recoverable, reportable problem converting one box, line or image.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SourceBox:
    """A single parsed Open Images box in pixel-space XYXY.

    Attributes:
        class_name: The source class label (may contain spaces, e.g. ``CRT
            monitor``); for this pilot it is ``Laptop``.
        x1: Left edge in pixels.
        y1: Top edge in pixels.
        x2: Right edge in pixels.
        y2: Bottom edge in pixels.
    """

    class_name: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True, slots=True)
class ConvertedBox:
    """A single normalised YOLO box.

    Attributes:
        class_id: The EcoTrace taxonomy class id (discovered, never assumed).
        x_center: Normalised centre x in ``[0, 1]``.
        y_center: Normalised centre y in ``[0, 1]``.
        width: Normalised width in ``(0, 1]``.
        height: Normalised height in ``(0, 1]``.
    """

    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class ConversionErrorRecord:
    """A recorded conversion failure for the error report.

    Attributes:
        stem: The image/label stem the error belongs to.
        file: The offending source file (relative to the repo root).
        line: 1-based source line number, or 0 for whole-file errors.
        code: Stable machine-readable error code.
        message: Human-readable description.
    """

    stem: str
    file: str
    line: int
    code: str
    message: str


def resolve_class_id(
    source_class: str,
    *,
    source_to_canonical: dict[str, str],
    taxonomy: DeviceTaxonomy,
) -> tuple[str, int]:
    """Resolve a source class name to its EcoTrace canonical name and class id.

    The id is looked up in the frozen taxonomy — it is never hardcoded, so a
    taxonomy re-ordering is picked up automatically.

    Args:
        source_class: The Open Images class label (e.g. ``Laptop``).
        source_to_canonical: Mapping from source class names to canonical
            EcoTrace taxonomy names (e.g. ``{"Laptop": "laptop"}``).
        taxonomy: The loaded EcoTrace taxonomy.

    Returns:
        A ``(canonical_name, class_id)`` tuple.

    Raises:
        ConversionError: ``UNKNOWN_SOURCE_CLASS`` when the source class has no
            mapping; ``WRONG_TAXONOMY_MAPPING`` when the mapped canonical name is
            not present in the taxonomy.
    """
    if source_class not in source_to_canonical:
        raise ConversionError(
            "UNKNOWN_SOURCE_CLASS",
            f"source class '{source_class}' has no EcoTrace mapping",
        )
    canonical = source_to_canonical[source_class]
    class_id = taxonomy.class_id_for(canonical)
    if class_id is None:
        raise ConversionError(
            "WRONG_TAXONOMY_MAPPING",
            (
                f"mapped class '{canonical}' is not in the frozen taxonomy "
                f"(version {taxonomy.version})"
            ),
        )
    return canonical, class_id


def parse_source_line(line: str) -> SourceBox:
    """Parse one Open Images annotation line into a :class:`SourceBox`.

    The class name may contain spaces, so the final four whitespace-separated
    fields are the coordinates and everything before them is the class name.

    Args:
        line: A single, non-empty source annotation line.

    Returns:
        The parsed :class:`SourceBox`.

    Raises:
        ConversionError: ``MALFORMED_LINE`` when the field count is wrong, the
            class name is empty, or a coordinate is non-numeric.
    """
    fields = line.split()
    if len(fields) < 5:
        raise ConversionError(
            "MALFORMED_LINE",
            f"expected '<class> x1 y1 x2 y2', found {len(fields)} field(s)",
        )
    *class_parts, x1, y1, x2, y2 = fields
    class_name = " ".join(class_parts)
    if not class_name:
        raise ConversionError("MALFORMED_LINE", "missing source class name")
    try:
        values = tuple(float(value) for value in (x1, y1, x2, y2))
    except ValueError as exc:
        raise ConversionError(
            "MALFORMED_LINE", "non-numeric coordinate field"
        ) from exc
    return SourceBox(
        class_name=class_name, x1=values[0], y1=values[1], x2=values[2], y2=values[3]
    )


def convert_box(
    box: SourceBox,
    *,
    image_width: int,
    image_height: int,
    class_id: int,
    precision: int = _PRECISION,
) -> ConvertedBox:
    """Convert one pixel-space XYXY box to a normalised YOLO box.

    Coordinates are validated against ``[0, 1]`` on the *raw* (pre-rounding)
    values so a box that spills past the image frame is rejected rather than
    clipped. The output is rounded to ``precision`` places for determinism.

    Args:
        box: The parsed source box.
        image_width: Image width in pixels (> 0).
        image_height: Image height in pixels (> 0).
        class_id: The resolved EcoTrace class id.
        precision: Decimal places to keep in the output.

    Returns:
        The normalised :class:`ConvertedBox`.

    Raises:
        ConversionError: ``INVALID_IMAGE_DIMENSIONS`` for a non-positive frame;
            ``NON_POSITIVE_SIZE`` when ``x2 <= x1`` or ``y2 <= y1``;
            ``COORD_OUT_OF_RANGE`` when any normalised value leaves ``[0, 1]``.
    """
    if image_width <= 0 or image_height <= 0:
        raise ConversionError(
            "INVALID_IMAGE_DIMENSIONS",
            f"image dimensions must be positive, got {image_width}x{image_height}",
        )
    if box.x2 <= box.x1 or box.y2 <= box.y1:
        raise ConversionError(
            "NON_POSITIVE_SIZE",
            (
                "source box has non-positive size "
                f"(x1={box.x1}, y1={box.y1}, x2={box.x2}, y2={box.y2})"
            ),
        )

    x_center = (box.x1 + box.x2) / 2.0 / image_width
    y_center = (box.y1 + box.y2) / 2.0 / image_height
    width = (box.x2 - box.x1) / image_width
    height = (box.y2 - box.y1) / image_height

    for name, value in (
        ("x_center", x_center),
        ("y_center", y_center),
        ("width", width),
        ("height", height),
    ):
        if not 0.0 <= value <= 1.0:
            raise ConversionError(
                "COORD_OUT_OF_RANGE",
                (
                    f"{name}={value:.6f} outside [0, 1]; source box exceeds the "
                    f"{image_width}x{image_height} image frame"
                ),
            )

    return ConvertedBox(
        class_id=class_id,
        x_center=round(x_center, precision),
        y_center=round(y_center, precision),
        width=round(width, precision),
        height=round(height, precision),
    )


def format_yolo_line(box: ConvertedBox) -> str:
    """Render a :class:`ConvertedBox` as a single YOLO label line.

    Args:
        box: The converted box.

    Returns:
        ``"<class_id> <x_center> <y_center> <width> <height>"`` with fixed
        precision so identical inputs yield byte-identical text.
    """
    return (
        f"{box.class_id} "
        f"{box.x_center:.{_PRECISION}f} "
        f"{box.y_center:.{_PRECISION}f} "
        f"{box.width:.{_PRECISION}f} "
        f"{box.height:.{_PRECISION}f}"
    )


def _read_image(path: Path) -> tuple[bytes, int, int]:
    """Read an image's raw bytes and pixel dimensions.

    Args:
        path: Absolute path of the source image.

    Returns:
        ``(raw_bytes, width, height)``.

    Raises:
        ConversionError: ``UNREADABLE_IMAGE`` when the file cannot be decoded.
    """
    try:
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            width, height = opened.width, opened.height
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ConversionError("UNREADABLE_IMAGE", str(exc)) from exc
    return data, width, height


@dataclass(frozen=True, slots=True)
class ImageConversion:
    """The outcome of converting one source image + its label.

    Attributes:
        stem: The shared image/label stem.
        image_bytes: Verbatim source image bytes (byte-identical staged copy).
        image_suffix: The source image file suffix (e.g. ``.jpg``).
        yolo_lines: The converted YOLO label lines (empty when failed).
        provenance: The per-image provenance record.
        source_object_count: Boxes present in the source label.
        converted_object_count: Boxes successfully converted.
        errors: Any per-line/whole-image errors (non-empty means not staged).
    """

    stem: str
    image_bytes: bytes
    image_suffix: str
    yolo_lines: tuple[str, ...]
    provenance: dict[str, object]
    source_object_count: int
    converted_object_count: int
    errors: tuple[ConversionErrorRecord, ...]

    @property
    def ok(self) -> bool:
        """Whether the image converted cleanly (no errors)."""
        return not self.errors


def _build_provenance(
    *,
    stem: str,
    image_path: Path,
    label_path: Path,
    sha256: str,
    width: int,
    height: int,
    object_count: int,
    source_name: str,
    source_class: str,
    ecotrace_class: str,
    class_id: int,
    conversion_version: str,
    conversion_timestamp: str,
) -> dict[str, object]:
    """Assemble the provenance record for one converted image."""
    return {
        "stem": stem,
        "source": source_name,
        "source_class": source_class,
        "ecotrace_class": ecotrace_class,
        "ecotrace_class_id": class_id,
        "source_image_filename": image_path.name,
        "source_annotation_filename": label_path.name,
        "sha256": sha256,
        "width": width,
        "height": height,
        "object_count": object_count,
        "conversion_version": conversion_version,
        "conversion_timestamp": conversion_timestamp,
    }


def convert_image(
    *,
    image_path: Path,
    label_path: Path,
    source_to_canonical: dict[str, str],
    taxonomy: DeviceTaxonomy,
    source_name: str,
    conversion_version: str,
    conversion_timestamp: str,
    labels_root: Path,
) -> ImageConversion:
    """Convert one source image and its label into a staged YOLO conversion.

    File-level atomicity: if the label is missing or *any* line fails, the image
    is marked failed (no label emitted, image not staged) and every failure is
    recorded, so staging only ever contains fully-valid conversions.

    Args:
        image_path: Absolute path of the source image.
        label_path: Absolute path of the matching source label.
        source_to_canonical: Source-class -> canonical-name mapping.
        taxonomy: The loaded EcoTrace taxonomy.
        source_name: Human-readable source identifier (e.g. ``Open Images V7``).
        conversion_version: The conversion/version identifier.
        conversion_timestamp: Injected ISO-8601 timestamp.
        labels_root: Source labels root (used for error file provenance).

    Returns:
        The :class:`ImageConversion` describing the outcome.
    """
    stem = image_path.stem
    errors: list[ConversionErrorRecord] = []

    try:
        image_bytes, width, height = _read_image(image_path)
    except ConversionError as exc:
        return ImageConversion(
            stem=stem,
            image_bytes=b"",
            image_suffix=image_path.suffix,
            yolo_lines=(),
            provenance={},
            source_object_count=0,
            converted_object_count=0,
            errors=(
                ConversionErrorRecord(
                    stem=stem,
                    file=_rel(image_path),
                    line=0,
                    code=exc.code,
                    message=exc.message,
                ),
            ),
        )
    sha256 = sha256_hash(image_bytes)

    if not label_path.exists():
        errors.append(
            ConversionErrorRecord(
                stem=stem,
                file=_rel(image_path),
                line=0,
                code="MISSING_SOURCE_LABEL",
                message=f"no source label found at {_rel(label_path)}",
            )
        )
        return ImageConversion(
            stem=stem,
            image_bytes=image_bytes,
            image_suffix=image_path.suffix,
            yolo_lines=(),
            provenance={},
            source_object_count=0,
            converted_object_count=0,
            errors=tuple(errors),
        )

    lines, source_count = _convert_label_lines(
        label_path=label_path,
        width=width,
        height=height,
        source_to_canonical=source_to_canonical,
        taxonomy=taxonomy,
        labels_root=labels_root,
        stem=stem,
        errors=errors,
    )

    provenance = _build_provenance(
        stem=stem,
        image_path=image_path,
        label_path=label_path,
        sha256=sha256,
        width=width,
        height=height,
        object_count=len(lines),
        source_name=source_name,
        source_class=_source_class_of(source_to_canonical),
        ecotrace_class=_canonical_of(source_to_canonical),
        class_id=taxonomy.class_id_for(_canonical_of(source_to_canonical)) or 0,
        conversion_version=conversion_version,
        conversion_timestamp=conversion_timestamp,
    )

    return ImageConversion(
        stem=stem,
        image_bytes=image_bytes,
        image_suffix=image_path.suffix,
        yolo_lines=tuple(lines),
        provenance=provenance,
        source_object_count=source_count,
        converted_object_count=len(lines),
        errors=tuple(errors),
    )


def _convert_label_lines(
    *,
    label_path: Path,
    width: int,
    height: int,
    source_to_canonical: dict[str, str],
    taxonomy: DeviceTaxonomy,
    labels_root: Path,
    stem: str,
    errors: list[ConversionErrorRecord],
) -> tuple[list[str], int]:
    """Convert every line of one source label file.

    Args:
        label_path: Absolute path of the source label file.
        width: Image width in pixels.
        height: Image height in pixels.
        source_to_canonical: Source-class -> canonical-name mapping.
        taxonomy: The loaded EcoTrace taxonomy.
        labels_root: Source labels root (for error provenance).
        stem: The image/label stem.
        errors: Mutable list that per-line errors are appended to.

    Returns:
        A ``(yolo_lines, source_box_count)`` tuple. ``yolo_lines`` is empty when
        any line failed (file-level atomicity).
    """
    try:
        text = label_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(
            ConversionErrorRecord(
                stem=stem,
                file=_rel(label_path),
                line=0,
                code="UNREADABLE_LABEL",
                message=str(exc),
            )
        )
        return [], 0

    lines: list[str] = []
    source_count = 0
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        source_count += 1
        try:
            box = parse_source_line(stripped)
            _, class_id = resolve_class_id(
                box.class_name,
                source_to_canonical=source_to_canonical,
                taxonomy=taxonomy,
            )
            converted = convert_box(
                box, image_width=width, image_height=height, class_id=class_id
            )
        except ConversionError as exc:
            errors.append(
                ConversionErrorRecord(
                    stem=stem,
                    file=_rel(label_path),
                    line=line_no,
                    code=exc.code,
                    message=exc.message,
                )
            )
            continue
        lines.append(format_yolo_line(converted))

    if source_count == 0:
        errors.append(
            ConversionErrorRecord(
                stem=stem,
                file=_rel(label_path),
                line=0,
                code="EMPTY_SOURCE_LABEL",
                message="source label contains no boxes",
            )
        )

    # File-level atomicity: any error voids the whole file so partial,
    # possibly-misleading conversions never reach staging.
    if errors:
        return [], source_count
    return lines, source_count


def _source_class_of(source_to_canonical: dict[str, str]) -> str:
    """Return the single source class for a one-entry pilot mapping."""
    return next(iter(source_to_canonical))


def _canonical_of(source_to_canonical: dict[str, str]) -> str:
    """Return the single canonical class for a one-entry pilot mapping."""
    return next(iter(source_to_canonical.values()))


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repo root as POSIX, or its name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """The full outcome of a conversion run.

    Attributes:
        conversions: Per-image conversion outcomes (sorted by stem).
        report: The JSON-serialisable conversion report.
        provenance: The JSON-serialisable provenance manifest.
        errors: The JSON-serialisable conversion error report.
    """

    conversions: tuple[ImageConversion, ...]
    report: dict[str, object]
    provenance: dict[str, object]
    errors: dict[str, object]


def convert_dataset(
    *,
    source_images_root: Path,
    source_labels_root: Path,
    source_to_canonical: dict[str, str],
    taxonomy: DeviceTaxonomy,
    source_name: str,
    conversion_version: str,
    conversion_timestamp: str,
) -> ConversionResult:
    """Convert every discovered source image into staged YOLO conversions.

    Also detects orphan source labels (a ``.txt`` with no matching image).

    Args:
        source_images_root: Directory holding the source images (non-recursive
            top level; the sibling ``Label/`` dir holds the annotations).
        source_labels_root: Directory holding the source ``.txt`` labels.
        source_to_canonical: Source-class -> canonical-name mapping.
        taxonomy: The loaded EcoTrace taxonomy.
        source_name: Human-readable source identifier.
        conversion_version: The conversion/version identifier.
        conversion_timestamp: Injected ISO-8601 timestamp.

    Returns:
        The assembled :class:`ConversionResult` (no files written).
    """
    image_paths = _list_source_images(source_images_root)
    conversions = [
        convert_image(
            image_path=image_path,
            label_path=(source_labels_root / f"{image_path.stem}.txt"),
            source_to_canonical=source_to_canonical,
            taxonomy=taxonomy,
            source_name=source_name,
            conversion_version=conversion_version,
            conversion_timestamp=conversion_timestamp,
            labels_root=source_labels_root,
        )
        for image_path in image_paths
    ]

    orphan_errors = _detect_orphan_labels(
        source_images_root=source_images_root,
        source_labels_root=source_labels_root,
        image_paths=image_paths,
    )

    canonical = _canonical_of(source_to_canonical)
    class_id = taxonomy.class_id_for(canonical)
    context: dict[str, object] = {
        "source": source_name,
        "source_class": _source_class_of(source_to_canonical),
        "ecotrace_class": canonical,
        "ecotrace_class_id": class_id,
        "taxonomy_version": taxonomy.version,
        "conversion_version": conversion_version,
        "conversion_timestamp": conversion_timestamp,
        "source_images_root": _rel(source_images_root),
        "source_labels_root": _rel(source_labels_root),
    }

    report = _build_report(
        conversions=conversions,
        orphan_errors=orphan_errors,
        source_label_count=_count_labels(source_labels_root),
        context=context,
    )
    provenance = _build_provenance_manifest(conversions=conversions, context=context)
    errors = _build_error_report(
        conversions=conversions,
        orphan_errors=orphan_errors,
        conversion_version=conversion_version,
    )
    return ConversionResult(
        conversions=tuple(conversions),
        report=report,
        provenance=provenance,
        errors=errors,
    )


def _list_source_images(root: Path) -> list[Path]:
    """Return sorted top-level source images under ``root`` (non-recursive)."""
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in _SOURCE_IMAGE_SUFFIXES
    )


def _count_labels(labels_root: Path) -> int:
    """Return the number of ``.txt`` source labels under ``labels_root``."""
    if not labels_root.is_dir():
        return 0
    return sum(1 for path in labels_root.glob("*.txt") if path.is_file())


def _detect_orphan_labels(
    *,
    source_images_root: Path,
    source_labels_root: Path,
    image_paths: list[Path],
) -> list[ConversionErrorRecord]:
    """Return one error per source label that has no matching source image."""
    image_stems = {path.stem for path in image_paths}
    orphans: list[ConversionErrorRecord] = []
    if not source_labels_root.is_dir():
        return orphans
    for label_path in sorted(source_labels_root.glob("*.txt")):
        if label_path.stem not in image_stems:
            orphans.append(
                ConversionErrorRecord(
                    stem=label_path.stem,
                    file=_rel(label_path),
                    line=0,
                    code="MISSING_SOURCE_IMAGE",
                    message="source label has no matching source image",
                )
            )
    return orphans


def _build_report(
    *,
    conversions: list[ImageConversion],
    orphan_errors: list[ConversionErrorRecord],
    source_label_count: int,
    context: dict[str, object],
) -> dict[str, object]:
    """Assemble the conversion report document (no invented statistics)."""
    converted = [c for c in conversions if c.ok]
    failed = [c for c in conversions if not c.ok]
    total_source_objects = sum(c.source_object_count for c in conversions)
    total_converted_objects = sum(c.converted_object_count for c in converted)
    error_count = sum(len(c.errors) for c in conversions) + len(orphan_errors)

    per_image = [
        {
            "stem": c.stem,
            "source_image_filename": f"{c.stem}{c.image_suffix}",
            "source_annotation_filename": f"{c.stem}.txt",
            "source_object_count": c.source_object_count,
            "converted_object_count": c.converted_object_count,
            "status": "converted" if c.ok else "failed",
        }
        for c in conversions
    ]

    return {
        **context,
        "summary": {
            "source_images_found": len(conversions),
            "source_labels_found": source_label_count,
            "images_converted": len(converted),
            "images_failed": len(failed),
            "total_source_objects": total_source_objects,
            "total_converted_objects": total_converted_objects,
            "orphan_source_labels": len(orphan_errors),
            "conversion_error_count": error_count,
        },
        "per_image": per_image,
    }


def _build_provenance_manifest(
    *,
    conversions: list[ImageConversion],
    context: dict[str, object],
) -> dict[str, object]:
    """Assemble the provenance manifest (staged images only)."""
    records = [c.provenance for c in conversions if c.ok]
    return {
        **context,
        "total_images": len(records),
        "records": records,
    }


def _build_error_report(
    *,
    conversions: list[ImageConversion],
    orphan_errors: list[ConversionErrorRecord],
    conversion_version: str,
) -> dict[str, object]:
    """Assemble the conversion error report (empty ``errors`` when clean)."""
    records: list[ConversionErrorRecord] = []
    for conversion in conversions:
        records.extend(conversion.errors)
    records.extend(orphan_errors)
    records.sort(key=lambda e: (e.stem, e.line, e.code))
    return {
        "conversion_version": conversion_version,
        "error_count": len(records),
        "errors": [
            {
                "stem": record.stem,
                "file": record.file,
                "line": record.line,
                "code": record.code,
                "message": record.message,
            }
            for record in records
        ],
    }


def write_outputs(result: ConversionResult, *, staging_root: Path) -> dict[str, Path]:
    """Write staged images, labels, provenance and reports under a staging root.

    Only cleanly-converted images are staged (with their YOLO label), keeping a
    strict one-to-one image/label pairing. Source files are never touched.

    Args:
        result: The conversion result to persist.
        staging_root: Destination staging directory (created if missing).

    Returns:
        A mapping of the key output paths that were written.
    """
    images_dir = staging_root / "images"
    labels_dir = staging_root / "labels"
    provenance_dir = staging_root / "provenance"
    reports_dir = staging_root / "reports"
    for directory in (images_dir, labels_dir, provenance_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for conversion in result.conversions:
        if not conversion.ok:
            continue
        (images_dir / f"{conversion.stem}{conversion.image_suffix}").write_bytes(
            conversion.image_bytes
        )
        label_text = "\n".join(conversion.yolo_lines)
        (labels_dir / f"{conversion.stem}.txt").write_text(
            label_text + "\n" if label_text else "", encoding="utf-8"
        )

    provenance_path = provenance_dir / "provenance_manifest.json"
    report_path = reports_dir / "conversion_report.json"
    errors_path = reports_dir / "conversion_errors.json"
    provenance_path.write_text(
        json.dumps(result.provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(result.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    errors_path.write_text(
        json.dumps(result.errors, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "images_dir": images_dir,
        "labels_dir": labels_dir,
        "provenance": provenance_path,
        "report": report_path,
        "errors": errors_path,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert an Open Images V7 pilot (Laptop) into EcoTrace YOLO format "
            "with preserved provenance. Read-only on the source; writes only to "
            "a staging directory. This is a Dataset v1.0 acquisition pilot only."
        )
    )
    parser.add_argument(
        "--source-images-root",
        type=Path,
        default=_DEFAULT_SOURCE_IMAGES,
        help="Directory of source Open Images images (default: OID Laptop pilot).",
    )
    parser.add_argument(
        "--source-labels-root",
        type=Path,
        default=_DEFAULT_SOURCE_LABELS,
        help="Directory of source .txt labels (default: OID Laptop Label dir).",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=_DEFAULT_STAGING,
        help="Destination staging directory (never the OID source).",
    )
    parser.add_argument(
        "--source-name",
        default=_DEFAULT_SOURCE_NAME,
        help=f"Human-readable source identifier (default '{_DEFAULT_SOURCE_NAME}').",
    )
    parser.add_argument(
        "--source-class",
        default=_DEFAULT_SOURCE_CLASS,
        help=f"Open Images source class name (default '{_DEFAULT_SOURCE_CLASS}').",
    )
    parser.add_argument(
        "--ecotrace-class",
        default=_DEFAULT_ECOTRACE_CLASS,
        help=(
            "Canonical EcoTrace taxonomy class the source maps to "
            f"(default '{_DEFAULT_ECOTRACE_CLASS}'). The class id is discovered "
            "from the frozen taxonomy, never assumed."
        ),
    )
    parser.add_argument(
        "--conversion-version",
        default=_DEFAULT_CONVERSION_VERSION,
        help=(
            "Conversion/version identifier recorded in provenance "
            f"(default '{_DEFAULT_CONVERSION_VERSION}')."
        ),
    )
    parser.add_argument(
        "--created-at",
        default=_DEFAULT_CREATED_AT,
        help=(
            "ISO-8601 conversion timestamp, injected for reproducibility "
            f"(default '{_DEFAULT_CREATED_AT}')."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Open Images -> EcoTrace YOLO converter.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 clean, 1 conversion errors, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.source_images_root.is_dir():
        print(
            f"error: source images root not found: {args.source_images_root}",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    if not args.source_labels_root.is_dir():
        print(
            f"error: source labels root not found: {args.source_labels_root}",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.created_at)
    except ValueError:
        print(
            f"error: --created-at is not a valid ISO-8601 timestamp: "
            f"{args.created_at}",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    taxonomy = load_taxonomy()
    source_to_canonical = {args.source_class: args.ecotrace_class}
    # Fail fast on an unmappable class before touching the filesystem.
    try:
        resolve_class_id(
            args.source_class,
            source_to_canonical=source_to_canonical,
            taxonomy=taxonomy,
        )
    except ConversionError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        return _EXIT_USAGE

    result = convert_dataset(
        source_images_root=args.source_images_root,
        source_labels_root=args.source_labels_root,
        source_to_canonical=source_to_canonical,
        taxonomy=taxonomy,
        source_name=args.source_name,
        conversion_version=args.conversion_version,
        conversion_timestamp=args.created_at,
    )
    outputs = write_outputs(result, staging_root=args.staging_root)

    summary = result.report["summary"]
    assert isinstance(summary, dict)
    print(json.dumps(result.report, indent=2, sort_keys=True))
    print(
        f"staged {summary['images_converted']}/{summary['source_images_found']} "
        f"images -> {outputs['images_dir'].as_posix()} "
        f"({summary['conversion_error_count']} error(s))",
        file=sys.stderr,
    )
    return _EXIT_OK if summary["conversion_error_count"] == 0 else _EXIT_ERRORS


if __name__ == "__main__":
    raise SystemExit(main())
