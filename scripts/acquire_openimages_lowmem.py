"""Low-memory Open Images V7 acquisition adapter (Sprint P4.3.3).

The vendored ``OIDv4_ToolKit`` loads the entire ~1.19 GB, ~14.6M-row
``train-annotations-bbox.csv`` into a single :func:`pandas.read_csv` call
(``modules/csv_downloader.py:TTV``). Every column is inferred as an ``object``
dtype, so the in-memory frame balloons to many gigabytes and the process is
killed with ``numpy._core._exceptions._ArrayMemoryError`` (observed:
``Unable to allocate ... shape (14610229,)``) before a single image is fetched.
That is the exact wall the ``printer`` class hit in P4.3.2.

This module is a **thin, project-owned adapter** that replaces only that one
fragile step — the annotation *scan* — with a genuinely memory-bounded,
chunked reader. It plugs into the existing P4.3.1 orchestrator through its
public :data:`~acquire_openimages_multiclass.DownloadFn` seam
(:class:`~acquire_openimages_multiclass.DownloadRequest` ->
:class:`~acquire_openimages_multiclass.DownloadResult`), so the orchestration
contract, the frozen converter, the validators and the QA boundary are all
reused verbatim. It is **not** a second dataset architecture and it introduces
**no** new annotation format: it emits exactly the OIDv4 per-class source layout
the frozen converter already consumes::

    OID/Dataset/train/<SourceClass>/<ImageID>.jpg
    OID/Dataset/train/<SourceClass>/Label/<ImageID>.txt
        # each line: "<SourceClass> x1 y1 x2 y2" (pixel XYXY)

Design guarantees:

* **Memory bounded.** The bbox CSV is streamed with
  ``pandas.read_csv(usecols=[11 of 13 columns], dtype=<narrowest>, chunksize=N)``.
  Only rows whose ``LabelName`` equals the target class MID survive each chunk;
  the full CSV is never materialised. Selection stops as soon as ``--limit``
  distinct ImageIDs are collected, so a bounded pilot reads only the leading
  chunks.
* **Source fidelity.** Exact source ImageIDs and exact source XYXY boxes are
  preserved. Normalised OID coordinates are multiplied by the *real* downloaded
  image's pixel dimensions — the same math the vendored ``get_label`` uses — so
  the labels are byte-for-byte what the converter would have received.
* **Attribute filtering preserved.** The five OID image attributes
  (``IsOccluded``/``IsTruncated``/``IsGroupOf``/``IsDepiction``/``IsInside``)
  are honoured with the same semantics as the toolkit's ``images_options``.
* **No fabrication.** Image/label counts are read from the filesystem after the
  real S3 download; a class that yields zero images is reported as zero.
* **Deterministic.** ImageIDs are selected in first-seen CSV order until
  ``--limit`` distinct ids are held. Because the bbox CSV is ImageID-contiguous
  (all of an image's boxes are adjacent), the scan stops the instant a *new*
  distinct id appears past the limit, so an identical CSV + limit selects an
  identical, fully-boxed set regardless of chunk size.
* **Source read-only + isolated.** Writes only under the toolkit's own
  ``OID/Dataset/train/<SourceClass>`` tree (the same location the vendored
  toolkit uses); never touches ``intelligence/device_ai`` or staged pilots.

The vendored toolkit is **not modified**: this adapter re-implements only the
scan+download+label steps it needs, reusing the toolkit's on-disk CSV cache and
the same ``aws s3 --no-sign-request`` object layout.

Exit codes:
    0: the bounded scan+download completed (zero images is still a clean run).
    1: a fatal acquisition error (missing CSV, unresolved class, aws failure).
    2: usage error (bad arguments).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import acquire_openimages_multiclass as orch
import pandas as pd
from _ecotrace_toolkit import REPO_ROOT

_EXIT_OK = 0
_EXIT_FAILURES = 1
_EXIT_USAGE = 2

# The Open Images train bbox CSV header (2018_04 release) is:
#   ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,
#   IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside
# We read only the 11 columns needed to (a) match the class MID, (b) filter on
# the image attributes and (c) reconstruct the source box. ``Source`` and
# ``Confidence`` (the two frame-of-reference-only columns) are never loaded.
_USECOLS = (
    "ImageID",
    "LabelName",
    "XMin",
    "XMax",
    "YMin",
    "YMax",
    "IsOccluded",
    "IsTruncated",
    "IsGroupOf",
    "IsDepiction",
    "IsInside",
)

# Narrowest safe dtypes: ImageIDs/MIDs as pandas 'string' (backed by Arrow-free
# object but far lighter than inferred object columns once filtered), the four
# normalised coordinates as float32 (they are in [0, 1]; float32 keeps ~7 sig
# figs which is ample for pixel reconstruction), and the five 0/1 attribute
# flags as the smallest signed integer. This keeps each chunk tiny.
_DTYPES: dict[str, str] = {
    "ImageID": "string",
    "LabelName": "string",
    "XMin": "float32",
    "XMax": "float32",
    "YMin": "float32",
    "YMax": "float32",
    "IsOccluded": "int8",
    "IsTruncated": "int8",
    "IsGroupOf": "int8",
    "IsDepiction": "int8",
    "IsInside": "int8",
}

# Default rows per chunk. 500k rows x 11 narrow columns is a few tens of MB per
# chunk — comfortably bounded regardless of the 14.6M-row total.
_DEFAULT_CHUNK_SIZE = 500_000

_TRAIN_BBOX_CSV = "train-annotations-bbox.csv"
_CLASS_DESCRIPTIONS_CSV = "class-descriptions-boxable.csv"

# The five OID per-image attribute filters, mapped to their CSV column. ``None``
# in the selector means "don't filter on this attribute" (the toolkit default).
_ATTRIBUTE_COLUMNS = (
    "IsOccluded",
    "IsTruncated",
    "IsGroupOf",
    "IsDepiction",
    "IsInside",
)


class AcquisitionError(Exception):
    """A fatal problem scanning, resolving or downloading a class."""


@dataclass(frozen=True, slots=True)
class SourceBoxRow:
    """One retained annotation row in normalised OID space (all coords in [0, 1]).

    Attributes:
        image_id: The Open Images ImageID (exact, preserved verbatim).
        x_min: Left edge, normalised to image width.
        x_max: Right edge, normalised to image width.
        y_min: Top edge, normalised to image height.
        y_max: Bottom edge, normalised to image height.
    """

    image_id: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass(frozen=True, slots=True)
class AttributeSelector:
    """Optional OID image-attribute filters (``None`` = accept either value).

    Mirrors ``OIDv4_ToolKit/modules/utils.py:images_options`` semantics: a
    non-``None`` value keeps only rows whose attribute equals it.
    """

    is_occluded: int | None = None
    is_truncated: int | None = None
    is_group_of: int | None = None
    is_depiction: int | None = None
    is_inside: int | None = None

    def as_map(self) -> dict[str, int]:
        """Return the active ``{column: required_value}`` filters only."""
        pairs = zip(
            _ATTRIBUTE_COLUMNS,
            (
                self.is_occluded,
                self.is_truncated,
                self.is_group_of,
                self.is_depiction,
                self.is_inside,
            ),
            strict=True,
        )
        return {col: val for col, val in pairs if val is not None}


@dataclass(frozen=True, slots=True)
class ScanResult:
    """The outcome of a bounded, low-memory annotation scan.

    Attributes:
        image_ids: The selected ImageIDs in first-seen CSV order (at most
            ``limit``).
        boxes_by_image: Every retained source box, grouped by ImageID.
        rows_read: Total CSV rows actually streamed across all chunks — a
            memory-independent proxy for how much of the file was touched.
        chunks_read: Number of chunks pulled from the reader.
        matched_rows: Rows whose class + attributes matched (pre-limit).
    """

    image_ids: tuple[str, ...]
    boxes_by_image: dict[str, tuple[SourceBoxRow, ...]]
    rows_read: int
    chunks_read: int
    matched_rows: int


def resolve_class_mid(class_descriptions_csv: Path, source_class: str) -> str:
    """Resolve an Open Images display name to its MID.

    For example ``Printer`` -> ``/m/01m4t``.

    The class-descriptions file is tiny (~600 rows) so a full read is fine; it
    is the *bbox* file that must be streamed.

    Args:
        class_descriptions_csv: Path to ``class-descriptions-boxable.csv``.
        source_class: The Open Images boxable display name (e.g. ``Printer``).

    Returns:
        The ``/m/...`` machine id for the class.

    Raises:
        AcquisitionError: When the file is missing or the class is not found.
    """
    if not class_descriptions_csv.is_file():
        raise AcquisitionError(
            f"class descriptions CSV not found: {class_descriptions_csv}"
        )
    descriptions = pd.read_csv(
        class_descriptions_csv, header=None, names=("mid", "display_name")
    )
    match = descriptions.loc[descriptions["display_name"] == source_class]
    if match.empty:
        raise AcquisitionError(
            f"Open Images class '{source_class}' not found in "
            f"{class_descriptions_csv.name}"
        )
    return str(match.iloc[0]["mid"])


def iter_matching_chunks(
    bbox_csv: Path,
    *,
    class_mid: str,
    selector: AttributeSelector,
    chunk_size: int,
) -> Iterator[tuple[pd.DataFrame, int]]:
    """Stream the bbox CSV in chunks, yielding only rows matching the class.

    This is the memory-bounded heart of the adapter. Each chunk is filtered to
    the target ``class_mid`` (and any active attribute filters) *before* being
    yielded, so at most one ``chunk_size``-row frame (narrow dtypes) is resident
    at any time and the filtered remainder is tiny.

    Args:
        bbox_csv: Path to ``train-annotations-bbox.csv``.
        class_mid: The target class MID (``/m/...``).
        selector: Active OID image-attribute filters.
        chunk_size: Rows per chunk handed to ``pandas.read_csv``.

    Yields:
        ``(matched_rows, raw_chunk_len)`` per chunk — ``matched_rows`` holds only
        the rows that matched (may be empty); ``raw_chunk_len`` is the real
        number of rows read from the file for that chunk (for honest accounting).

    Raises:
        AcquisitionError: When the bbox CSV is missing.
    """
    if not bbox_csv.is_file():
        raise AcquisitionError(f"train annotations CSV not found: {bbox_csv}")
    attribute_filters = selector.as_map()
    reader = pd.read_csv(
        bbox_csv,
        usecols=list(_USECOLS),
        dtype=_DTYPES,
        chunksize=chunk_size,
    )
    for chunk in reader:
        raw_len = len(chunk)
        matched = chunk.loc[chunk["LabelName"] == class_mid]
        for column, required in attribute_filters.items():
            matched = matched.loc[matched[column] == required]
        yield matched, raw_len


def scan_class_annotations(
    bbox_csv: Path,
    *,
    class_mid: str,
    limit: int,
    selector: AttributeSelector | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> ScanResult:
    """Collect the first ``limit`` distinct ImageIDs (and their boxes) for a class.

    Reads the CSV chunk by chunk, accumulating matching rows grouped by ImageID
    in **first-seen order**. Because the Open Images bbox CSV is sorted by
    ImageID (every ImageID's rows are contiguous), all boxes for a given image
    arrive together; the scan therefore stops the instant it encounters a
    *new* distinct ImageID once ``limit`` images are already held — at which
    point every selected image is complete. This makes the selection both
    memory bounded (only the chosen images' boxes plus one chunk are ever
    resident) and deterministic **independent of ``chunk_size``**: the same CSV
    and limit always yield the same first-``limit`` images with all their boxes.

    Args:
        bbox_csv: Path to ``train-annotations-bbox.csv``.
        class_mid: The target class MID (``/m/...``).
        limit: Maximum number of distinct ImageIDs to acquire.
        selector: Optional OID image-attribute filters.
        chunk_size: Rows per chunk.

    Returns:
        A :class:`ScanResult` with the selected ImageIDs and their source boxes.
    """
    selector = selector or AttributeSelector()
    # Insertion order == first-seen order, so tuple(selected) is deterministic.
    selected: dict[str, list[SourceBoxRow]] = {}
    rows_read = 0
    chunks_read = 0
    matched_rows = 0
    done = False

    for matched, raw_len in iter_matching_chunks(
        bbox_csv, class_mid=class_mid, selector=selector, chunk_size=chunk_size
    ):
        chunks_read += 1
        rows_read += raw_len
        matched_rows += len(matched)
        for row in matched.itertuples(index=False):
            image_id = str(row.ImageID)
            box = SourceBoxRow(
                image_id=image_id,
                x_min=float(row.XMin),
                x_max=float(row.XMax),
                y_min=float(row.YMin),
                y_max=float(row.YMax),
            )
            if image_id in selected:
                selected[image_id].append(box)
            elif len(selected) < limit:
                selected[image_id] = [box]
            else:
                # A new distinct ImageID beyond the limit. The CSV is
                # ImageID-contiguous, so every already-selected image is now
                # complete — stop scanning to stay memory bounded.
                done = True
                break
        if done:
            break

    image_ids = tuple(selected)
    frozen = {image_id: tuple(boxes) for image_id, boxes in selected.items()}
    return ScanResult(
        image_ids=image_ids,
        boxes_by_image=frozen,
        rows_read=rows_read,
        chunks_read=chunks_read,
        matched_rows=matched_rows,
    )


def _aws_command(image_id: str, dest_dir: Path) -> list[str]:
    """Build the ``aws s3`` argv to fetch one train image (no shell)."""
    return [
        "aws",
        "s3",
        "--no-sign-request",
        "--only-show-errors",
        "cp",
        f"s3://open-images-dataset/train/{image_id}.jpg",
        str(dest_dir / f"{image_id}.jpg"),
    ]


def download_images(
    image_ids: tuple[str, ...],
    *,
    dest_dir: Path,
    aws_path: str,
    env: dict[str, str],
) -> list[str]:
    """Download the selected images from the public Open Images S3 bucket.

    Uses the same anonymous ``s3 cp`` object layout as the vendored toolkit, one
    object at a time (no new threading model), so a partial download is reported
    honestly by the caller counting real files afterwards.

    Args:
        image_ids: The ImageIDs to fetch.
        dest_dir: Directory to write ``<ImageID>.jpg`` into (created if missing).
        aws_path: Resolved path to the ``aws`` executable.
        env: Environment for the subprocess (PATH includes the venv Scripts).

    Returns:
        The ImageIDs that landed on disk as readable files.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    for image_id in image_ids:
        argv = [aws_path, *_aws_command(image_id, dest_dir)[1:]]
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, capture_output=True, text=True, check=False, env=env
        )
        target = dest_dir / f"{image_id}.jpg"
        if target.is_file() and target.stat().st_size > 0:
            downloaded.append(image_id)
    return downloaded


def write_source_labels(
    scan: ScanResult,
    downloaded_ids: list[str],
    *,
    images_dir: Path,
    labels_dir: Path,
    source_class: str,
) -> int:
    """Write OIDv4-format source labels for every successfully downloaded image.

    The label format is exactly what the frozen converter consumes —
    ``<SourceClass> x1 y1 x2 y2`` in *pixels* — reconstructed from the retained
    normalised OID box and the real downloaded image's dimensions (identical to
    the vendored ``get_label`` math). Images that fail to open are skipped (no
    label), so staging only ever sees clean pairs.

    Args:
        scan: The scan result holding the retained normalised boxes.
        downloaded_ids: ImageIDs that actually downloaded.
        images_dir: Directory holding the downloaded ``<ImageID>.jpg`` files.
        labels_dir: Sibling ``Label/`` directory to write ``<ImageID>.txt`` into.
        source_class: The Open Images source class label (label line prefix).

    Returns:
        The number of label files written.
    """
    from PIL import Image, UnidentifiedImageError

    labels_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for image_id in downloaded_ids:
        boxes = scan.boxes_by_image.get(image_id, ())
        if not boxes:
            continue
        image_path = images_dir / f"{image_id}.jpg"
        try:
            with Image.open(image_path) as opened:
                opened.load()
                width, height = opened.width, opened.height
        except (OSError, UnidentifiedImageError, ValueError):
            continue
        lines = []
        for box in boxes:
            x1 = box.x_min * width
            y1 = box.y_min * height
            x2 = box.x_max * width
            y2 = box.y_max * height
            lines.append(f"{source_class} {x1} {y1} {x2} {y2}")
        (labels_dir / f"{image_id}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        written += 1
    return written


def _resolve_aws(toolkit_root: Path) -> tuple[str, dict[str, str]]:
    """Resolve the ``aws`` executable and subprocess env from the acquisition venv.

    Mirrors ``acquire_openimages_multiclass._toolkit_env`` /
    ``_aws_available``: prefers the dedicated ``dataset_acquisition/.venv``
    Scripts dir, falling back to ``PATH``.

    Args:
        toolkit_root: Root of the OIDv4_ToolKit (its ``.venv`` sibling holds aws).

    Returns:
        A ``(aws_path, environment)`` tuple.

    Raises:
        AcquisitionError: When ``aws`` cannot be resolved.
    """
    env = dict(os.environ)
    scripts_dir = toolkit_root.parent / ".venv" / "Scripts"
    if scripts_dir.is_dir():
        env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    for candidate in ("aws.cmd", "aws.exe", "aws"):
        resolved = scripts_dir / candidate
        if resolved.is_file():
            return str(resolved), env
    on_path = shutil.which("aws", path=env.get("PATH"))
    if on_path:
        return on_path, env
    raise AcquisitionError(
        "the AWS CLI ('aws') is required to fetch images from the "
        "open-images-dataset S3 bucket but was not found in the acquisition "
        "venv or on PATH"
    )


def lowmem_download(request: orch.DownloadRequest) -> orch.DownloadResult:
    """Drop-in low-memory replacement for ``real_download``.

    Mirrors ``acquire_openimages_multiclass.real_download`` exactly, but with a
    chunked annotation scan in place of the OOM-prone full read.

    Satisfies the orchestrator's :data:`~acquire_openimages_multiclass.DownloadFn`
    contract exactly: same request in, same
    :class:`~acquire_openimages_multiclass.DownloadResult` out, same on-disk
    layout (``OID/Dataset/train/<SourceClass>/`` + ``Label/``). The only
    difference from the vendored path is that the annotation scan is chunked and
    column-narrowed, so it never exhausts host memory.

    Args:
        request: The immutable download request from the orchestrator.

    Returns:
        A :class:`~acquire_openimages_multiclass.DownloadResult` describing what
        actually landed on disk (never a fabricated success).
    """
    images_root = (
        request.toolkit_root / "OID" / "Dataset" / "train" / request.open_images_class
    )
    labels_root = images_root / "Label"
    csv_dir = request.toolkit_root / "OID" / "csv_folder"
    bbox_csv = csv_dir / _TRAIN_BBOX_CSV
    descriptions_csv = csv_dir / _CLASS_DESCRIPTIONS_CSV

    try:
        aws_path, env = _resolve_aws(request.toolkit_root)
        class_mid = resolve_class_mid(descriptions_csv, request.open_images_class)
        scan = scan_class_annotations(
            bbox_csv, class_mid=class_mid, limit=request.limit
        )
    except AcquisitionError as exc:
        return orch.DownloadResult(
            ok=False,
            image_count=0,
            label_count=0,
            images_root=images_root,
            labels_root=labels_root,
            message=str(exc),
        )

    downloaded_ids = download_images(
        scan.image_ids, dest_dir=images_root, aws_path=aws_path, env=env
    )
    write_source_labels(
        scan,
        downloaded_ids,
        images_dir=images_root,
        labels_dir=labels_root,
        source_class=request.open_images_class,
    )

    image_count = _count_images(images_root)
    label_count = _count_files(labels_root, "*.txt")
    message = (
        ""
        if image_count > 0
        else (
            f"scanned {scan.matched_rows} matching annotation row(s) across "
            f"{scan.chunks_read} chunk(s); selected {len(scan.image_ids)} "
            "image(s) but none downloaded"
        )
    )
    return orch.DownloadResult(
        ok=True,
        image_count=image_count,
        label_count=label_count,
        images_root=images_root,
        labels_root=labels_root,
        message=message,
    )


def _count_images(root: Path) -> int:
    """Return the number of top-level source images under ``root``."""
    if not root.is_dir():
        return 0
    return sum(
        1
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in orch.conv._SOURCE_IMAGE_SUFFIXES
    )


def _count_files(root: Path, pattern: str) -> int:
    """Return the number of files matching ``pattern`` directly under ``root``."""
    if not root.is_dir():
        return 0
    return sum(1 for path in root.glob(pattern) if path.is_file())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments for the standalone scan/download entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Low-memory Open Images V7 acquisition adapter (P4.3.3). Streams the "
            "train bbox CSV in narrow, chunked reads to acquire one class without "
            "exhausting host memory, writing the same OIDv4 source layout the "
            "frozen converter consumes. Dataset v1.0 is not released."
        )
    )
    parser.add_argument(
        "--source-class",
        required=True,
        help="Open Images boxable display name to acquire (e.g. 'Printer').",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum distinct ImageIDs to acquire (default: 20).",
    )
    parser.add_argument(
        "--toolkit-root",
        type=Path,
        default=REPO_ROOT / "dataset_acquisition" / "OIDv4_ToolKit",
        help="Root of the OIDv4_ToolKit (holds OID/csv_folder and OID/Dataset).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=_DEFAULT_CHUNK_SIZE,
        help=f"Rows per CSV chunk (default: {_DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Scan + report the bounded ImageID selection without downloading.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for standalone low-memory scan/download of a single class.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 ok, 1 acquisition error, 2 usage error).
    """
    args = _parse_args(argv)
    if args.limit < 0:
        print("error: --limit must be >= 0", file=sys.stderr)
        return _EXIT_USAGE

    csv_dir = args.toolkit_root / "OID" / "csv_folder"
    bbox_csv = csv_dir / _TRAIN_BBOX_CSV
    descriptions_csv = csv_dir / _CLASS_DESCRIPTIONS_CSV

    try:
        class_mid = resolve_class_mid(descriptions_csv, args.source_class)
        scan = scan_class_annotations(
            bbox_csv,
            class_mid=class_mid,
            limit=args.limit,
            chunk_size=args.chunk_size,
        )
    except AcquisitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_FAILURES

    print(
        f"class '{args.source_class}' -> {class_mid}: selected "
        f"{len(scan.image_ids)}/{args.limit} image(s) from "
        f"{scan.matched_rows} matching row(s) over {scan.chunks_read} chunk(s)"
    )
    if args.scan_only:
        for image_id in scan.image_ids:
            print(image_id)
        return _EXIT_OK

    request = orch.DownloadRequest(
        open_images_class=args.source_class,
        limit=args.limit,
        toolkit_root=args.toolkit_root,
    )
    result = lowmem_download(request)
    print(
        f"downloaded {result.image_count} image(s), {result.label_count} label(s) "
        f"-> {result.images_root}"
    )
    if result.message:
        print(result.message, file=sys.stderr)
    return _EXIT_OK if result.ok else _EXIT_FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
