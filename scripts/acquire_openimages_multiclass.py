"""Batch, manifest-driven Open Images V7 -> EcoTrace acquisition (Sprint P4.3.1).

This is the **orchestration layer** for the remaining 18 EcoTrace device classes
(``laptop`` is the already-completed single-class pilot). It does *not* train a
model and it invents no conversion mathematics: it drives the **frozen** pilot
tooling for every class, one isolated per-class directory at a time.

Pipeline per class (each stage is kept strictly separate):

#. **Download** the class's Open Images V7 boxes through the existing
   ``OIDv4_ToolKit`` mechanism (injected, so unit tests never touch the network).
#. **Convert** the pixel-XYXY source into EcoTrace YOLO by calling the pilot
   converter's public API (:func:`convert_openimages_to_yolo.convert_dataset` +
   :func:`~convert_openimages_to_yolo.write_outputs`) — the conversion formulas,
   reject-never-clip rule and provenance are reused verbatim.
#. **Validate** the staged output with the frozen ``ImageValidator`` (Gate A) and
   the P4.2.2 annotation validator (Gate B); every count is read off real files.
#. Leave the result at **QA_PENDING**. Human QA is *not* performed here, so
   ``qa_accepted``/``qa_rejected`` are always ``0``; only a human may advance a
   class to ``QA_ACCEPTED``, and only ``QA_ACCEPTED`` data may ever become a
   Dataset v1.0 candidate. **Dataset v1.0 is not released.**

Design guarantees:

* **Taxonomy is dynamic.** The 19 classes and their ids come from
  :func:`device_ai.dataset.taxonomy.load_taxonomy`; nothing is hard-coded.
* **Source policy.** Open Images V7 is the only source. A class whose Open Images
  label cannot be mapped *safely* is marked ``UNMAPPED`` and **blocked** from
  canonical staging — the tool never guesses an ambiguous class.
* **No fabrication.** Requested/downloaded/converted/valid counts are derived
  from the filesystem and the tools' own reports. A download that yields zero
  images is reported as zero — never as a success.
* **Isolation + safety.** Each class writes only to its own
  ``dataset_acquisition/staging/openimages_<class>_v1`` directory; the tool
  refuses to touch the completed ``laptop`` pilot staging and never writes into
  ``intelligence/device_ai/datasets/``.
* **Resumable + deterministic.** A class whose staging already carries a
  provenance manifest is skipped (``ALREADY_ACQUIRED``) unless ``--force``; the
  only timestamp is injected via ``--created-at`` (the wall clock is never read).

Exit codes:
    0: every selected class succeeded (or ``--list`` / clean ``--dry-run``).
    1: at least one selected class failed to acquire (download failed/empty).
    2: usage error (bad arguments, invalid plan, or an invalid class mapping).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import convert_openimages_to_yolo as conv
import validate_annotations as ann
from _ecotrace_toolkit import REPO_ROOT

from device_ai.configs.settings import Settings
from device_ai.dataset.image_validation import ImageValidator
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_FAILURES = 1
_EXIT_USAGE = 2

# Repository anchors. Everything the orchestrator writes lives under
# ``dataset_acquisition/``; the frozen ``device_ai`` datasets dir is never used.
_ACQUISITION_ROOT = REPO_ROOT / "dataset_acquisition"
_DEFAULT_PLAN = (
    _ACQUISITION_ROOT / "manifests" / "p4_3_1_openimages_acquisition_plan.csv"
)
_DEFAULT_STAGING_ROOT = _ACQUISITION_ROOT / "staging"
_DEFAULT_REPORTS_ROOT = _ACQUISITION_ROOT / "reports"
_DEFAULT_STATUS_OUT = _DEFAULT_REPORTS_ROOT / "p4_3_1_run_report.json"
_TOOLKIT_ROOT = _ACQUISITION_ROOT / "OIDv4_ToolKit"

# The single source this sprint is allowed to use.
_APPROVED_SOURCE = "Open Images V7"

# Injected defaults (never the wall clock).
_DEFAULT_CREATED_AT = "2026-08-09T00:00:00+00:00"
_DEFAULT_RUN_LABEL = "p4_3_1"

# The completed pilot class is protected: the orchestrator refuses to acquire or
# overwrite it here, so its hand-reviewed canonical staging is never clobbered.
_PILOT_CLASS = "laptop"

# Mapping status vocabulary (mirrors the plan manifest's ``mapping_status``).
_MAP_MAPPED = "MAPPED"
_MAP_UNMAPPED = "UNMAPPED"

# Per-class acquisition state vocabulary (kept strictly separated). QA_ACCEPTED
# and QA_REJECTED are intentionally absent: only a human reviewer sets those.
_STATE_BLOCKED = "BLOCKED_UNMAPPED"
_STATE_ALREADY = "ALREADY_ACQUIRED"
_STATE_DRY_RUN = "DRY_RUN"
_STATE_DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
_STATE_DOWNLOAD_EMPTY = "DOWNLOAD_EMPTY"
_STATE_CONVERSION_FAILED = "CONVERSION_FAILED"
_STATE_QA_PENDING = "QA_PENDING"


class PlanError(Exception):
    """A fatal problem loading or validating the acquisition plan manifest."""


@dataclass(frozen=True, slots=True)
class PlanRow:
    """One declarative plan row: an EcoTrace class and its Open Images mapping.

    Attributes:
        class_id: The taxonomy class id declared in the plan (validated against
            the frozen taxonomy).
        ecotrace_class: The canonical EcoTrace class name.
        open_images_class: The Open Images V7 boxable label, or ``""`` when
            ``mapping_status`` is ``UNMAPPED``.
        mapping_status: ``MAPPED`` or ``UNMAPPED``.
        source: The declared source (must be the approved source when mapped).
        source_license: The recorded licence/provenance note (never a claim of
            redistribution rights).
        planned_min: Per-class minimum image target.
        planned_recommended: Per-class recommended image target.
        planned_ideal: Per-class ideal image target.
        notes: Free-text provenance/notes.
    """

    class_id: int
    ecotrace_class: str
    open_images_class: str
    mapping_status: str
    source: str
    source_license: str
    planned_min: int
    planned_recommended: int
    planned_ideal: int
    notes: str


@dataclass(frozen=True, slots=True)
class MappingIssue:
    """A validation problem with one plan row's class mapping.

    Attributes:
        ecotrace_class: The offending class name (or the raw cell when unknown).
        code: Stable machine-readable issue code.
        message: Human-readable description.
    """

    ecotrace_class: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """An immutable request to download one class from Open Images V7.

    Attributes:
        open_images_class: The Open Images boxable label to fetch.
        limit: Maximum number of images to request.
        toolkit_root: Root of the ``OIDv4_ToolKit`` download mechanism.
    """

    open_images_class: str
    limit: int
    toolkit_root: Path


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """The outcome of a download attempt (never fabricates a success).

    Attributes:
        ok: Whether the download mechanism ran without a fatal error. Zero
            images is still ``ok=True`` but yields a ``DOWNLOAD_EMPTY`` state.
        image_count: Real number of source image files present afterwards.
        label_count: Real number of source ``.txt`` labels present afterwards.
        images_root: Directory holding the downloaded images.
        labels_root: Sibling ``Label/`` directory holding the source labels.
        message: Human-readable detail (e.g. a blocker explanation).
    """

    ok: bool
    image_count: int
    label_count: int
    images_root: Path
    labels_root: Path
    message: str


# A download function takes a request and returns a result. The real one shells
# out to the OID toolkit; unit tests inject an offline fake.
DownloadFn = Callable[[DownloadRequest], DownloadResult]

# The vendored OIDv4_ToolKit downloader queries ``os.get_terminal_size()`` only to
# size a cosmetic separator and has no fallback when *both* stdio fds are pipes
# (the headless subprocess case here), so on Windows it crashes with WinError 6
# before any download. We launch its ``main.py`` through this tiny in-process
# shim, which patches that single fragile call to degrade gracefully and then
# runs the toolkit verbatim -- leaving the vendored (untracked) toolkit pristine.
# ``main.py`` reads its arguments from ``sys.argv``; the class name and limit
# arrive as real argv entries (indices 1 and 2), so labels with spaces are safe.
_HEADLESS_LAUNCHER = (
    "import os, sys, runpy\n"
    "_orig = os.get_terminal_size\n"
    "def _safe(fd=1):\n"
    "    try:\n"
    "        return _orig(fd)\n"
    "    except OSError:\n"
    "        return os.terminal_size((80, 24))\n"
    "os.get_terminal_size = _safe\n"
    "cls, lim = sys.argv[1], sys.argv[2]\n"
    "sys.argv = ['main.py', 'downloader', '--classes', cls,\n"
    "            '--type_csv', 'train', '--limit', lim, '-y']\n"
    "runpy.run_path('main.py', run_name='__main__')\n"
)


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    """The fully-resolved, machine-readable outcome for one class.

    Every count is derived from real files or a tool's own report — none are
    invented. ``qa_accepted``/``qa_rejected`` are always ``0`` because human QA
    is out of scope for this sprint.
    """

    class_id: int
    ecotrace_class: str
    open_images_class: str
    mapping_status: str
    state: str
    requested: int
    downloaded: int
    converted: int
    valid_images: int
    valid_annotations: int
    duplicates: int
    conversion_errors: int
    qa_pending: int
    qa_accepted: int
    qa_rejected: int
    staging_dir: str
    provenance_note: str
    messages: tuple[str, ...] = field(default=())


def _cell(row: dict[str, str], key: str) -> str:
    """Return a stripped CSV cell value, or ``""`` when absent/blank."""
    value = row.get(key)
    return value.strip() if value else ""


def _int_cell(row: dict[str, str], key: str) -> int:
    """Return an integer CSV cell value, raising :class:`PlanError` on garbage."""
    raw = _cell(row, key)
    try:
        return int(raw)
    except ValueError as exc:
        raise PlanError(f"column '{key}' is not an integer: {raw!r}") from exc


def load_plan(plan_path: Path) -> list[PlanRow]:
    """Load the acquisition plan manifest into typed rows.

    Args:
        plan_path: Path to ``p4_3_1_openimages_acquisition_plan.csv``. Lines
            beginning with ``#`` are treated as comments and skipped.

    Returns:
        The parsed plan rows in file order.

    Raises:
        PlanError: When the file is missing, empty, or a row is malformed.
    """
    if not plan_path.is_file():
        raise PlanError(f"acquisition plan not found: {plan_path}")
    text = plan_path.read_text(encoding="utf-8")
    data_lines = [line for line in text.splitlines() if not line.startswith("#")]
    reader = csv.DictReader(data_lines)
    rows: list[PlanRow] = []
    for raw in reader:
        rows.append(
            PlanRow(
                class_id=_int_cell(raw, "class_id"),
                ecotrace_class=_cell(raw, "ecotrace_class"),
                open_images_class=_cell(raw, "open_images_class"),
                mapping_status=_cell(raw, "mapping_status"),
                source=_cell(raw, "source"),
                source_license=_cell(raw, "source_license"),
                planned_min=_int_cell(raw, "planned_min"),
                planned_recommended=_int_cell(raw, "planned_recommended"),
                planned_ideal=_int_cell(raw, "planned_ideal"),
                notes=_cell(raw, "notes"),
            )
        )
    if not rows:
        raise PlanError(f"acquisition plan has no data rows: {plan_path}")
    return rows


def validate_plan(
    rows: Sequence[PlanRow], taxonomy: DeviceTaxonomy
) -> list[MappingIssue]:
    """Validate every plan row against the frozen taxonomy and source policy.

    Checks, per row: the ``(class_id, ecotrace_class)`` pair matches the frozen
    taxonomy; a ``MAPPED`` row names a non-empty Open Images class and the
    approved source; an ``UNMAPPED`` row leaves the Open Images class empty. The
    plan must also cover every taxonomy class exactly once.

    Args:
        rows: The parsed plan rows.
        taxonomy: The loaded EcoTrace taxonomy.

    Returns:
        Every mapping issue found, ordered by class id. Empty means valid.
    """
    issues: list[MappingIssue] = []
    seen: dict[str, int] = {}
    for row in rows:
        seen[row.ecotrace_class] = seen.get(row.ecotrace_class, 0) + 1
        expected = taxonomy.name_for(row.class_id) if _in_range(taxonomy, row) else None
        if expected is None:
            issues.append(
                MappingIssue(
                    row.ecotrace_class,
                    "CLASS_ID_OUT_OF_RANGE",
                    f"class_id {row.class_id} is outside the taxonomy",
                )
            )
        elif expected != row.ecotrace_class:
            issues.append(
                MappingIssue(
                    row.ecotrace_class,
                    "TAXONOMY_MISMATCH",
                    f"class_id {row.class_id} is '{expected}', not "
                    f"'{row.ecotrace_class}'",
                )
            )
        issues.extend(_validate_mapping_cells(row))

    for name, count in sorted(seen.items()):
        if count > 1:
            issues.append(
                MappingIssue(name, "DUPLICATE_CLASS", f"class appears {count} times")
            )
    for class_id in range(taxonomy.num_classes):
        name = taxonomy.name_for(class_id)
        if name not in seen:
            issues.append(
                MappingIssue(name, "MISSING_CLASS", "taxonomy class absent from plan")
            )
    issues.sort(key=lambda i: (i.ecotrace_class, i.code))
    return issues


def _in_range(taxonomy: DeviceTaxonomy, row: PlanRow) -> bool:
    """Return whether ``row.class_id`` is a valid taxonomy index."""
    return bool(0 <= row.class_id < taxonomy.num_classes)


def _validate_mapping_cells(row: PlanRow) -> list[MappingIssue]:
    """Validate a single row's mapping/source cells for internal consistency."""
    issues: list[MappingIssue] = []
    if row.mapping_status == _MAP_MAPPED:
        if not row.open_images_class:
            issues.append(
                MappingIssue(
                    row.ecotrace_class,
                    "MAPPED_WITHOUT_SOURCE_CLASS",
                    "MAPPED row must name an Open Images class",
                )
            )
        if row.source != _APPROVED_SOURCE:
            issues.append(
                MappingIssue(
                    row.ecotrace_class,
                    "UNAPPROVED_SOURCE",
                    f"source must be '{_APPROVED_SOURCE}', got '{row.source}'",
                )
            )
    elif row.mapping_status == _MAP_UNMAPPED:
        if row.open_images_class:
            issues.append(
                MappingIssue(
                    row.ecotrace_class,
                    "UNMAPPED_WITH_SOURCE_CLASS",
                    "UNMAPPED row must not name an Open Images class",
                )
            )
    else:
        issues.append(
            MappingIssue(
                row.ecotrace_class,
                "UNKNOWN_MAPPING_STATUS",
                f"mapping_status must be MAPPED or UNMAPPED, got "
                f"'{row.mapping_status}'",
            )
        )
    return issues


def _toolkit_env(toolkit_root: Path) -> tuple[str, dict[str, str]]:
    """Resolve the interpreter and environment for the OID download subprocess.

    The OIDv4_ToolKit needs ``cv2``/``pandas``/``awscli`` which live in the
    dedicated ``dataset_acquisition/.venv`` (a sibling of ``toolkit_root``), not
    in the ``device_ai`` venv that runs this orchestrator. When that venv is
    present its interpreter is used and its ``Scripts`` directory is prepended to
    ``PATH`` so the bundled ``aws`` binary resolves; otherwise the current
    interpreter and ambient ``PATH`` are used.

    Args:
        toolkit_root: Root of the OIDv4_ToolKit download mechanism.

    Returns:
        A ``(python_executable, environment)`` tuple for :func:`subprocess.run`.
    """
    env = dict(os.environ)
    scripts_dir = toolkit_root.parent / ".venv" / "Scripts"
    venv_python = scripts_dir / "python.exe"
    if venv_python.is_file():
        env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
        return str(venv_python), env
    return sys.executable, env


def _aws_available(scripts_dir: Path, env: dict[str, str]) -> bool:
    """Return whether the ``aws`` CLI is resolvable for the download subprocess."""
    if (scripts_dir / "aws.cmd").is_file() or (scripts_dir / "aws").is_file():
        return True
    return shutil.which("aws", path=env.get("PATH")) is not None


def real_download(request: DownloadRequest) -> DownloadResult:
    """Download one class via the ``OIDv4_ToolKit`` mechanism (network).

    Reuses the existing toolkit unchanged: it is invoked as a subprocess with the
    toolkit as the working directory (so its ``OID/`` cache and CSV files are
    reused) using the dedicated acquisition venv's interpreter. The image/label
    counts are read from the filesystem afterwards, so a partial or empty
    download is reported honestly rather than as a success.

    Args:
        request: The immutable download request.

    Returns:
        A :class:`DownloadResult` describing what actually landed on disk.
    """
    images_root = (
        request.toolkit_root / "OID" / "Dataset" / "train" / request.open_images_class
    )
    labels_root = images_root / "Label"
    python_exe, env = _toolkit_env(request.toolkit_root)
    scripts_dir = request.toolkit_root.parent / ".venv" / "Scripts"
    if not _aws_available(scripts_dir, env):
        return DownloadResult(
            ok=False,
            image_count=0,
            label_count=0,
            images_root=images_root,
            labels_root=labels_root,
            message=(
                "the AWS CLI ('aws') is required by OIDv4_ToolKit to fetch "
                "images from the open-images-dataset S3 bucket but was not found "
                "in the acquisition venv or on PATH"
            ),
        )
    cmd = [
        python_exe,
        "-c",
        _HEADLESS_LAUNCHER,
        request.open_images_class,
        str(request.limit),
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd,
            cwd=request.toolkit_root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        return DownloadResult(
            ok=False,
            image_count=0,
            label_count=0,
            images_root=images_root,
            labels_root=labels_root,
            message=f"failed to launch OIDv4_ToolKit: {exc}",
        )
    image_count = _count_images(images_root)
    label_count = _count_files(labels_root, "*.txt")
    ok = proc.returncode == 0 or image_count > 0
    message = "" if ok else (proc.stderr.strip() or "OIDv4_ToolKit exited non-zero")
    return DownloadResult(
        ok=ok,
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
        if path.is_file() and path.suffix.lower() in conv._SOURCE_IMAGE_SUFFIXES
    )


def _count_files(root: Path, pattern: str) -> int:
    """Return the number of files matching ``pattern`` directly under ``root``."""
    if not root.is_dir():
        return 0
    return sum(1 for path in root.glob(pattern) if path.is_file())


def staging_dir_for(ecotrace_class: str, staging_root: Path) -> Path:
    """Return the isolated per-class staging directory for a class."""
    return staging_root / f"openimages_{ecotrace_class}_v1"


def _count_valid(staging_root: Path, settings: Settings) -> tuple[int, int, int]:
    """Count valid images, valid annotations and duplicates in staged output.

    Reuses the frozen ``ImageValidator`` (Gate A, structural) and the P4.2.2
    annotation validator (Gate B) — no validation logic is re-implemented here.

    Args:
        staging_root: The per-class staging root holding ``images/`` + ``labels/``.
        settings: Injected application settings supplying the frozen thresholds.

    Returns:
        ``(valid_images, valid_annotations, duplicates)`` — all derived from the
        validators' own reports.
    """
    images_root = staging_root / "images"
    labels_root = staging_root / "labels"
    image_report = ImageValidator(settings).validate(images_root=images_root)
    bad_images = {issue.file for issue in image_report.issues}
    valid_images = image_report.total_images - len(bad_images)
    duplicates = len(image_report.duplicate_hashes)

    annotation_report = ann.validate(images_root=images_root, labels_root=labels_root)
    bad_labels = {issue.file for issue in annotation_report.issues}
    valid_annotations = annotation_report.total_labels - len(bad_labels)
    return valid_images, valid_annotations, duplicates


def acquire_class(
    row: PlanRow,
    *,
    limit: int,
    staging_root: Path,
    toolkit_root: Path,
    taxonomy: DeviceTaxonomy,
    settings: Settings,
    download_fn: DownloadFn,
    created_at: str,
    conversion_version: str,
    dry_run: bool,
    force: bool,
) -> AcquisitionOutcome:
    """Acquire one class end to end, returning a machine-readable outcome.

    The stages (download -> convert -> validate) are each guarded so a failure at
    any point yields an honest state and never a fabricated success. Unmapped
    classes and the completed pilot class are refused before any side effect.

    Args:
        row: The plan row for the class.
        limit: Maximum images to request for the class.
        staging_root: Base staging directory (per-class dirs live beneath it).
        toolkit_root: Root of the OID download mechanism.
        taxonomy: The loaded EcoTrace taxonomy.
        settings: Injected application settings (frozen thresholds).
        download_fn: The (injectable) download function.
        created_at: Injected ISO-8601 conversion timestamp.
        conversion_version: Conversion/version identifier recorded in provenance.
        dry_run: When True, plan only — no download/convert/validate side effects.
        force: When True, re-acquire even if staging already exists (never for
            the protected pilot class).

    Returns:
        The resolved :class:`AcquisitionOutcome`.
    """
    staging = staging_dir_for(row.ecotrace_class, staging_root)
    base = _base_outcome(row, staging, requested=limit)

    if row.mapping_status != _MAP_MAPPED or not row.open_images_class:
        return _with(
            base,
            state=_STATE_BLOCKED,
            messages=(
                f"'{row.ecotrace_class}' has no safe Open Images mapping; blocked "
                "from canonical staging",
            ),
        )
    if row.ecotrace_class == _PILOT_CLASS:
        return _with(
            base,
            state=_STATE_ALREADY,
            messages=(
                "the laptop pilot is already complete; its staging is protected "
                "and never overwritten by this tool",
            ),
        )
    if _is_already_acquired(staging) and not force:
        return _with(
            base,
            state=_STATE_ALREADY,
            messages=(
                f"staging '{_rel(staging)}' already has a provenance manifest; "
                "pass --force to re-acquire",
            ),
        )
    if dry_run:
        return _with(
            base,
            state=_STATE_DRY_RUN,
            messages=(
                f"would download up to {limit} '{row.open_images_class}' image(s) "
                f"and stage to '{_rel(staging)}'",
            ),
        )

    result = download_fn(
        DownloadRequest(
            open_images_class=row.open_images_class,
            limit=limit,
            toolkit_root=toolkit_root,
        )
    )
    if not result.ok:
        return _with(
            base,
            state=_STATE_DOWNLOAD_FAILED,
            messages=(f"download failed: {result.message}",),
        )
    if result.image_count == 0:
        return _with(
            base,
            state=_STATE_DOWNLOAD_EMPTY,
            downloaded=0,
            messages=("download produced zero images (no fabricated success)",),
        )
    return _convert_and_validate(
        base,
        row=row,
        result=result,
        staging=staging,
        taxonomy=taxonomy,
        settings=settings,
        created_at=created_at,
        conversion_version=conversion_version,
    )


def _convert_and_validate(
    base: AcquisitionOutcome,
    *,
    row: PlanRow,
    result: DownloadResult,
    staging: Path,
    taxonomy: DeviceTaxonomy,
    settings: Settings,
    created_at: str,
    conversion_version: str,
) -> AcquisitionOutcome:
    """Convert a downloaded class and validate the staged output.

    Args:
        base: The pre-filled base outcome (class + request context).
        row: The plan row for the class.
        result: The successful download result.
        staging: The per-class staging directory to write.
        taxonomy: The loaded EcoTrace taxonomy.
        settings: Injected application settings.
        created_at: Injected ISO-8601 conversion timestamp.
        conversion_version: Conversion/version identifier.

    Returns:
        A ``QA_PENDING`` (or ``CONVERSION_FAILED``) outcome with real counts.
    """
    source_to_canonical = {row.open_images_class: row.ecotrace_class}
    conversion = conv.convert_dataset(
        source_images_root=result.images_root,
        source_labels_root=result.labels_root,
        source_to_canonical=source_to_canonical,
        taxonomy=taxonomy,
        source_name=_APPROVED_SOURCE,
        conversion_version=conversion_version,
        conversion_timestamp=created_at,
    )
    conv.write_outputs(conversion, staging_root=staging)
    summary = conversion.report["summary"]
    assert isinstance(summary, dict)
    converted = int(summary["images_converted"])
    conversion_errors = int(summary["conversion_error_count"])

    if converted == 0:
        return _with(
            base,
            state=_STATE_CONVERSION_FAILED,
            downloaded=result.image_count,
            converted=0,
            conversion_errors=conversion_errors,
            staging_dir=_rel(staging),
            messages=(
                f"downloaded {result.image_count} image(s) but none converted "
                f"cleanly ({conversion_errors} error(s))",
            ),
        )

    valid_images, valid_annotations, duplicates = _count_valid(staging, settings)
    return _with(
        base,
        state=_STATE_QA_PENDING,
        downloaded=result.image_count,
        converted=converted,
        valid_images=valid_images,
        valid_annotations=valid_annotations,
        duplicates=duplicates,
        conversion_errors=conversion_errors,
        qa_pending=converted,
        staging_dir=_rel(staging),
        messages=(
            f"staged {converted} image(s) at '{_rel(staging)}'; awaiting human QA "
            "(never auto-approved)",
        ),
    )


def _base_outcome(
    row: PlanRow, staging: Path, *, requested: int
) -> AcquisitionOutcome:
    """Return a zeroed outcome pre-filled from a plan row."""
    return AcquisitionOutcome(
        class_id=row.class_id,
        ecotrace_class=row.ecotrace_class,
        open_images_class=row.open_images_class,
        mapping_status=row.mapping_status,
        state=_STATE_BLOCKED,
        requested=requested,
        downloaded=0,
        converted=0,
        valid_images=0,
        valid_annotations=0,
        duplicates=0,
        conversion_errors=0,
        qa_pending=0,
        qa_accepted=0,
        qa_rejected=0,
        staging_dir="",
        provenance_note=row.source_license,
        messages=(),
    )


def _with(base: AcquisitionOutcome, **changes: object) -> AcquisitionOutcome:
    """Return a copy of ``base`` with the given fields replaced."""
    data = asdict(base)
    data.update(changes)
    return AcquisitionOutcome(**data)  # type: ignore[arg-type]


def _is_already_acquired(staging: Path) -> bool:
    """Return whether a per-class staging already holds a provenance manifest."""
    return (staging / "provenance" / "provenance_manifest.json").is_file()


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repo root as POSIX, or its name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def select_rows(
    rows: Sequence[PlanRow],
    *,
    selected: Sequence[str] | None,
    select_all: bool,
) -> list[PlanRow]:
    """Resolve the CLI selectors into an ordered list of plan rows.

    Args:
        rows: All plan rows.
        selected: Explicit class names from ``--class``/``--classes`` (or None).
        select_all: Whether ``--all`` was given.

    Returns:
        The selected rows in taxonomy order.

    Raises:
        PlanError: When a requested class name is not present in the plan.
    """
    by_name = {row.ecotrace_class: row for row in rows}
    if select_all:
        return list(rows)
    chosen: list[PlanRow] = []
    for name in selected or ():
        if name not in by_name:
            raise PlanError(
                f"class '{name}' is not in the plan; run --list to see valid names"
            )
        chosen.append(by_name[name])
    return chosen


def build_status_payload(
    outcomes: Sequence[AcquisitionOutcome], *, context: dict[str, object]
) -> dict[str, object]:
    """Assemble the deterministic machine-readable run report.

    Args:
        outcomes: The per-class acquisition outcomes.
        context: Provenance context echoed into the report header.

    Returns:
        A primitive-only mapping suitable for ``json.dump`` (sorted keys).
    """
    by_state: dict[str, int] = {}
    for outcome in outcomes:
        by_state[outcome.state] = by_state.get(outcome.state, 0) + 1
    return {
        **context,
        "summary": {
            "classes_selected": len(outcomes),
            "by_state": dict(sorted(by_state.items())),
            "total_requested": sum(o.requested for o in outcomes),
            "total_downloaded": sum(o.downloaded for o in outcomes),
            "total_converted": sum(o.converted for o in outcomes),
            "total_valid_images": sum(o.valid_images for o in outcomes),
            "total_qa_pending": sum(o.qa_pending for o in outcomes),
            "total_qa_accepted": sum(o.qa_accepted for o in outcomes),
        },
        "classes": [_outcome_to_dict(o) for o in outcomes],
    }


def _outcome_to_dict(outcome: AcquisitionOutcome) -> dict[str, object]:
    """Convert an outcome to a JSON-serialisable dict (messages as a list)."""
    data = asdict(outcome)
    data["messages"] = list(outcome.messages)
    return data


def write_status(payload: dict[str, object], path: Path) -> None:
    """Write the run report as deterministic JSON (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _render_list(rows: Sequence[PlanRow], taxonomy: DeviceTaxonomy) -> str:
    """Render the human-readable ``--list`` table of classes and mappings."""
    lines = [
        f"EcoTrace taxonomy v{taxonomy.version} - {taxonomy.num_classes} classes",
        f"Approved source: {_APPROVED_SOURCE}",
        "",
        f"{'id':>2}  {'ecotrace_class':<14}  {'status':<8}  open_images_class",
        f"{'--':>2}  {'-' * 14:<14}  {'-' * 8:<8}  {'-' * 20}",
    ]
    mapped = 0
    for row in rows:
        if row.mapping_status == _MAP_MAPPED:
            mapped += 1
        source = row.open_images_class or "(none - blocked)"
        lines.append(
            f"{row.class_id:>2}  {row.ecotrace_class:<14}  "
            f"{row.mapping_status:<8}  {source}"
        )
    lines.extend(
        [
            "",
            f"{mapped} MAPPED, {len(rows) - mapped} UNMAPPED (blocked). "
            "Dataset v1.0 is not released.",
        ]
    )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Batch, manifest-driven Open Images V7 -> EcoTrace acquisition "
            "orchestration (P4.3.1). Reuses the frozen pilot converter and "
            "validators; writes only to dataset_acquisition/staging. Human QA "
            "stays pending and Dataset v1.0 is not released."
        )
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--list",
        action="store_true",
        help="List the taxonomy classes and their Open Images mapping, then exit.",
    )
    selector.add_argument(
        "--class",
        dest="single_class",
        metavar="CLASS",
        help="Acquire a single EcoTrace class by name.",
    )
    selector.add_argument(
        "--classes",
        nargs="+",
        metavar="CLASS",
        help="Acquire several EcoTrace classes by name.",
    )
    selector.add_argument(
        "--all",
        action="store_true",
        help="Acquire every MAPPED class (UNMAPPED and the pilot are skipped).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum images to request per class (default: 20).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the plan and show what would happen; no downloads.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-acquire even if a class's staging already exists (never laptop).",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=_DEFAULT_PLAN,
        help="Path to the acquisition plan manifest CSV.",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=_DEFAULT_STAGING_ROOT,
        help="Base staging directory (per-class dirs are created beneath it).",
    )
    parser.add_argument(
        "--toolkit-root",
        type=Path,
        default=_TOOLKIT_ROOT,
        help="Root of the OIDv4_ToolKit download mechanism.",
    )
    parser.add_argument(
        "--status-out",
        type=Path,
        default=_DEFAULT_STATUS_OUT,
        help="Path to write the machine-readable JSON run report.",
    )
    parser.add_argument(
        "--conversion-version",
        default="openimages-multiclass-v1",
        help="Conversion/version identifier recorded in provenance.",
    )
    parser.add_argument(
        "--created-at",
        default=_DEFAULT_CREATED_AT,
        help="Injected ISO-8601 conversion timestamp (the clock is never read).",
    )
    parser.add_argument(
        "--run-label",
        default=_DEFAULT_RUN_LABEL,
        help="Free-text run label recorded in the report header.",
    )
    return parser.parse_args(argv)


def _validate_staging_root(staging_root: Path) -> str | None:
    """Return an error string if the staging root is an unsafe location."""
    resolved = staging_root.resolve()
    forbidden = (REPO_ROOT / "intelligence" / "device_ai" / "datasets").resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        return (
            "refusing to stage into the frozen device_ai datasets directory; "
            "use dataset_acquisition/staging"
        )
    return None


def _selectors_given(args: argparse.Namespace) -> bool:
    """Return whether any acquisition selector was supplied."""
    return bool(args.single_class or args.classes or args.all)


def run(args: argparse.Namespace, *, download_fn: DownloadFn = real_download) -> int:
    """Execute the orchestration for parsed ``args``.

    Args:
        args: Parsed command-line arguments.
        download_fn: The (injectable) download function; defaults to the real
            OID subprocess runner.

    Returns:
        A process exit code (0 ok, 1 acquisition failures, 2 usage error).
    """
    taxonomy = load_taxonomy()
    try:
        rows = load_plan(args.plan)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    mapping_issues = validate_plan(rows, taxonomy)
    if mapping_issues:
        print("error: acquisition plan is invalid:", file=sys.stderr)
        for issue in mapping_issues:
            print(
                f"  - {issue.ecotrace_class}: {issue.code}: {issue.message}",
                file=sys.stderr,
            )
        return _EXIT_USAGE

    if args.list:
        print(_render_list(rows, taxonomy))
        return _EXIT_OK

    if not _selectors_given(args):
        print(
            "error: choose one of --list, --class, --classes or --all",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    staging_error = _validate_staging_root(args.staging_root)
    if staging_error is not None:
        print(f"error: {staging_error}", file=sys.stderr)
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.created_at)
    except ValueError:
        print(
            f"error: --created-at is not valid ISO-8601: {args.created_at}",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    try:
        selected_names = (
            [args.single_class] if args.single_class else args.classes
        )
        targets = select_rows(
            rows, selected=selected_names, select_all=args.all
        )
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    settings = Settings()
    outcomes = [
        acquire_class(
            row,
            limit=args.limit,
            staging_root=args.staging_root,
            toolkit_root=args.toolkit_root,
            taxonomy=taxonomy,
            settings=settings,
            download_fn=download_fn,
            created_at=args.created_at,
            conversion_version=args.conversion_version,
            dry_run=args.dry_run,
            force=args.force,
        )
        for row in targets
    ]

    context: dict[str, object] = {
        "run_label": args.run_label,
        "source": _APPROVED_SOURCE,
        "taxonomy_version": taxonomy.version,
        "limit_per_class": args.limit,
        "dry_run": args.dry_run,
        "created_at": args.created_at,
        "conversion_version": args.conversion_version,
        "is_dataset_v1": False,
        "is_released": False,
    }
    payload = build_status_payload(outcomes, context=context)
    write_status(payload, args.status_out)

    print(json.dumps(payload, indent=2, sort_keys=True))
    print(
        f"processed {len(outcomes)} class(es) -> {_rel(args.status_out)}",
        file=sys.stderr,
    )
    failed = {
        _STATE_DOWNLOAD_FAILED,
        _STATE_DOWNLOAD_EMPTY,
        _STATE_CONVERSION_FAILED,
    }
    return _EXIT_FAILURES if any(o.state in failed for o in outcomes) else _EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point for the multi-class acquisition orchestrator.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 ok, 1 acquisition failures, 2 usage error).
    """
    return run(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
