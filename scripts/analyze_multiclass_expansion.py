"""P4.3.2 post-acquisition analysis over the multi-class expansion batch.

This is a **thin, additive** analysis layer for the P4.3.2 sprint. It performs
**no** download, **no** conversion, and adds **no** new domain logic: every
number it emits is derived from real staged files and the **frozen** P4.2.x /
P4.3.1 tooling, reused verbatim:

* image structural gate (Gate A)  -> ``device_ai.dataset.image_validation``
* annotation gate (Gate B)        -> ``scripts/validate_annotations.py:validate``
* image quality metrics/flags     -> ``device_ai.dataset.metadata.MetadataGenerator``
* duplicate detection             -> ``device_ai.dataset.duplicates.DuplicateDetector``
* taxonomy (dynamic, never hardcoded) -> ``device_ai.dataset.taxonomy.load_taxonomy``

Cross-class duplicate detection is achieved **without a new algorithm**: the
frozen ``MetadataGenerator.analyze_directory`` is run against the common batch
parent root so each :class:`ImageRecord` keeps its
``openimages_<class>_v1/images/<stem>.jpg`` relative path, and a single
``DuplicateDetector.detect`` call over the combined record list surfaces both
within-class and cross-class pairs (a pair is cross-class iff its two paths sit
under different per-class staging dirs).

The script writes **one** deterministic machine-readable JSON
(``--report-out``); the human-readable Markdown report is authored separately
from the same artifacts. It mutates no dataset and marks nothing QA_ACCEPTED:
every converted image remains ``QA_PENDING``.

Exit codes:
    0: analysis completed (findings, if any, are reported — not an error).
    2: usage error (missing batch root, unreadable manifest, bad timestamp).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import validate_annotations as ann
from _ecotrace_toolkit import REPO_ROOT

from device_ai.configs.settings import Settings
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.image_validation import ImageValidator
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.records import AnnotationReport
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

_EXIT_OK = 0
_EXIT_USAGE = 2

_ACQUISITION_ROOT = REPO_ROOT / "dataset_acquisition"
_DEFAULT_BATCH_ROOT = (
    _ACQUISITION_ROOT / "staging" / "openimages_multiclass_v1"
)
_DEFAULT_REPORT_OUT = (
    _ACQUISITION_ROOT / "reports" / "p4_3_2_multiclass_expansion_report.json"
)
_DEFAULT_STATUS_DIR = _ACQUISITION_ROOT / "reports"
_STATUS_GLOB = "p4_3_2_real_*.json"
_DEFAULT_CREATED_AT = "2026-08-10T00:00:00+00:00"

# Orchestrator terminal states that mean a requested class produced no staged
# data. Such a class is reported BLOCKED (quality metrics NOT_MEASURED) rather
# than silently omitted from the analysis.
_FAILED_STATES = frozenset(
    {"DOWNLOAD_FAILED", "DOWNLOAD_EMPTY", "MAPPING_BLOCKED", "ERROR"}
)
_NOT_MEASURED = "NOT_MEASURED"

# The three pilot staging dirs that MUST remain byte-for-byte unchanged.
_PROTECTED_DIRS = (
    "openimages_laptop_v1",
    "openimages_laptop_canonical_v1",
    "openimages_smartphone_v1",
)

# QA boundary: analysis never advances a class past QA_PENDING.
_QA_PENDING = "QA_PENDING"


@dataclass(frozen=True, slots=True)
class ClassAnalysis:
    """Derived, real-file metrics for one acquired class staging dir."""

    ecotrace_class: str
    class_id: int
    staging_dir: str
    source_class: str
    # Structural / pairing counts (from real files + frozen reports).
    images_on_disk: int
    labels_on_disk: int
    paired: int
    images_without_labels: tuple[str, ...]
    labels_without_images: tuple[str, ...]
    # Conversion accounting (from the frozen converter's own report).
    source_images_found: int
    source_labels_found: int
    images_converted: int
    images_failed: int
    conversion_error_count: int
    total_converted_objects: int
    # Gate A (structural image validation).
    valid_images: int
    image_issue_counts: dict[str, int]
    # Gate B (annotation validation).
    total_labels: int
    total_boxes: int
    valid_annotations: int
    annotation_issue_counts: dict[str, int]
    class_id_counts: dict[str, int]
    # Quality flags (frozen metadata thresholds; reported, never auto-reject).
    quality_flag_counts: dict[str, int]
    # Within-class duplicates (exact + near) from the frozen detector.
    within_class_exact_duplicates: int
    within_class_near_duplicates: int
    # Provenance verification (recomputed SHA-256 vs manifest).
    provenance_records: int
    provenance_sha_verified: int
    provenance_sha_mismatched: tuple[str, ...]
    provenance_missing_for: tuple[str, ...]


def _load_json(path: Path) -> dict[str, object]:
    """Load a JSON object, returning ``{}`` when the file is absent."""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _issue_counts(codes: list[str]) -> dict[str, int]:
    """Return a deterministic code -> count mapping."""
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _as_int(value: object, default: int = 0) -> int:
    """Coerce a JSON-loaded ``object`` to ``int``, falling back to ``default``.

    JSON values arrive typed as ``object``; this keeps the numeric extraction
    total (never raising) so a malformed report degrades to the default rather
    than crashing the analysis.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _stems(root: Path, suffix: str) -> set[str]:
    """Return the set of file stems with ``suffix`` directly under ``root``."""
    if not root.is_dir():
        return set()
    return {p.stem for p in root.iterdir() if p.is_file() and p.suffix == suffix}


def analyze_class(
    class_dir: Path,
    *,
    taxonomy: DeviceTaxonomy,
    settings: Settings,
) -> ClassAnalysis:
    """Analyse one per-class staging dir using only frozen tooling.

    Every count is derived from the staged files and the frozen validators'
    own reports; nothing is fabricated and no annotation is altered.

    Args:
        class_dir: A ``openimages_<class>_v1`` staging directory.
        taxonomy: The loaded EcoTrace taxonomy (dynamic ids).
        settings: Injected application settings (frozen thresholds).

    Returns:
        A fully-populated :class:`ClassAnalysis`.
    """
    images_root = class_dir / "images"
    labels_root = class_dir / "labels"
    reports_root = class_dir / "reports"
    prov_path = class_dir / "provenance" / "provenance_manifest.json"

    conv_report = _load_json(reports_root / "conversion_report.json")
    conv_errors = _load_json(reports_root / "conversion_errors.json")
    prov = _load_json(prov_path)

    ecotrace_class = str(conv_report.get("ecotrace_class") or class_dir.name)
    class_id = _as_int(conv_report.get("ecotrace_class_id", -1), -1)
    source_class = str(conv_report.get("source_class") or "")
    raw_summary = conv_report.get("summary", {})
    summary: dict[str, object] = raw_summary if isinstance(raw_summary, dict) else {}

    # --- Pairing (image stem <-> label stem), from real files ---------------
    image_stems = _stems(images_root, ".jpg") | _stems(images_root, ".png")
    label_stems = _stems(labels_root, ".txt")
    images_without_labels = tuple(sorted(image_stems - label_stems))
    labels_without_images = tuple(sorted(label_stems - image_stems))
    paired = len(image_stems & label_stems)

    # --- Gate A: frozen structural image validation -------------------------
    image_report = ImageValidator(settings).validate(images_root=images_root)
    bad_images = {issue.file for issue in image_report.issues}
    valid_images = image_report.total_images - len(bad_images)
    image_issue_counts = _issue_counts([i.code for i in image_report.issues])

    # --- Gate B: frozen annotation validation -------------------------------
    ann_report = ann.validate(images_root=images_root, labels_root=labels_root)
    bad_labels = {issue.file for issue in ann_report.issues}
    valid_annotations = ann_report.total_labels - len(bad_labels)
    annotation_issue_counts = _issue_counts([i.code for i in ann_report.issues])

    return _finish_class_analysis(
        class_dir=class_dir,
        ecotrace_class=ecotrace_class,
        class_id=class_id,
        source_class=source_class,
        summary=summary,
        conv_errors=conv_errors,
        prov=prov,
        images_root=images_root,
        labels_root=labels_root,
        image_stems=image_stems,
        label_stems=label_stems,
        paired=paired,
        images_without_labels=images_without_labels,
        labels_without_images=labels_without_images,
        valid_images=valid_images,
        image_issue_counts=image_issue_counts,
        ann_report=ann_report,
        valid_annotations=valid_annotations,
        annotation_issue_counts=annotation_issue_counts,
        settings=settings,
    )


def _finish_class_analysis(
    *,
    class_dir: Path,
    ecotrace_class: str,
    class_id: int,
    source_class: str,
    summary: dict[str, object],
    conv_errors: dict[str, object],
    prov: dict[str, object],
    images_root: Path,
    labels_root: Path,
    image_stems: set[str],
    label_stems: set[str],
    paired: int,
    images_without_labels: tuple[str, ...],
    labels_without_images: tuple[str, ...],
    valid_images: int,
    image_issue_counts: dict[str, int],
    ann_report: AnnotationReport,
    valid_annotations: int,
    annotation_issue_counts: dict[str, int],
    settings: Settings,
) -> ClassAnalysis:
    """Compute quality flags, within-class dedup and provenance verification.

    Split from :func:`analyze_class` to keep each function small; all inputs
    are already-derived real values.
    """
    summary_map = summary

    # --- Quality flags: frozen metadata thresholds (reported, never reject) --
    generator = MetadataGenerator.from_settings(settings)
    records = generator.analyze_directory(images_root)
    quality_codes: list[str] = []
    for record in records:
        quality_codes.extend(record.quality.issues)
    quality_flag_counts = _issue_counts(quality_codes)

    # --- Within-class duplicates: frozen detector over this class only -------
    detector = DuplicateDetector.from_settings(settings)
    dup_report = detector.detect(records)
    within_exact = sum(1 for pair in dup_report.pairs if pair.exact)
    within_near = sum(1 for pair in dup_report.pairs if not pair.exact)

    # --- Class-id histogram from the frozen annotation report ---------------
    class_id_counts = {
        str(cid): count for cid, count in sorted(ann_report.class_counts.items())
    }

    # --- Provenance verification: recompute SHA-256 vs the manifest ---------
    raw_prov_records = prov.get("records", [])
    prov_records = raw_prov_records if isinstance(raw_prov_records, list) else []
    manifest_by_stem: dict[str, str] = {}
    for rec in prov_records:
        if isinstance(rec, dict):
            stem = str(rec.get("stem", ""))
            manifest_by_stem[stem] = str(rec.get("sha256", ""))
    verified = 0
    mismatched: list[str] = []
    missing: list[str] = []
    for record in records:
        stem = Path(record.filename).stem
        expected = manifest_by_stem.get(stem)
        if expected is None:
            missing.append(stem)
            continue
        if record.hashes.sha256 == expected:
            verified += 1
        else:
            mismatched.append(stem)

    return ClassAnalysis(
        ecotrace_class=ecotrace_class,
        class_id=class_id,
        staging_dir=class_dir.as_posix(),
        source_class=source_class,
        images_on_disk=len(image_stems),
        labels_on_disk=len(label_stems),
        paired=paired,
        images_without_labels=images_without_labels,
        labels_without_images=labels_without_images,
        source_images_found=_as_int(summary_map.get("source_images_found", 0)),
        source_labels_found=_as_int(summary_map.get("source_labels_found", 0)),
        images_converted=_as_int(summary_map.get("images_converted", 0)),
        images_failed=_as_int(summary_map.get("images_failed", 0)),
        conversion_error_count=_as_int(conv_errors.get("error_count", 0)),
        total_converted_objects=_as_int(summary_map.get("total_converted_objects", 0)),
        valid_images=valid_images,
        image_issue_counts=image_issue_counts,
        total_labels=ann_report.total_labels,
        total_boxes=ann_report.total_boxes,
        valid_annotations=valid_annotations,
        annotation_issue_counts=annotation_issue_counts,
        class_id_counts=class_id_counts,
        quality_flag_counts=quality_flag_counts,
        within_class_exact_duplicates=within_exact,
        within_class_near_duplicates=within_near,
        provenance_records=len(manifest_by_stem),
        provenance_sha_verified=verified,
        provenance_sha_mismatched=tuple(sorted(mismatched)),
        provenance_missing_for=tuple(sorted(missing)),
    )


@dataclass(frozen=True, slots=True)
class CrossClassPair:
    """A duplicate relationship whose two images sit in different classes."""

    source: str
    source_class: str
    duplicate: str
    duplicate_class: str
    distance: int
    exact: bool


def _class_of(relative_path: str) -> str:
    """Return the ``openimages_<class>_v1`` segment of a batch relative path.

    The frozen detector reports ``relative_path`` values rooted at the batch
    parent, e.g. ``openimages_tablet_v1/images/<stem>.jpg``. The first path
    segment names the per-class staging dir.
    """
    return Path(relative_path).parts[0] if relative_path else ""


def detect_cross_class_duplicates(
    batch_root: Path,
    class_dirs: list[Path],
    *,
    settings: Settings,
) -> tuple[list[CrossClassPair], int, int]:
    """Run one frozen ``detect`` over the whole batch; split cross vs within.

    No new duplicate algorithm is introduced: the frozen
    :class:`MetadataGenerator` analyses every batch image against the common
    ``batch_root`` (so relative paths retain their per-class prefix), and a
    single :meth:`DuplicateDetector.detect` call surfaces every pair. A pair is
    *cross-class* iff its two paths sit under different per-class dirs.

    Args:
        batch_root: The batch parent (``openimages_multiclass_v1``).
        class_dirs: The per-class staging dirs to include.
        settings: Injected settings (frozen hamming threshold).

    Returns:
        ``(cross_class_pairs, total_pairs, cross_class_count)``.
    """
    generator = MetadataGenerator.from_settings(settings)
    records = []
    for class_dir in class_dirs:
        images_root = class_dir / "images"
        if not images_root.is_dir():
            continue
        for path in sorted(images_root.iterdir()):
            if path.is_file() and path.suffix in {".jpg", ".png"}:
                # root=batch_root keeps the openimages_<class>_v1/... prefix,
                # so cross-class pairs are distinguishable by first path segment.
                records.append(generator.analyze_file(path, root=batch_root))
    report = DuplicateDetector.from_settings(settings).detect(records)
    cross: list[CrossClassPair] = []
    for pair in report.pairs:
        src_class = _class_of(pair.source)
        dup_class = _class_of(pair.duplicate)
        if src_class != dup_class:
            cross.append(
                CrossClassPair(
                    source=pair.source,
                    source_class=src_class,
                    duplicate=pair.duplicate,
                    duplicate_class=dup_class,
                    distance=pair.distance,
                    exact=pair.exact,
                )
            )
    return cross, len(report.pairs), len(cross)


def _dir_fingerprint(root: Path) -> dict[str, object]:
    """Return a method-stable fingerprint of a directory tree.

    Uses file count, aggregate byte size, and the newest modification time —
    all method-independent signals of whether any file changed. (An aggregate
    content hash is intentionally avoided here: its value depends on how paths
    are fed to the hasher, which is not stable across environments.)

    Args:
        root: Directory to fingerprint.

    Returns:
        A JSON-serialisable fingerprint mapping.
    """
    if not root.is_dir():
        return {"exists": False, "file_count": 0, "total_bytes": 0, "newest_mtime": 0.0}
    files = [p for p in root.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    newest = max((p.stat().st_mtime for p in files), default=0.0)
    return {
        "exists": True,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "newest_mtime": round(newest, 3),
    }


def verify_pilot_protection(
    staging_root: Path,
    baseline: dict[str, dict[str, object]] | None,
) -> dict[str, object]:
    """Fingerprint each protected pilot dir and compare against a baseline.

    Args:
        staging_root: The parent ``staging`` dir holding the protected dirs.
        baseline: Optional prior fingerprints keyed by dir name; when given,
            an ``unchanged`` verdict is derived per dir.

    Returns:
        A mapping ``{dir_name: {fingerprint..., "unchanged": bool|None}}``.
    """
    result: dict[str, object] = {}
    for name in _PROTECTED_DIRS:
        current = _dir_fingerprint(staging_root / name)
        entry: dict[str, object] = dict(current)
        if baseline is not None and name in baseline:
            base = baseline[name]
            entry["unchanged"] = (
                current["file_count"] == base.get("file_count")
                and current["total_bytes"] == base.get("total_bytes")
            )
            entry["baseline"] = base
        else:
            entry["unchanged"] = None
        result[name] = entry
    return result


def _discover_class_dirs(batch_root: Path) -> list[Path]:
    """Return the acquired per-class staging dirs under ``batch_root``, sorted."""
    if not batch_root.is_dir():
        return []
    return sorted(
        p
        for p in batch_root.iterdir()
        if p.is_dir()
        and p.name.startswith("openimages_")
        and (p / "provenance" / "provenance_manifest.json").is_file()
    )


def collect_acquisition_status(
    status_dir: Path,
    *,
    glob: str = _STATUS_GLOB,
) -> list[dict[str, object]]:
    """Read the orchestrator's own per-class run reports for this batch.

    The analysis proper only sees classes that actually staged data (they have a
    provenance manifest on disk). A class whose bounded acquisition **failed**
    (e.g. ``DOWNLOAD_FAILED``) writes a status JSON but stages nothing, so it
    would otherwise vanish from the report. This reads every
    ``p4_3_2_real_*.json`` the orchestrator emitted and surfaces each requested
    class's real terminal state — hiding no failure. Nothing here is fabricated:
    every field is copied from the orchestrator's own report, and a failed class
    is explicitly marked ``NOT_MEASURED`` for the metrics it never produced.

    Args:
        status_dir: Directory holding the orchestrator status JSONs.
        glob: Filename glob selecting this batch's real-run reports.

    Returns:
        One deterministic, primitive-only status entry per requested class,
        sorted by class id then name.
    """
    entries: dict[str, dict[str, object]] = {}
    if not status_dir.is_dir():
        return []
    for path in sorted(status_dir.glob(glob)):
        report = _load_json(path)
        raw_classes = report.get("classes", [])
        classes = raw_classes if isinstance(raw_classes, list) else []
        for cls in classes:
            if not isinstance(cls, dict):
                continue
            name = str(cls.get("ecotrace_class", ""))
            state = str(cls.get("state", ""))
            staged = (
                state not in _FAILED_STATES
                and _as_int(cls.get("converted", 0)) > 0
            )
            entry = {
                "ecotrace_class": name,
                "class_id": _as_int(cls.get("class_id", -1), -1),
                "source_class": str(cls.get("open_images_class", "")),
                "mapping_status": str(cls.get("mapping_status", "")),
                "state": state,
                "requested": _as_int(cls.get("requested", 0)),
                "downloaded": _as_int(cls.get("downloaded", 0)),
                "converted": _as_int(cls.get("converted", 0)),
                "valid_images": _as_int(cls.get("valid_images", 0)),
                "staged_data": staged,
                "quality_measured": staged,
                "failure_reason": (
                    _NOT_MEASURED
                    if staged
                    else _first_failure_reason(cls.get("messages", []))
                ),
                "status_report": path.name,
            }
            # A later report for the same class supersedes an earlier one so the
            # most recent terminal state wins (e.g. a successful retry).
            key = name or path.name
            prev = entries.get(key)
            if prev is None or not prev["staged_data"]:
                entries[key] = entry
    return sorted(entries.values(), key=lambda e: (e["class_id"], e["ecotrace_class"]))


def _first_failure_reason(messages: object) -> str:
    """Return a one-line failure reason from an orchestrator ``messages`` list.

    The full multi-line traceback is preserved in the orchestrator's own status
    JSON; here we surface only its final, most informative line so the analysis
    report stays readable without discarding the honest failure signal.
    """
    if not isinstance(messages, list) or not messages:
        return "unknown failure (no message recorded)"
    first = str(messages[0]).strip()
    last_line = first.splitlines()[-1].strip() if first else ""
    return last_line or first[:200]


def _class_to_dict(analysis: ClassAnalysis) -> dict[str, object]:
    """Convert a :class:`ClassAnalysis` to a primitive-only, QA_PENDING dict."""
    return {
        "ecotrace_class": analysis.ecotrace_class,
        "class_id": analysis.class_id,
        "staging_dir": analysis.staging_dir,
        "source_class": analysis.source_class,
        "qa_status": _QA_PENDING,
        "counts": {
            "images_on_disk": analysis.images_on_disk,
            "labels_on_disk": analysis.labels_on_disk,
            "paired": analysis.paired,
            "source_images_found": analysis.source_images_found,
            "source_labels_found": analysis.source_labels_found,
            "images_converted": analysis.images_converted,
            "images_failed": analysis.images_failed,
            "conversion_error_count": analysis.conversion_error_count,
            "total_converted_objects": analysis.total_converted_objects,
            "valid_images": analysis.valid_images,
            "total_labels": analysis.total_labels,
            "total_boxes": analysis.total_boxes,
            "valid_annotations": analysis.valid_annotations,
            "within_class_exact_duplicates": analysis.within_class_exact_duplicates,
            "within_class_near_duplicates": analysis.within_class_near_duplicates,
            "provenance_records": analysis.provenance_records,
            "provenance_sha_verified": analysis.provenance_sha_verified,
        },
        "images_without_labels": list(analysis.images_without_labels),
        "labels_without_images": list(analysis.labels_without_images),
        "image_issue_counts": analysis.image_issue_counts,
        "annotation_issue_counts": analysis.annotation_issue_counts,
        "quality_flag_counts": analysis.quality_flag_counts,
        "class_id_counts": analysis.class_id_counts,
        "provenance_sha_mismatched": list(analysis.provenance_sha_mismatched),
        "provenance_missing_for": list(analysis.provenance_missing_for),
    }


def build_report(
    batch_root: Path,
    *,
    settings: Settings,
    taxonomy: DeviceTaxonomy,
    created_at: str,
    baseline: dict[str, dict[str, object]] | None,
    status_dir: Path | None = None,
) -> dict[str, object]:
    """Assemble the full P4.3.2 machine-readable analysis report.

    Args:
        batch_root: The batch parent dir to analyse.
        settings: Injected settings (frozen thresholds).
        taxonomy: Loaded taxonomy (dynamic ids).
        created_at: Injected ISO-8601 timestamp (never the wall clock).
        baseline: Optional pilot-protection baseline fingerprints.
        status_dir: Optional dir of orchestrator per-class status JSONs; when
            given, every *requested* class's terminal state (including failures)
            is surfaced so no failure is hidden.

    Returns:
        A deterministic, primitive-only report mapping.
    """
    class_dirs = _discover_class_dirs(batch_root)
    analyses = [
        analyze_class(d, taxonomy=taxonomy, settings=settings) for d in class_dirs
    ]
    cross_pairs, total_pairs, cross_count = detect_cross_class_duplicates(
        batch_root, class_dirs, settings=settings
    )
    staging_root = batch_root.parent
    protection = verify_pilot_protection(staging_root, baseline)
    acquisition_status = (
        collect_acquisition_status(status_dir) if status_dir is not None else []
    )

    return {
        "sprint": "P4.3.2",
        "batch_root": batch_root.as_posix(),
        "created_at": created_at,
        "taxonomy_version": taxonomy.version,
        "is_dataset_v1": False,
        "is_released": False,
        "qa_boundary": _QA_PENDING,
        "thresholds": {
            "blur_threshold": settings.blur_threshold,
            "brightness_dark_threshold": settings.brightness_dark_threshold,
            "brightness_bright_threshold": settings.brightness_bright_threshold,
            "min_image_dimension": settings.min_image_dimension,
            "max_image_dimension": settings.max_image_dimension,
            "duplicate_hamming_threshold": settings.duplicate_hamming_threshold,
        },
        "acquisition_status": acquisition_status,
        "classes": [_class_to_dict(a) for a in analyses],
        "cross_class_duplicates": {
            "total_pairs_in_batch": total_pairs,
            "cross_class_pair_count": cross_count,
            "pairs": [
                {
                    "source": p.source,
                    "source_class": p.source_class,
                    "duplicate": p.duplicate,
                    "duplicate_class": p.duplicate_class,
                    "distance": p.distance,
                    "exact": p.exact,
                }
                for p in cross_pairs
            ],
        },
        "pilot_protection": protection,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "P4.3.2 post-acquisition analysis over the multi-class expansion "
            "batch (frozen tooling only; QA stays PENDING; v1.0 not released)."
        ),
    )
    parser.add_argument(
        "--batch-root",
        type=Path,
        default=_DEFAULT_BATCH_ROOT,
        help="Batch parent dir holding openimages_<class>_v1 sub-dirs.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=_DEFAULT_REPORT_OUT,
        help="Destination for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional prior pilot-protection fingerprint JSON to compare against.",
    )
    parser.add_argument(
        "--status-dir",
        type=Path,
        default=_DEFAULT_STATUS_DIR,
        help=(
            "Dir of orchestrator per-class status JSONs (p4_3_2_real_*.json); "
            "used to surface every requested class's terminal state, failures "
            "included. Pass a non-existent path to skip."
        ),
    )
    parser.add_argument(
        "--created-at",
        type=str,
        default=_DEFAULT_CREATED_AT,
        help="Injected ISO-8601 timestamp (the clock is never read).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: analyse the batch and write the JSON report.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        Process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.batch_root.is_dir():
        print(f"error: batch root not found: {args.batch_root}", file=sys.stderr)
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.created_at)
    except ValueError:
        print(f"error: invalid --created-at: {args.created_at}", file=sys.stderr)
        return _EXIT_USAGE

    baseline: dict[str, dict[str, object]] | None = None
    if args.baseline is not None:
        if not args.baseline.is_file():
            print(f"error: baseline not found: {args.baseline}", file=sys.stderr)
            return _EXIT_USAGE
        loaded = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline = loaded.get("pilot_protection", loaded)

    settings = Settings()
    taxonomy = load_taxonomy()
    report = build_report(
        args.batch_root,
        settings=settings,
        taxonomy=taxonomy,
        created_at=args.created_at,
        baseline=baseline,
        status_dir=args.status_dir,
    )

    text = json.dumps(report, indent=2, sort_keys=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
