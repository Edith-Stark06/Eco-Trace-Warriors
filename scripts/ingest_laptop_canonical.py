"""Remediate + canonically ingest the Open Images Laptop pilot (Sprint P4.2.4).

This CLI turns the **source-preserved** conversion staging
(``openimages_laptop_v1``) into a **canonical EcoTrace candidate** staging
(``openimages_laptop_canonical_v1``) by applying the manual visual-QA verdict
``PILOT_PASS_WITH_REVIEW`` (see
``docs/ai/reports/openimages_laptop_pilot_visual_qa.md``):

* **Exclude** the one REJECT image (QA14, a blurry keyboard-only macro) from the
  candidate dataset. The Open Images *source* is never touched; only the
  canonical candidate omits it, and the exclusion is fully recorded.
* **Re-annotate** the three REVIEW images that carry a genuine annotation defect
  (QA03 group box -> per-instance split; QA04 missing prominent laptop -> added;
  QA15 loose box -> tightened) into the canonical ``labels/``.
* **Hold** the borderline-blur REVIEW image (QA01) as ``REVIEW_PENDING`` with its
  original annotation unchanged (no automatic accept/reject authority exists for
  a below-threshold blur score; see the readiness checklist Gate A).
* **Accept** the remaining clean images unchanged.
* **Rename** every retained image to the code-owned collection convention
  ``<class_name>_<source_tag>_<seq>.<ext>`` (e.g. ``laptop_openimages_000001.jpg``)
  so the expected ``FILENAME_CONVENTION`` failure disappears in canonical staging,
  recording a deterministic ``source stem -> canonical stem`` mapping.

Design guarantees (identical in spirit to the frozen converter):

* **No frozen code is modified.** The taxonomy id is discovered through
  :func:`device_ai.dataset.taxonomy.load_taxonomy`, the SHA-256 reuses the frozen
  :func:`device_ai.dataset.hashing.sha256_hash`, and every corrected box is
  normalised + validated through the pilot converter's own ``convert_box`` (so a
  proposed box that leaves ``[0, 1]`` is rejected, never clipped).
* **Source is read-only.** The ``openimages_laptop_v1`` staging *and* the Open
  Images download are only ever read; all output lands under a separate canonical
  staging directory.
* **Corrections cannot self-certify.** Per the annotation review manual
  (separation of duties), every re-annotation and the held REVIEW image are
  emitted with ``reviewer_status = PENDING_REVIEW``; the tool asserts nothing is
  READY or RELEASED. This remains a single-class acquisition pilot, **not**
  Dataset v1.0.
* **Deterministic.** Byte-identical images are copied verbatim (SHA-256 re-checked
  against the source provenance), canonical sequence numbers are assigned in
  sorted source-stem order, the only timestamp is injected via
  ``--remediation-timestamp``, and all JSON is ``indent=2, sort_keys=True``.

Exit codes:
    0: canonical candidate ingested and every retained image SHA-256 verified.
    1: an integrity check failed (missing source, SHA mismatch, invalid box).
    2: usage error (missing directories, invalid timestamp).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT, parse_collection_filename
from convert_openimages_to_yolo import SourceBox, convert_box, format_yolo_line

from device_ai.dataset.hashing import sha256_hash
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_ERRORS = 1
_EXIT_USAGE = 2

# Deterministic defaults for the Laptop pilot canonical ingestion.
_DEFAULT_SOURCE_STAGING = (
    REPO_ROOT / "dataset_acquisition/staging/openimages_laptop_v1"
)
_DEFAULT_CANONICAL_STAGING = (
    REPO_ROOT / "dataset_acquisition/staging/openimages_laptop_canonical_v1"
)
_DEFAULT_SOURCE_TAG = "openimages"
_DEFAULT_REMEDIATION_VERSION = "openimages-laptop-canonical-v1"
_DEFAULT_REMEDIATION_TIMESTAMP = "2026-08-09T00:00:00+00:00"

# Remediation action vocabulary (stable, machine-readable).
_ACTION_ACCEPT = "ACCEPT"
_ACTION_EXCLUDE = "EXCLUDE"
_ACTION_REVIEW_HOLD = "KEEP_REVIEW_PENDING"
_ACTION_SPLIT = "REANNOTATE_SPLIT"
_ACTION_ADD = "REANNOTATE_ADD_INSTANCE"
_ACTION_TIGHTEN = "REANNOTATE_TIGHTEN"

# Remediation status vocabulary.
_STATUS_ACCEPTED = "ACCEPTED"
_STATUS_EXCLUDED = "EXCLUDED"
_STATUS_REVIEW_PENDING = "REVIEW_PENDING"
_STATUS_REMEDIATION_REVIEW_PENDING = "REMEDIATION_REVIEW_PENDING"

# Reviewer status vocabulary (separation of duties: AI cannot self-certify).
_REVIEWER_QA_ACCEPTED = "QA_ACCEPTED"
_REVIEWER_PENDING = "PENDING_REVIEW"
_REVIEWER_EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class Remediation:
    """A hand-authored, human-proposed remediation decision for one source image.

    The corrected boxes are expressed in **pixel-space XYXY** (the same space as
    the Open Images source) so they can be normalised and validated through the
    pilot converter's frozen-style ``convert_box``. Every non-ACCEPT decision is
    a *proposal* pending independent human review — the coordinate values are
    deliberate visual estimates, not tool-measured ground truth.

    Attributes:
        action: One of the ``_ACTION_*`` constants.
        qa_id: The visual-QA tile id (1-based) from the QA report.
        qa_decision: The visual-QA decision (ACCEPT / REVIEW / REJECT).
        reason: Human-readable rationale for the decision.
        keep_original_boxes: When True, the source YOLO label is preserved and
            ``added_boxes_px`` are appended (used for a missing-instance add).
            When False, ``added_boxes_px`` *replace* the source label entirely
            (used for a split or a tighten).
        added_boxes_px: Proposed boxes as ``(x1, y1, x2, y2)`` pixel tuples.
        difficult: Whether the image should be flagged a ``difficult`` example
            (dense/receding cluster) per the annotation guidelines.
    """

    action: str
    qa_id: int
    qa_decision: str
    reason: str
    keep_original_boxes: bool = True
    added_boxes_px: tuple[tuple[float, float, float, float], ...] = ()
    difficult: bool = False


# --- The remediation spec (the P4.2.4 policy decisions, keyed by source stem) --
#
# Only the five images that the visual QA flagged (1 REJECT + 4 REVIEW) appear
# here; every other source image is ACCEPTed unchanged by default. The pixel
# coordinates below are human-proposed visual estimates that RE-ENTER first
# review (annotation review manual, separation of duties) and are therefore
# emitted as PENDING_REVIEW — nothing here is self-certified as final.
_REMEDIATION_SPEC: dict[str, Remediation] = {
    # QA14 -- blurry, keyboard-only macro, indistinguishable from the separate
    # `keyboard` class. Excluded from the candidate; the Open Images source copy
    # is left untouched.
    "79182035199f2b58": Remediation(
        action=_ACTION_EXCLUDE,
        qa_id=14,
        qa_decision="REJECT",
        reason=(
            "Blurry (blur 58.7) extreme keyboard macro with no laptop form "
            "factor visible; visually indistinguishable from the separate "
            "`keyboard` taxonomy class. Not a usable `laptop` exemplar."
        ),
    ),
    # QA03 -- one group box spans a receding row of ~5-6 distinct laptops.
    # Proposed split into per-instance boxes for the distinguishable laptops;
    # flagged `difficult` because the cluster recedes and overlaps.
    "0171ad35f1651698": Remediation(
        action=_ACTION_SPLIT,
        qa_id=3,
        qa_decision="REVIEW",
        reason=(
            "Source group box covers a whole row of distinct laptops (violates "
            "one-box-per-instance). Proposed split into per-laptop boxes for the "
            "distinguishable foreground/mid instances; flagged difficult."
        ),
        keep_original_boxes=False,
        added_boxes_px=(
            (0.0, 300.0, 270.0, 768.0),
            (150.0, 280.0, 340.0, 540.0),
            (300.0, 285.0, 440.0, 470.0),
            (400.0, 280.0, 510.0, 430.0),
            (460.0, 285.0, 590.0, 410.0),
        ),
        difficult=True,
    ),
    # QA04 -- prominent sticker-covered laptop (centre-right) is unannotated.
    # Keep the five source boxes and add one box for the missing instance.
    "14587a599414300c": Remediation(
        action=_ACTION_ADD,
        qa_id=4,
        qa_decision="REVIEW",
        reason=(
            "Source omits the prominent open sticker-covered laptop "
            "(centre-right). Proposed one added box for the missing instance; "
            "the five source boxes are preserved."
        ),
        keep_original_boxes=True,
        added_boxes_px=((495.0, 255.0, 700.0, 405.0),),
    ),
    # QA15 -- loose box: roughly half the box area is non-laptop (cat/desk).
    # Proposed tighter box around the truncated white MacBook only.
    "936a6d462e9d4873": Remediation(
        action=_ACTION_TIGHTEN,
        qa_id=15,
        qa_decision="REVIEW",
        reason=(
            "Source box (y1~1 to y2~767, full frame height) includes the cat "
            "paws and wall well above the screen and desk to the right (~half "
            "the box is non-laptop). Proposed tighter box: top raised to the "
            "screen bezel and right edge pulled in to the truncated white "
            "MacBook (screen + keyboard base) only."
        ),
        keep_original_boxes=False,
        added_boxes_px=((0.0, 108.0, 420.0, 768.0),),
    ),
    # QA01 -- borderline low-light blur (blur 45.6). No automatic accept/reject
    # authority exists for a below-threshold score (readiness checklist Gate A),
    # so it is HELD as REVIEW_PENDING with its source annotation unchanged.
    "00767fb6565581c6": Remediation(
        action=_ACTION_REVIEW_HOLD,
        qa_id=1,
        qa_decision="REVIEW",
        reason=(
            "Borderline low-light blur (blur 45.6, lowest in the set); laptop "
            "still identifiable and box correct. No policy authority to auto "
            "accept/reject a below-threshold blur -> held for human sign-off."
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One source-preserved provenance record needed for canonical ingestion.

    Attributes:
        stem: The source image/label stem.
        source_image_filename: e.g. ``00767fb6565581c6.jpg``.
        source_annotation_filename: e.g. ``00767fb6565581c6.txt``.
        sha256: SHA-256 of the source image bytes (from the pilot provenance).
        width: Decoded image width in pixels.
        height: Decoded image height in pixels.
        source: Human-readable source dataset (e.g. ``Open Images V7``).
        source_class: The source class spelling (``Laptop``).
        ecotrace_class: The canonical EcoTrace class (``laptop``).
        ecotrace_class_id: The discovered taxonomy id (``0``).
        object_count: Boxes in the source label.
    """

    stem: str
    source_image_filename: str
    source_annotation_filename: str
    sha256: str
    width: int
    height: int
    source: str
    source_class: str
    ecotrace_class: str
    ecotrace_class_id: int
    object_count: int


@dataclass(slots=True)
class CanonicalImage:
    """The fully-resolved ingestion outcome for one retained source image.

    Attributes:
        source: The originating :class:`SourceRecord`.
        canonical_stem: e.g. ``laptop_openimages_000001``.
        canonical_image_filename: e.g. ``laptop_openimages_000001.jpg``.
        canonical_label_filename: e.g. ``laptop_openimages_000001.txt``.
        sequence: Zero-padded canonical sequence string.
        yolo_lines: Final canonical YOLO label lines.
        action: The applied ``_ACTION_*`` value.
        qa_id: Visual-QA tile id (0 when not individually QA-flagged).
        qa_decision: Visual-QA decision.
        remediation_status: Applied ``_STATUS_*`` value.
        reviewer_status: Applied ``_REVIEWER_*`` value.
        reason: Rationale for the decision.
        original_object_count: Boxes in the source label.
        corrected_object_count: Boxes in the canonical label.
        difficult: Whether the image is flagged a difficult example.
        image_bytes: Verbatim source image bytes (byte-identical copy).
    """

    source: SourceRecord
    canonical_stem: str
    canonical_image_filename: str
    canonical_label_filename: str
    sequence: str
    yolo_lines: tuple[str, ...]
    action: str
    qa_id: int
    qa_decision: str
    remediation_status: str
    reviewer_status: str
    reason: str
    original_object_count: int
    corrected_object_count: int
    difficult: bool
    image_bytes: bytes = field(repr=False, default=b"")


@dataclass(frozen=True, slots=True)
class Exclusion:
    """A recorded exclusion of a source image from the canonical candidate.

    Attributes:
        source: The originating :class:`SourceRecord`.
        qa_id: Visual-QA tile id.
        qa_decision: Visual-QA decision (``REJECT``).
        reason: Rationale for the exclusion.
    """

    source: SourceRecord
    qa_id: int
    qa_decision: str
    reason: str


class IngestError(Exception):
    """A fatal ingestion integrity error (missing source, SHA mismatch, box)."""


def load_source_records(provenance_path: Path) -> list[SourceRecord]:
    """Load the source-preserved provenance manifest into typed records.

    Args:
        provenance_path: Path to the pilot ``provenance_manifest.json``.

    Returns:
        Source records sorted by stem (deterministic ingestion order).

    Raises:
        IngestError: When the manifest is missing or malformed.
    """
    if not provenance_path.is_file():
        raise IngestError(f"source provenance manifest not found: {provenance_path}")
    data = json.loads(provenance_path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    if not isinstance(records, list) or not records:
        raise IngestError(f"no provenance records in {provenance_path}")
    out: list[SourceRecord] = []
    for rec in records:
        out.append(
            SourceRecord(
                stem=str(rec["stem"]),
                source_image_filename=str(rec["source_image_filename"]),
                source_annotation_filename=str(rec["source_annotation_filename"]),
                sha256=str(rec["sha256"]),
                width=int(rec["width"]),
                height=int(rec["height"]),
                source=str(rec["source"]),
                source_class=str(rec["source_class"]),
                ecotrace_class=str(rec["ecotrace_class"]),
                ecotrace_class_id=int(rec["ecotrace_class_id"]),
                object_count=int(rec["object_count"]),
            )
        )
    return sorted(out, key=lambda r: r.stem)


def _read_source_label_lines(label_path: Path) -> list[str]:
    """Return the non-empty stripped lines of a source YOLO label file."""
    if not label_path.is_file():
        raise IngestError(f"source label not found: {label_path}")
    return [
        line.strip()
        for line in label_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _corrected_lines(
    *,
    remediation: Remediation,
    source_lines: list[str],
    width: int,
    height: int,
    class_id: int,
) -> tuple[str, ...]:
    """Build the canonical YOLO lines for a re-annotated image.

    Proposed pixel boxes are normalised + validated through the pilot converter's
    ``convert_box`` (reject-never-clip); the class id is the discovered taxonomy
    id, never assumed.

    Args:
        remediation: The remediation decision.
        source_lines: The source label's stripped YOLO lines.
        width: Image width in pixels.
        height: Image height in pixels.
        class_id: The discovered EcoTrace class id.

    Returns:
        The final canonical YOLO lines.

    Raises:
        IngestError: When a proposed box fails ``convert_box`` validation.
    """
    lines: list[str] = list(source_lines) if remediation.keep_original_boxes else []
    for x1, y1, x2, y2 in remediation.added_boxes_px:
        box = SourceBox(class_name="Laptop", x1=x1, y1=y1, x2=x2, y2=y2)
        try:
            converted = convert_box(
                box, image_width=width, image_height=height, class_id=class_id
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a fatal ingest error
            raise IngestError(
                f"proposed box ({x1},{y1},{x2},{y2}) invalid on "
                f"{width}x{height}: {exc}"
            ) from exc
        lines.append(format_yolo_line(converted))
    return tuple(lines)


def plan_ingestion(
    *,
    source_records: list[SourceRecord],
    source_staging: Path,
    source_tag: str,
    taxonomy: DeviceTaxonomy,
) -> tuple[list[CanonicalImage], list[Exclusion]]:
    """Resolve every source record into a canonical image or an exclusion.

    Canonical sequence numbers are assigned to *retained* images in sorted
    source-stem order, so the mapping is deterministic and gap-free.

    Args:
        source_records: The typed source provenance records (sorted by stem).
        source_staging: Root of the source-preserved pilot staging.
        source_tag: The collection source tag (e.g. ``openimages``).
        taxonomy: The loaded EcoTrace taxonomy.

    Returns:
        A ``(canonical_images, exclusions)`` tuple.

    Raises:
        IngestError: On any integrity failure (missing/SHA-mismatched source,
            invalid proposed box, or a canonical filename that fails the
            collection convention).
    """
    labels_dir = source_staging / "labels"
    images_dir = source_staging / "images"
    class_names = taxonomy.class_names

    canonical: list[CanonicalImage] = []
    exclusions: list[Exclusion] = []
    sequence = 0

    for record in source_records:
        remediation = _REMEDIATION_SPEC.get(record.stem)
        if remediation is not None and remediation.action == _ACTION_EXCLUDE:
            exclusions.append(
                Exclusion(
                    source=record,
                    qa_id=remediation.qa_id,
                    qa_decision=remediation.qa_decision,
                    reason=remediation.reason,
                )
            )
            continue

        # Verify the byte-identical source image and its SHA-256 up front.
        image_path = images_dir / record.source_image_filename
        if not image_path.is_file():
            raise IngestError(f"source image not found: {image_path}")
        image_bytes = image_path.read_bytes()
        actual_sha = sha256_hash(image_bytes)
        if actual_sha != record.sha256:
            raise IngestError(
                f"SHA-256 mismatch for {record.stem}: provenance {record.sha256} "
                f"!= actual {actual_sha}"
            )

        source_lines = _read_source_label_lines(
            labels_dir / record.source_annotation_filename
        )

        action, status, reviewer, reason, difficult, lines = _resolve_label(
            record=record,
            remediation=remediation,
            source_lines=source_lines,
            taxonomy=taxonomy,
        )

        sequence += 1
        seq_str = f"{sequence:06d}"
        suffix = Path(record.source_image_filename).suffix
        canonical_stem = f"{record.ecotrace_class}_{source_tag}_{seq_str}"
        canonical_image = f"{canonical_stem}{suffix}"

        parsed = parse_collection_filename(canonical_image, class_names)
        if not parsed.is_valid:
            raise IngestError(
                f"canonical filename {canonical_image} violates the collection "
                f"convention: {parsed.reason}"
            )

        canonical.append(
            CanonicalImage(
                source=record,
                canonical_stem=canonical_stem,
                canonical_image_filename=canonical_image,
                canonical_label_filename=f"{canonical_stem}.txt",
                sequence=seq_str,
                yolo_lines=lines,
                action=action,
                qa_id=remediation.qa_id if remediation else 0,
                qa_decision=remediation.qa_decision if remediation else "ACCEPT",
                remediation_status=status,
                reviewer_status=reviewer,
                reason=reason,
                original_object_count=record.object_count,
                corrected_object_count=len(lines),
                difficult=difficult,
                image_bytes=image_bytes,
            )
        )

    return canonical, exclusions


def _resolve_label(
    *,
    record: SourceRecord,
    remediation: Remediation | None,
    source_lines: list[str],
    taxonomy: DeviceTaxonomy,
) -> tuple[str, str, str, str, bool, tuple[str, ...]]:
    """Resolve the action/status/reviewer/label for one retained image.

    Returns:
        ``(action, remediation_status, reviewer_status, reason, difficult,
        yolo_lines)``.
    """
    if remediation is None:
        # Clean ACCEPT: canonical label is the source label verbatim.
        return (
            _ACTION_ACCEPT,
            _STATUS_ACCEPTED,
            _REVIEWER_QA_ACCEPTED,
            "Clean visual QA ACCEPT; source annotation preserved unchanged.",
            False,
            tuple(source_lines),
        )

    if remediation.action == _ACTION_REVIEW_HOLD:
        # QA01: held, source annotation unchanged, pending human sign-off.
        return (
            _ACTION_REVIEW_HOLD,
            _STATUS_REVIEW_PENDING,
            _REVIEWER_PENDING,
            remediation.reason,
            remediation.difficult,
            tuple(source_lines),
        )

    # A re-annotation (split / add / tighten): build corrected lines and mark
    # them pending independent review (corrections cannot self-certify).
    class_id = taxonomy.class_id_for(record.ecotrace_class)
    if class_id is None:  # pragma: no cover - taxonomy is frozen with `laptop`
        raise IngestError(
            f"canonical class '{record.ecotrace_class}' absent from taxonomy "
            f"v{taxonomy.version}"
        )
    lines = _corrected_lines(
        remediation=remediation,
        source_lines=source_lines,
        width=record.width,
        height=record.height,
        class_id=class_id,
    )
    return (
        remediation.action,
        _STATUS_REMEDIATION_REVIEW_PENDING,
        _REVIEWER_PENDING,
        remediation.reason,
        remediation.difficult,
        lines,
    )


def _context(
    *,
    source_staging: Path,
    canonical_staging: Path,
    source_tag: str,
    taxonomy: DeviceTaxonomy,
    remediation_version: str,
    remediation_timestamp: str,
) -> dict[str, object]:
    """Assemble the shared provenance echo written into every output document."""
    return {
        "pilot": "openimages-laptop",
        "sprint": "P4.2.4",
        "remediation_version": remediation_version,
        "remediation_timestamp": remediation_timestamp,
        "source_staging": _rel(source_staging),
        "canonical_staging": _rel(canonical_staging),
        "source_tag": source_tag,
        "ecotrace_class": "laptop",
        "ecotrace_class_id": taxonomy.class_id_for("laptop"),
        "taxonomy_version": taxonomy.version,
        "is_dataset_v1": False,
        "is_released": False,
    }


def build_filename_map(
    canonical: list[CanonicalImage], *, context: dict[str, object]
) -> dict[str, object]:
    """Build the deterministic source-stem -> canonical-stem mapping document."""
    return {
        **context,
        "total_mapped": len(canonical),
        "mapping": [
            {
                "source_stem": c.source.stem,
                "source_image_filename": c.source.source_image_filename,
                "canonical_stem": c.canonical_stem,
                "canonical_image_filename": c.canonical_image_filename,
                "canonical_label_filename": c.canonical_label_filename,
                "sequence": c.sequence,
                "sha256": c.source.sha256,
            }
            for c in canonical
        ],
    }


def build_remediation_manifest(
    canonical: list[CanonicalImage],
    exclusions: list[Exclusion],
    *,
    context: dict[str, object],
) -> dict[str, object]:
    """Build the machine-readable remediation manifest (PART 7/9 fields)."""
    records = [
        {
            "canonical_image_filename": c.canonical_image_filename,
            "canonical_label_filename": c.canonical_label_filename,
            "canonical_stem": c.canonical_stem,
            "sequence": c.sequence,
            "source_stem": c.source.stem,
            "source_image_filename": c.source.source_image_filename,
            "source_annotation_filename": c.source.source_annotation_filename,
            "source_sha256": c.source.sha256,
            "source_dataset": c.source.source,
            "source_class": c.source.source_class,
            "ecotrace_class": c.source.ecotrace_class,
            "ecotrace_class_id": c.source.ecotrace_class_id,
            "width": c.source.width,
            "height": c.source.height,
            "qa_id": c.qa_id,
            "qa_decision": c.qa_decision,
            "remediation_action": c.action,
            "remediation_status": c.remediation_status,
            "reviewer_status": c.reviewer_status,
            "original_object_count": c.original_object_count,
            "corrected_object_count": c.corrected_object_count,
            "difficult": c.difficult,
            "reason": c.reason,
        }
        for c in canonical
    ]
    excluded = [
        {
            "source_stem": e.source.stem,
            "source_image_filename": e.source.source_image_filename,
            "source_annotation_filename": e.source.source_annotation_filename,
            "source_sha256": e.source.sha256,
            "source_dataset": e.source.source,
            "source_class": e.source.source_class,
            "ecotrace_class": e.source.ecotrace_class,
            "ecotrace_class_id": e.source.ecotrace_class_id,
            "width": e.source.width,
            "height": e.source.height,
            "object_count": e.source.object_count,
            "qa_id": e.qa_id,
            "qa_decision": e.qa_decision,
            "remediation_action": _ACTION_EXCLUDE,
            "remediation_status": _STATUS_EXCLUDED,
            "reviewer_status": _REVIEWER_EXCLUDED,
            "reason": e.reason,
        }
        for e in exclusions
    ]

    by_action: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for c in canonical:
        by_action[c.action] = by_action.get(c.action, 0) + 1
        by_status[c.remediation_status] = by_status.get(c.remediation_status, 0) + 1
    for _exclusion in exclusions:
        by_action[_ACTION_EXCLUDE] = by_action.get(_ACTION_EXCLUDE, 0) + 1
        by_status[_STATUS_EXCLUDED] = by_status.get(_STATUS_EXCLUDED, 0) + 1

    return {
        **context,
        "summary": {
            "source_images": len(canonical) + len(exclusions),
            "retained_images": len(canonical),
            "excluded_images": len(exclusions),
            "total_original_objects": sum(c.original_object_count for c in canonical)
            + sum(e.source.object_count for e in exclusions),
            "retained_original_objects": sum(
                c.original_object_count for c in canonical
            ),
            "retained_corrected_objects": sum(
                c.corrected_object_count for c in canonical
            ),
            "images_reannotated": sum(
                1
                for c in canonical
                if c.remediation_status == _STATUS_REMEDIATION_REVIEW_PENDING
            ),
            "images_review_pending": sum(
                1 for c in canonical if c.remediation_status == _STATUS_REVIEW_PENDING
            ),
            "by_action": dict(sorted(by_action.items())),
            "by_status": dict(sorted(by_status.items())),
        },
        "records": records,
        "exclusions": excluded,
    }


def build_provenance(
    canonical: list[CanonicalImage], *, context: dict[str, object]
) -> dict[str, object]:
    """Build the canonical provenance manifest (one record per retained image)."""
    return {
        **context,
        "total_images": len(canonical),
        "records": [
            {
                "canonical_stem": c.canonical_stem,
                "canonical_image_filename": c.canonical_image_filename,
                "source_stem": c.source.stem,
                "source_image_filename": c.source.source_image_filename,
                "source_annotation_filename": c.source.source_annotation_filename,
                "source_dataset": c.source.source,
                "source_class": c.source.source_class,
                "ecotrace_class": c.source.ecotrace_class,
                "ecotrace_class_id": c.source.ecotrace_class_id,
                "sha256": c.source.sha256,
                "width": c.source.width,
                "height": c.source.height,
                "object_count": c.corrected_object_count,
                "remediation_status": c.remediation_status,
                "reviewer_status": c.reviewer_status,
                "remediation_version": context["remediation_version"],
                "remediation_timestamp": context["remediation_timestamp"],
            }
            for c in canonical
        ],
    }


def write_canonical(
    canonical: list[CanonicalImage],
    *,
    filename_map: dict[str, object],
    remediation_manifest: dict[str, object],
    provenance: dict[str, object],
    canonical_staging: Path,
) -> dict[str, Path]:
    """Write the canonical images, labels, provenance and reports.

    Args:
        canonical: The retained canonical images.
        filename_map: The source->canonical mapping document.
        remediation_manifest: The remediation manifest document.
        provenance: The canonical provenance manifest.
        canonical_staging: Destination canonical staging root.

    Returns:
        A mapping of the key output paths written.

    Raises:
        IngestError: When a re-copied canonical image fails its SHA-256 re-check.
    """
    images_dir = canonical_staging / "images"
    labels_dir = canonical_staging / "labels"
    provenance_dir = canonical_staging / "provenance"
    reports_dir = canonical_staging / "reports"
    for directory in (images_dir, labels_dir, provenance_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for c in canonical:
        image_out = images_dir / c.canonical_image_filename
        image_out.write_bytes(c.image_bytes)
        # Re-check the written bytes so the canonical copy is provably identical.
        if sha256_hash(image_out.read_bytes()) != c.source.sha256:
            raise IngestError(
                f"canonical copy SHA mismatch for {c.canonical_image_filename}"
            )
        label_text = "\n".join(c.yolo_lines)
        (labels_dir / c.canonical_label_filename).write_text(
            label_text + "\n" if label_text else "", encoding="utf-8"
        )

    map_path = reports_dir / "canonical_filename_map.json"
    manifest_path = reports_dir / "remediation_manifest.json"
    provenance_path = provenance_dir / "provenance_manifest.json"
    _write_json(map_path, filename_map)
    _write_json(manifest_path, remediation_manifest)
    _write_json(provenance_path, provenance)
    return {
        "images_dir": images_dir,
        "labels_dir": labels_dir,
        "provenance": provenance_path,
        "remediation_manifest": manifest_path,
        "filename_map": map_path,
    }


def _write_json(path: Path, data: dict[str, object]) -> None:
    """Write ``data`` as deterministic JSON (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repo root as POSIX, or its name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Remediate + canonically ingest the Open Images Laptop pilot "
            "(P4.2.4). Read-only on the source staging; writes only to a new "
            "canonical staging directory. This is an acquisition pilot only, "
            "NOT a Dataset v1.0 release."
        )
    )
    parser.add_argument(
        "--source-staging",
        type=Path,
        default=_DEFAULT_SOURCE_STAGING,
        help="Source-preserved pilot staging root (read-only).",
    )
    parser.add_argument(
        "--canonical-staging",
        type=Path,
        default=_DEFAULT_CANONICAL_STAGING,
        help="Destination canonical staging root (never the source).",
    )
    parser.add_argument(
        "--source-tag",
        default=_DEFAULT_SOURCE_TAG,
        help=f"Collection source tag (default '{_DEFAULT_SOURCE_TAG}').",
    )
    parser.add_argument(
        "--remediation-version",
        default=_DEFAULT_REMEDIATION_VERSION,
        help="Remediation/version identifier recorded in every output.",
    )
    parser.add_argument(
        "--remediation-timestamp",
        default=_DEFAULT_REMEDIATION_TIMESTAMP,
        help="Injected ISO-8601 timestamp (the wall clock is never read).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the canonical remediation + ingestion tool.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 clean, 1 integrity error, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.source_staging.is_dir():
        print(
            f"error: source staging not found: {args.source_staging}",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.remediation_timestamp)
    except ValueError:
        print(
            "error: --remediation-timestamp is not valid ISO-8601: "
            f"{args.remediation_timestamp}",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    taxonomy = load_taxonomy()
    provenance_path = args.source_staging / "provenance" / "provenance_manifest.json"

    try:
        source_records = load_source_records(provenance_path)
        canonical, exclusions = plan_ingestion(
            source_records=source_records,
            source_staging=args.source_staging,
            source_tag=args.source_tag,
            taxonomy=taxonomy,
        )
        context = _context(
            source_staging=args.source_staging,
            canonical_staging=args.canonical_staging,
            source_tag=args.source_tag,
            taxonomy=taxonomy,
            remediation_version=args.remediation_version,
            remediation_timestamp=args.remediation_timestamp,
        )
        filename_map = build_filename_map(canonical, context=context)
        remediation_manifest = build_remediation_manifest(
            canonical, exclusions, context=context
        )
        provenance = build_provenance(canonical, context=context)
        outputs = write_canonical(
            canonical,
            filename_map=filename_map,
            remediation_manifest=remediation_manifest,
            provenance=provenance,
            canonical_staging=args.canonical_staging,
        )
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERRORS

    summary = remediation_manifest["summary"]
    assert isinstance(summary, dict)
    print(json.dumps(remediation_manifest, indent=2, sort_keys=True))
    print(
        f"ingested {summary['retained_images']}/{summary['source_images']} images "
        f"({summary['excluded_images']} excluded, "
        f"{summary['images_reannotated']} re-annotated, "
        f"{summary['images_review_pending']} review-pending) -> "
        f"{outputs['images_dir'].as_posix()}",
        file=sys.stderr,
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
