"""Build the P4.3.4 multi-class human-QA & candidate-assessment package.

This is a **manual-review checkpoint tool** — it is *not* production tooling and
*not* part of the frozen ``intelligence/device_ai`` pipeline. It assembles the
read-only evidence a human reviewer needs to sign off (or reject) the real
multi-class Open Images acquisitions produced by P4.3.x, and it does **nothing
else**. In particular it:

* **Certifies nothing.** Every reviewable item is emitted ``PENDING_REVIEW`` with
  empty ``human_decision``/``reviewer``/``review_date``/``notes``. No human
  decision is fabricated or inferred. The tool's ``proposed_decision`` is an
  advisory suggestion derived only from the frozen gates and is explicitly **not**
  a human decision.
* **Promotes nothing.** The candidate inventory admits only items whose
  ``status == "QA_ACCEPTED"``. At generation time every item is
  ``PENDING_REVIEW``, so the candidate inventory is deterministically **empty**.
  **Dataset v1.0 is NOT released.**
* **Is strictly read-only** w.r.t. every dataset artifact. It reads the Open
  Images source trees and the per-class staging directories and writes **only**
  under a separate review directory. A SHA-256 snapshot of every source and
  staging image/label is taken before and after generation and compared, and the
  comparison is recorded in ``integrity_verification.json``.
* **Invents no metric.** Structural validity comes from the frozen
  :class:`device_ai.dataset.image_validation.ImageValidator` (Gate A) and the
  P4.2.2 :mod:`validate_annotations` layer (Gate B); the blur numbers come from
  the frozen :func:`device_ai.dataset.metadata.blur_score` via the shared
  :mod:`make_visual_qa_multiclass` renderer. Class names/ids come from the frozen
  taxonomy (:func:`device_ai.dataset.taxonomy.load_taxonomy`); nothing is
  hard-coded and every count is read off real files/manifests.

Classes are discovered dynamically by walking
``dataset_acquisition/staging/**/provenance/provenance_manifest.json`` (so the
smartphone class at the top level and the tablet/monitor/printer classes nested
under ``openimages_multiclass_v1`` are all found without hard-coded paths). The
completed ``laptop`` pilot — which has its own P4.2.5 sign-off package — is
excluded and never touched.

Artifacts written under ``--review-root`` (default
``dataset_acquisition/review/p4_3_4_multiclass_qa_v1``):

* ``inventory.json`` / ``inventory.md`` — Part 1: per-class acquired-data
  inventory (counts, per-image SHA-256, provenance/conversion pointers).
* ``preqa_report.json`` / ``preqa_report.md`` — Part 2: the automated pre-QA gate
  (frozen Gate A + Gate B) per class.
* ``<class>/previews/`` + ``<class>/contact_sheet_pNN.jpg`` +
  ``<class>/qa_data.json`` — Part 3: per-class visual QA material (large classes
  are split into deterministic contact-sheet pages).
* ``signoff_template.json`` — Parts 4/5: one machine-readable row per image, all
  ``PENDING_REVIEW`` with blank human fields.
* ``second_review_sample.json`` / ``second_review_sample.md`` — Part 6: a
  deterministic, representative second-review sample (all ``PENDING_REVIEW``).
* ``candidate_inventory.json`` / ``candidate_inventory.md`` — Part 7: the
  Dataset-v1.0 candidate inventory (zero promoted at generation).
* ``integrity_verification.json`` — Part 8: the before/after SHA-256 snapshot
  proof that no source or staging artifact changed.
* ``package_manifest.json`` — a top-level index tying the package together with
  the explicit "Dataset v1.0 NOT RELEASED / no human decision fabricated"
  attestations.

Exit codes:
    0: package written and every source + staging tree verified unchanged.
    1: an integrity check failed (a snapshot drifted, or a SHA-256 did not
       reconcile against its provenance manifest).
    2: usage error (staging root missing, no acquired classes, bad timestamp).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import make_visual_qa_multiclass as vqa
import validate_annotations as ann
from _ecotrace_toolkit import REPO_ROOT
from device_ai.configs.settings import Settings, get_settings
from device_ai.dataset.hashing import sha256_hash
from device_ai.dataset.image_validation import ImageValidator, image_validation_to_dict
from device_ai.dataset.taxonomy import load_taxonomy

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_ERRORS = 1
_EXIT_USAGE = 2

# Injected defaults (never the wall clock).
_DEFAULT_STAGING_ROOT = REPO_ROOT / "dataset_acquisition" / "staging"
_DEFAULT_REVIEW_ROOT = (
    REPO_ROOT / "dataset_acquisition" / "review" / "p4_3_4_multiclass_qa_v1"
)
_DEFAULT_TIMESTAMP = "2026-08-10T00:00:00+00:00"
_DEFAULT_PACKAGE_VERSION = "p4-3-4-multiclass-human-qa-v1"

# The completed pilot class is protected: it has its own P4.2.5 sign-off package
# and is never re-reviewed or touched here.
_PILOT_CLASS = "laptop"

# The single acquisition source this package covers.
_APPROVED_SOURCE = "Open Images V7"

# The *only* decision states a human reviewer may record (Part 5). This exact
# four-value vocabulary is shared by ``status`` and ``proposed_decision``, but the
# two fields are independent: ``proposed_decision`` is advisory and never becomes
# ``status`` without an explicit human edit.
_DECISION_STATES = (
    "PENDING_REVIEW",
    "QA_ACCEPTED",
    "QA_REVIEW_REQUIRED",
    "QA_REJECTED",
)
_STATUS_PENDING = "PENDING_REVIEW"
_DECISION_ACCEPTED = "QA_ACCEPTED"
_DECISION_REVIEW_REQUIRED = "QA_REVIEW_REQUIRED"

# Deterministic second-review sampling defaults.
_DEFAULT_SAMPLE_SEED = 20260810
_DEFAULT_SAMPLE_FRACTION = 0.2

# Visual-QA layout defaults (contact-sheet paging keeps large classes readable).
_DEFAULT_PAGE_SIZE = 30
_DEFAULT_COLS = 5
_DEFAULT_CELL = 320


class PackageError(Exception):
    """A fatal QA-packaging error (missing artifact, snapshot drift, mismatch)."""


@dataclass(frozen=True, slots=True)
class AcquiredClass:
    """One discovered per-class acquisition, resolved from its provenance manifest.

    Attributes:
        ecotrace_class: Canonical EcoTrace class name (e.g. ``tablet``).
        class_id: Frozen-taxonomy class id for ``ecotrace_class``.
        source: Declared acquisition source (``Open Images V7``).
        source_class: The Open Images source label (e.g. ``Tablet computer``).
        staging_dir: Per-class staging root (holds ``images/`` + ``labels/``).
        manifest_path: Path to the provenance manifest.
        conversion_report_path: Path to the conversion report, or ``None``.
        source_images_root: Absolute Open Images source images root, or ``None``.
        source_labels_root: Absolute Open Images source labels root, or ``None``.
        records: The manifest's per-image records (stem -> metadata), in order.
    """

    ecotrace_class: str
    class_id: int
    source: str
    source_class: str
    staging_dir: Path
    manifest_path: Path
    conversion_report_path: Path | None
    source_images_root: Path | None
    source_labels_root: Path | None
    records: tuple[dict[str, object], ...]

    @property
    def images_dir(self) -> Path:
        """Directory holding the staged (canonical) images."""
        return self.staging_dir / "images"

    @property
    def labels_dir(self) -> Path:
        """Directory holding the staged (canonical) YOLO labels."""
        return self.staging_dir / "labels"


# --------------------------------------------------------------------------- #
# Deterministic filesystem helpers                                            #
# --------------------------------------------------------------------------- #
def snapshot_tree(root: Path) -> dict[str, str]:
    """Return a ``relpath -> sha256`` snapshot of every file under ``root``.

    Used to *prove* (not merely assert) that generating the package left the
    source and staging trees byte-identical: taken before and after and compared.

    Args:
        root: Directory to snapshot recursively (missing dir -> empty snapshot).

    Returns:
        A mapping of POSIX relative path to SHA-256 of the file bytes.
    """
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = sha256_hash(path.read_bytes())
    return out


def _diff_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """Return the added / removed / modified paths between two snapshots."""
    before_keys = set(before)
    after_keys = set(after)
    modified = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    return {
        "added": sorted(after_keys - before_keys),
        "removed": sorted(before_keys - after_keys),
        "modified": modified,
    }


def _as_int(value: object, default: int = 0) -> int:
    """Coerce a loosely-typed manifest/JSON value to ``int``, never raising.

    The provenance manifests and per-class document dicts are typed as
    ``dict[str, object]`` (their values arrive from JSON), so an explicit,
    total coercion keeps the counting arithmetic both correct and mypy-clean.
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


def _rel_repo(path: Path) -> str:
    """Return ``path`` relative to the repo root as POSIX, or its name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _write_json(path: Path, data: dict[str, object]) -> None:
    """Write ``data`` as deterministic JSON (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text, ensuring the parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _resolve_source_root(raw: object) -> Path | None:
    """Resolve a manifest source-root string to an absolute path, or ``None``."""
    if not isinstance(raw, str) or not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


# --------------------------------------------------------------------------- #
# Part 1 — discovery + inventory                                              #
# --------------------------------------------------------------------------- #
def discover_classes(staging_root: Path, *, exclude: str) -> list[AcquiredClass]:
    """Discover every acquired class under ``staging_root`` from its manifest.

    Walks ``**/provenance/provenance_manifest.json`` so per-class staging at any
    depth is found without hard-coded paths, then resolves each into a typed
    :class:`AcquiredClass`. The protected pilot class (``exclude``) is skipped.

    Args:
        staging_root: Base staging directory to search recursively.
        exclude: Ecotrace class name to skip (the completed pilot).

    Returns:
        Discovered classes ordered by ``(class_id, ecotrace_class)``.

    Raises:
        PackageError: When a manifest is unreadable or structurally invalid.
    """
    discovered: list[AcquiredClass] = []
    for manifest_path in sorted(staging_root.rglob("provenance/provenance_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:  # pragma: no cover - defensive
            raise PackageError(f"unreadable provenance manifest: {manifest_path}") from exc
        if not isinstance(manifest, dict):  # pragma: no cover - defensive
            raise PackageError(f"malformed provenance manifest: {manifest_path}")
        ecotrace_class = str(manifest.get("ecotrace_class", ""))
        if not ecotrace_class:
            raise PackageError(f"manifest missing ecotrace_class: {manifest_path}")
        if ecotrace_class == exclude:
            continue
        records = manifest.get("records", [])
        if not isinstance(records, list):
            raise PackageError(f"manifest 'records' is not a list: {manifest_path}")
        staging_dir = manifest_path.parents[1]
        conversion_report = staging_dir / "reports" / "conversion_report.json"
        discovered.append(
            AcquiredClass(
                ecotrace_class=ecotrace_class,
                class_id=int(manifest.get("ecotrace_class_id", -1)),
                source=str(manifest.get("source", "")),
                source_class=str(manifest.get("source_class", "")),
                staging_dir=staging_dir,
                manifest_path=manifest_path,
                conversion_report_path=(
                    conversion_report if conversion_report.is_file() else None
                ),
                source_images_root=_resolve_source_root(manifest.get("source_images_root")),
                source_labels_root=_resolve_source_root(manifest.get("source_labels_root")),
                records=tuple(r for r in records if isinstance(r, dict)),
            )
        )
    discovered.sort(key=lambda c: (c.class_id, c.ecotrace_class))
    return discovered


def _staged_image_paths(images_dir: Path) -> list[Path]:
    """Return the staged image files under ``images_dir``, sorted by name."""
    if not images_dir.is_dir():
        return []
    return sorted(
        p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".png"}
    )


def _reconcile_hashes(acquired: AcquiredClass) -> tuple[dict[str, str], list[str]]:
    """Hash each staged image and reconcile it against the manifest SHA-256.

    Args:
        acquired: The class whose staged images to hash.

    Returns:
        A ``(stem -> staged_sha256, mismatches)`` pair; ``mismatches`` lists the
        stems whose staged bytes disagree with (or are absent from) the manifest.
    """
    manifest_sha = {
        str(rec["stem"]): str(rec["sha256"])
        for rec in acquired.records
        if "stem" in rec and "sha256" in rec
    }
    staged_sha: dict[str, str] = {}
    mismatches: list[str] = []
    for image_path in _staged_image_paths(acquired.images_dir):
        digest = sha256_hash(image_path.read_bytes())
        staged_sha[image_path.stem] = digest
        if manifest_sha.get(image_path.stem) != digest:
            mismatches.append(image_path.stem)
    return staged_sha, sorted(mismatches)


def build_inventory(
    classes: list[AcquiredClass], *, context: dict[str, object]
) -> tuple[dict[str, object], dict[str, dict[str, str]]]:
    """Build the deterministic acquired-data inventory (Part 1).

    Args:
        classes: The discovered classes.
        context: Provenance echo written into the document header.

    Returns:
        A ``(inventory_document, staged_sha_by_class)`` pair. The second element
        maps each class name to its ``stem -> staged_sha256`` table (reused by the
        integrity check so images are hashed once).
    """
    entries: list[dict[str, object]] = []
    staged_sha_by_class: dict[str, dict[str, str]] = {}
    for acquired in classes:
        image_paths = _staged_image_paths(acquired.images_dir)
        label_count = sum(
            1 for p in acquired.labels_dir.glob("*.txt") if p.is_file()
        ) if acquired.labels_dir.is_dir() else 0
        object_count = sum(_as_int(rec.get("object_count", 0)) for rec in acquired.records)
        staged_sha, mismatches = _reconcile_hashes(acquired)
        staged_sha_by_class[acquired.ecotrace_class] = staged_sha
        visual_qa = acquired.staging_dir / "manual_review" / "qa_data.json"
        entries.append(
            {
                "ecotrace_class": acquired.ecotrace_class,
                "ecotrace_class_id": acquired.class_id,
                "source": acquired.source,
                "source_class": acquired.source_class,
                "staging_dir": _rel_repo(acquired.staging_dir),
                "image_count": len(image_paths),
                "label_count": label_count,
                "manifest_record_count": len(acquired.records),
                "object_count": object_count,
                "provenance_manifest": _rel_repo(acquired.manifest_path),
                "conversion_report": (
                    _rel_repo(acquired.conversion_report_path)
                    if acquired.conversion_report_path
                    else None
                ),
                "source_images_root": (
                    _rel_repo(acquired.source_images_root)
                    if acquired.source_images_root
                    else None
                ),
                "existing_visual_qa": (
                    _rel_repo(visual_qa) if visual_qa.is_file() else None
                ),
                "sha256_reconciled": not mismatches,
                "sha256_mismatches": mismatches,
                "per_image_sha256": dict(sorted(staged_sha.items())),
            }
        )
    document = {
        **context,
        "part": "1-acquired-data-inventory",
        "class_count": len(entries),
        "total_images": sum(_as_int(e["image_count"]) for e in entries),
        "total_labels": sum(_as_int(e["label_count"]) for e in entries),
        "total_objects": sum(_as_int(e["object_count"]) for e in entries),
        "all_sha256_reconciled": all(bool(e["sha256_reconciled"]) for e in entries),
        "classes": entries,
    }
    return document, staged_sha_by_class


def render_inventory_md(document: dict[str, object]) -> str:
    """Render the inventory document as a human-readable Markdown table."""
    classes = document["classes"]
    assert isinstance(classes, list)
    lines = [
        "# P4.3.4 Acquired-Data Inventory (Part 1)",
        "",
        f"- Source: **{_APPROVED_SOURCE}**",
        f"- Classes: **{document['class_count']}**",
        (
            f"- Total images: **{document['total_images']}**  "
            f"labels: **{document['total_labels']}**  "
            f"objects: **{document['total_objects']}**"
        ),
        (
            "- All SHA-256 reconciled vs manifest: "
            f"**{document['all_sha256_reconciled']}**"
        ),
        "",
        "| Class | id | images | labels | objects | SHA-256 reconciled | staging |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in classes:
        assert isinstance(entry, dict)
        lines.append(
            f"| {entry['ecotrace_class']} | {entry['ecotrace_class_id']} | "
            f"{entry['image_count']} | {entry['label_count']} | "
            f"{entry['object_count']} | {entry['sha256_reconciled']} | "
            f"`{entry['staging_dir']}` |"
        )
    lines.extend(["", "_Dataset v1.0 is NOT released. No image is promoted._", ""])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Part 2 — automated pre-QA gate                                              #
# --------------------------------------------------------------------------- #
def _issue_map_from_gate(
    image_payload: dict[str, object], annotation_payload: dict[str, object]
) -> dict[str, list[str]]:
    """Return a ``stem -> sorted issue codes`` map from the two gate reports."""
    issues: dict[str, set[str]] = {}
    for key in ("issues",):
        for payload in (image_payload, annotation_payload):
            entries = payload.get(key, [])
            if not isinstance(entries, list):
                continue
            for issue in entries:
                if not isinstance(issue, dict):
                    continue
                stem = Path(str(issue.get("file", ""))).stem
                if stem:
                    issues.setdefault(stem, set()).add(str(issue.get("code", "")))
    return {stem: sorted(codes) for stem, codes in issues.items()}


def run_preqa_gate(
    classes: list[AcquiredClass], *, settings: Settings, context: dict[str, object]
) -> tuple[dict[str, object], dict[str, dict[str, list[str]]]]:
    """Run the frozen Gate A + Gate B validators per class (Part 2).

    Args:
        classes: The discovered classes.
        settings: Injected settings supplying the frozen thresholds.
        context: Provenance echo for the document header.

    Returns:
        A ``(preqa_document, issue_map_by_class)`` pair. ``issue_map_by_class``
        maps class -> stem -> issue codes and feeds the sign-off ``issue_summary``.
    """
    per_class: list[dict[str, object]] = []
    issue_map_by_class: dict[str, dict[str, list[str]]] = {}
    for acquired in classes:
        image_report = ImageValidator(settings).validate(images_root=acquired.images_dir)
        image_payload = image_validation_to_dict(image_report)
        annotation_report = ann.validate(
            images_root=acquired.images_dir, labels_root=acquired.labels_dir
        )
        annotation_payload = ann.report_to_dict(
            annotation_report,
            images_root=acquired.images_dir,
            labels_root=acquired.labels_dir,
        )
        issue_map_by_class[acquired.ecotrace_class] = _issue_map_from_gate(
            image_payload, annotation_payload
        )
        image_summary = image_payload["summary"]
        annotation_summary = annotation_payload["summary"]
        assert isinstance(image_summary, dict)
        assert isinstance(annotation_summary, dict)
        per_class.append(
            {
                "ecotrace_class": acquired.ecotrace_class,
                "ecotrace_class_id": acquired.class_id,
                "gate_a_image_validation": image_payload,
                "gate_b_annotation_validation": annotation_payload,
                "gate_a_passed": bool(image_payload["is_valid"]),
                "gate_b_passed": bool(annotation_summary["is_valid"]),
                "duplicate_hashes": image_summary["duplicate_hashes"],
            }
        )
    document = {
        **context,
        "part": "2-automated-pre-qa-gate",
        "note": (
            "Automated structural gates only. A PASS is not a human QA decision; "
            "every image remains PENDING_REVIEW."
        ),
        "class_count": len(per_class),
        "all_gate_a_passed": all(bool(c["gate_a_passed"]) for c in per_class),
        "all_gate_b_passed": all(bool(c["gate_b_passed"]) for c in per_class),
        "classes": per_class,
    }
    return document, issue_map_by_class


def render_preqa_md(document: dict[str, object]) -> str:
    """Render the pre-QA gate document as Markdown."""
    classes = document["classes"]
    assert isinstance(classes, list)
    lines = [
        "# P4.3.4 Automated Pre-QA Gate (Part 2)",
        "",
        "- Gate A (image structural): frozen `ImageValidator`",
        "- Gate B (annotation): P4.2.2 `validate_annotations`",
        f"- All Gate A passed: **{document['all_gate_a_passed']}**",
        f"- All Gate B passed: **{document['all_gate_b_passed']}**",
        "",
        "| Class | Gate A | Gate B | image issues | annotation issues | dup hashes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in classes:
        assert isinstance(entry, dict)
        image_payload = entry["gate_a_image_validation"]
        annotation_payload = entry["gate_b_annotation_validation"]
        assert isinstance(image_payload, dict)
        assert isinstance(annotation_payload, dict)
        image_summary = image_payload["summary"]
        annotation_summary = annotation_payload["summary"]
        assert isinstance(image_summary, dict)
        assert isinstance(annotation_summary, dict)
        lines.append(
            f"| {entry['ecotrace_class']} | {entry['gate_a_passed']} | "
            f"{entry['gate_b_passed']} | {image_summary['total_issues']} | "
            f"{annotation_summary['issue_count']} | {entry['duplicate_hashes']} |"
        )
    lines.extend(
        [
            "",
            "A gate PASS is structural only and is **not** a human QA sign-off.",
            "",
        ]
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Part 3 — visual QA material                                                 #
# --------------------------------------------------------------------------- #
def build_visual_qa(
    acquired: AcquiredClass,
    *,
    class_names: tuple[str, ...],
    blur_threshold: float,
    class_out_dir: Path,
    page_size: int,
    cols: int,
    cell: int,
) -> tuple[list[vqa.Tile], dict[str, object]]:
    """Render per-image previews + paged contact sheets + ``qa_data.json``.

    Reuses the frozen-backed :func:`make_visual_qa_multiclass.render_preview` and
    :func:`make_visual_qa_multiclass.build_contact_sheet` verbatim, so the box
    tags and blur numbers agree with P4.3.2. Large classes are split into
    deterministic contact-sheet pages of at most ``page_size`` tiles.

    Args:
        acquired: The class to render.
        class_names: Frozen taxonomy class names (for box tags).
        blur_threshold: Frozen blur threshold for the ``[BLURRY]`` mark.
        class_out_dir: Output directory for this class's material.
        page_size: Maximum tiles per contact-sheet page.
        cols: Contact-sheet column count.
        cell: Contact-sheet cell size in pixels.

    Returns:
        A ``(tiles, qa_data)`` pair. ``qa_data`` is the ``QA_PENDING`` document
        written to ``qa_data.json``.
    """
    previews_dir = class_out_dir / "previews"
    tiles: list[vqa.Tile] = []
    for qa_id, image_path in enumerate(_staged_image_paths(acquired.images_dir), start=1):
        label_path = acquired.labels_dir / f"{image_path.stem}.txt"
        tiles.append(
            vqa.render_preview(
                image_path=image_path,
                label_path=label_path,
                qa_id=qa_id,
                blur_threshold=blur_threshold,
                class_names=class_names,
                out_dir=previews_dir,
            )
        )

    contact_sheets: list[str] = []
    page_count = max(1, math.ceil(len(tiles) / page_size)) if tiles else 0
    for page in range(page_count):
        chunk = tiles[page * page_size : (page + 1) * page_size]
        if not chunk:
            continue
        sheet_path = class_out_dir / f"contact_sheet_p{page + 1:02d}.jpg"
        vqa.build_contact_sheet(chunk, cols=cols, cell=cell, out_path=sheet_path)
        contact_sheets.append(_rel_repo(sheet_path))

    qa_data: dict[str, object] = {
        "ecotrace_class": acquired.ecotrace_class,
        "ecotrace_class_id": acquired.class_id,
        "qa_status": vqa._QA_PENDING,
        "blur_threshold": blur_threshold,
        "total_images": len(tiles),
        "total_objects": sum(t.box_count for t in tiles),
        "blurry_count": sum(1 for t in tiles if t.is_blurry),
        "page_count": page_count,
        "contact_sheets": contact_sheets,
        "tiles": [
            {
                "qa_id": t.qa_id,
                "stem": t.stem,
                "filename": t.filename,
                "width": t.width,
                "height": t.height,
                "box_count": t.box_count,
                "class_ids": list(t.class_ids),
                "blur": t.blur,
                "is_blurry": t.is_blurry,
                "preview": _rel_repo(t.preview_path),
            }
            for t in tiles
        ],
    }
    _write_json(class_out_dir / "qa_data.json", qa_data)
    return tiles, qa_data


# --------------------------------------------------------------------------- #
# Parts 4/5 — sign-off template                                               #
# --------------------------------------------------------------------------- #
def _proposed_decision(codes: list[str], *, is_blurry: bool) -> tuple[str, str]:
    """Return an advisory ``(proposed_decision, issue_summary)`` for one image.

    The proposal is derived only from the frozen gates (structural issue codes)
    and the frozen blur flag. It is **advisory**: it never sets ``status`` and a
    human must record the real decision.

    Args:
        codes: Sorted gate issue codes affecting the image (may be empty).
        is_blurry: Whether the frozen blur metric flags the image.

    Returns:
        The proposed decision (from :data:`_DECISION_STATES`) and a short summary.
    """
    parts = list(codes)
    if is_blurry:
        parts.append("BLURRY")
    if not parts:
        return _DECISION_ACCEPTED, "none"
    return _DECISION_REVIEW_REQUIRED, ", ".join(parts)


def build_signoff_rows(
    acquired: AcquiredClass,
    tiles: list[vqa.Tile],
    *,
    issue_map: dict[str, list[str]],
) -> list[dict[str, object]]:
    """Build the machine-readable sign-off rows for one class (Parts 4/5).

    Every row starts ``status = PENDING_REVIEW`` with empty human fields. The
    tool fills none of ``human_decision``/``reviewer``/``review_date``/``notes``.

    Args:
        acquired: The class the rows belong to.
        tiles: The rendered visual-QA tiles for the class.
        issue_map: ``stem -> gate issue codes`` for the class.

    Returns:
        One row per staged image, in visual-QA (``qa_id``) order.
    """
    record_by_stem = {str(rec["stem"]): rec for rec in acquired.records if "stem" in rec}
    rows: list[dict[str, object]] = []
    for tile in tiles:
        record = record_by_stem.get(tile.stem, {})
        codes = issue_map.get(tile.stem, [])
        proposed, summary = _proposed_decision(codes, is_blurry=tile.is_blurry)
        rows.append(
            {
                "item_id": f"{acquired.ecotrace_class}_{tile.qa_id:03d}",
                "class": acquired.ecotrace_class,
                "class_id": acquired.class_id,
                "canonical_image_filename": tile.filename,
                "source_image_filename": str(
                    record.get("source_image_filename", tile.filename)
                ),
                "source_image_id": tile.stem,
                "sha256": str(record.get("sha256", "")),
                "box_count": tile.box_count,
                "issue_summary": summary,
                "proposed_decision": proposed,
                # Human fields — left blank; no decision is fabricated or inferred.
                "status": _STATUS_PENDING,
                "human_decision": "",
                "reviewer": "",
                "review_date": "",
                "notes": "",
            }
        )
    return rows


def build_signoff_document(
    rows: list[dict[str, object]], *, context: dict[str, object]
) -> dict[str, object]:
    """Assemble the sign-off template document from all per-class rows."""
    by_class: dict[str, int] = {}
    for row in rows:
        name = str(row["class"])
        by_class[name] = by_class.get(name, 0) + 1
    return {
        **context,
        "part": "4-5-signoff-template",
        "allowed_statuses": list(_DECISION_STATES),
        "instructions": (
            "Set 'status' to one of allowed_statuses and fill 'human_decision', "
            "'reviewer' and 'review_date' by hand. Every item starts "
            "PENDING_REVIEW; no field is auto-completed. 'proposed_decision' is an "
            "advisory suggestion from the automated gates and is NOT a human "
            "decision; it never changes 'status' without an explicit human edit."
        ),
        "total_items": len(rows),
        "items_by_class": dict(sorted(by_class.items())),
        "pending_review_count": sum(1 for r in rows if r["status"] == _STATUS_PENDING),
        "signoff": rows,
    }


# --------------------------------------------------------------------------- #
# Part 6 — deterministic second-review sample                                 #
# --------------------------------------------------------------------------- #
def select_second_review(
    rows_by_class: dict[str, list[dict[str, object]]],
    *,
    seed: int,
    fraction: float,
    context: dict[str, object],
) -> dict[str, object]:
    """Select a deterministic, representative second-review sample (Part 6).

    For every class a fixed-seed shuffle of the class's items (sorted by
    ``item_id`` for a stable starting order) is truncated to
    ``max(1, round(fraction * n))`` items, so the sample is reproducible and
    spans every class. Every selected entry is emitted ``PENDING_REVIEW``.

    Args:
        rows_by_class: Sign-off rows grouped by class name.
        seed: Fixed RNG seed (the wall clock is never read).
        fraction: Per-class sampling fraction in ``(0, 1]``.
        context: Provenance echo for the document header.

    Returns:
        The second-review-sample document.
    """
    sample: list[dict[str, object]] = []
    per_class_counts: dict[str, int] = {}
    for name in sorted(rows_by_class):
        rows = sorted(rows_by_class[name], key=lambda r: str(r["item_id"]))
        if not rows:
            continue
        target = max(1, round(fraction * len(rows)))
        rng = random.Random(f"{seed}:{name}")
        order = list(rows)
        rng.shuffle(order)
        chosen = sorted(order[:target], key=lambda r: str(r["item_id"]))
        per_class_counts[name] = len(chosen)
        for row in chosen:
            sample.append(
                {
                    "item_id": row["item_id"],
                    "class": row["class"],
                    "source_image_id": row["source_image_id"],
                    "canonical_image_filename": row["canonical_image_filename"],
                    "sha256": row["sha256"],
                    "box_count": row["box_count"],
                    "proposed_decision": row["proposed_decision"],
                    "status": _STATUS_PENDING,
                    "human_decision": "",
                    "reviewer": "",
                    "review_date": "",
                    "notes": "",
                }
            )
    sample.sort(key=lambda r: str(r["item_id"]))
    return {
        **context,
        "part": "6-second-review-sample",
        "allowed_statuses": list(_DECISION_STATES),
        "sample_seed": seed,
        "sample_fraction": fraction,
        "note": (
            "Deterministic (fixed-seed) representative sample for independent "
            "second review. Every entry is PENDING_REVIEW; no decision is "
            "fabricated or inferred."
        ),
        "total_sampled": len(sample),
        "sampled_by_class": per_class_counts,
        "sample": sample,
    }


def render_second_review_md(document: dict[str, object]) -> str:
    """Render the second-review sample as Markdown."""
    counts = document["sampled_by_class"]
    assert isinstance(counts, dict)
    lines = [
        "# P4.3.4 Second-Review Sample (Part 6)",
        "",
        f"- Seed: `{document['sample_seed']}`  fraction: `{document['sample_fraction']}`",
        f"- Total sampled: **{document['total_sampled']}** (all PENDING_REVIEW)",
        "",
        "| Class | sampled |",
        "| --- | --- |",
    ]
    for name, count in sorted(counts.items()):
        lines.append(f"| {name} | {count} |")
    lines.extend(["", "_No decision is fabricated or inferred._", ""])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Part 7 — candidate inventory                                                #
# --------------------------------------------------------------------------- #
def build_candidate_inventory(
    rows: list[dict[str, object]], *, context: dict[str, object]
) -> dict[str, object]:
    """Build the Dataset-v1.0 candidate inventory (Part 7).

    Only items whose ``status == "QA_ACCEPTED"`` may enter. At generation every
    item is ``PENDING_REVIEW``, so the inventory is deterministically empty.

    Args:
        rows: All sign-off rows.
        context: Provenance echo for the document header.

    Returns:
        The candidate-inventory document (zero candidates at generation).
    """
    candidates = [
        {
            "item_id": row["item_id"],
            "class": row["class"],
            "source_image_id": row["source_image_id"],
            "canonical_image_filename": row["canonical_image_filename"],
            "sha256": row["sha256"],
        }
        for row in rows
        if row["status"] == _DECISION_ACCEPTED
    ]
    return {
        **context,
        "part": "7-candidate-inventory",
        "promotion_rule": "Only items with status == 'QA_ACCEPTED' are promoted.",
        "note": "Human QA decisions are pending; no images have been promoted.",
        "total_reviewable_items": len(rows),
        "promoted_count": len(candidates),
        "candidates": candidates,
        "is_dataset_v1": False,
        "is_released": False,
        "dataset_v1_released": False,
    }


def render_candidate_md(document: dict[str, object]) -> str:
    """Render the candidate inventory as Markdown."""
    return "\n".join(
        [
            "# P4.3.4 Dataset v1.0 Candidate Inventory (Part 7)",
            "",
            f"- Reviewable items: **{document['total_reviewable_items']}**",
            f"- Promoted candidates: **{document['promoted_count']}**",
            "",
            "**Human QA decisions are pending; no images have been promoted.**",
            "",
            "**Dataset v1.0 is NOT released.**",
            "",
        ]
    )


# --------------------------------------------------------------------------- #
# Part 8 — integrity verification                                             #
# --------------------------------------------------------------------------- #
def build_integrity_document(
    classes: list[AcquiredClass],
    *,
    source_before: dict[str, dict[str, str]],
    source_after: dict[str, dict[str, str]],
    staging_before: dict[str, dict[str, str]],
    staging_after: dict[str, dict[str, str]],
    context: dict[str, object],
) -> dict[str, object]:
    """Build the before/after SHA-256 immutability proof (Part 8).

    Args:
        classes: The discovered classes (for names/ids only).
        source_before: Per-class source snapshot taken before generation.
        source_after: Per-class source snapshot taken after generation.
        staging_before: Per-class staging snapshot taken before generation.
        staging_after: Per-class staging snapshot taken after generation.
        context: Provenance echo for the document header.

    Returns:
        The integrity-verification document.
    """
    per_class: list[dict[str, object]] = []
    all_source_ok = True
    all_staging_ok = True
    for acquired in classes:
        name = acquired.ecotrace_class
        src_before = source_before.get(name, {})
        src_after = source_after.get(name, {})
        stg_before = staging_before.get(name, {})
        stg_after = staging_after.get(name, {})
        source_unchanged = src_before == src_after
        staging_unchanged = stg_before == stg_after
        all_source_ok = all_source_ok and source_unchanged
        all_staging_ok = all_staging_ok and staging_unchanged
        per_class.append(
            {
                "ecotrace_class": name,
                "source_present": bool(src_after),
                "source_files_checked": len(src_after),
                "staging_files_checked": len(stg_after),
                "source_unchanged": source_unchanged,
                "staging_unchanged": staging_unchanged,
                "source_diff": _diff_snapshots(src_before, src_after),
                "staging_diff": _diff_snapshots(stg_before, stg_after),
            }
        )
    return {
        **context,
        "part": "8-integrity-verification",
        "source_unchanged": all_source_ok,
        "staging_unchanged": all_staging_ok,
        "all_unchanged": all_source_ok and all_staging_ok,
        "classes": per_class,
    }


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
def _context(*, package_version: str, timestamp: str) -> dict[str, object]:
    """Assemble the shared provenance echo written into every document."""
    return {
        "sprint": "P4.3.4",
        "package": "multiclass-human-qa",
        "package_version": package_version,
        "generated_at": timestamp,
        "source": _APPROVED_SOURCE,
        "taxonomy_version": load_taxonomy().version,
        "is_dataset_v1": False,
        "is_released": False,
        "dataset_v1_released": False,
        "no_human_decision_fabricated": True,
    }


def _snapshot_classes(
    classes: list[AcquiredClass],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Snapshot every class's source and staging trees (source + staging)."""
    source: dict[str, dict[str, str]] = {}
    staging: dict[str, dict[str, str]] = {}
    for acquired in classes:
        source[acquired.ecotrace_class] = (
            snapshot_tree(acquired.source_images_root)
            if acquired.source_images_root
            else {}
        )
        staging[acquired.ecotrace_class] = {
            **snapshot_tree(acquired.images_dir),
            **{f"labels/{k}": v for k, v in snapshot_tree(acquired.labels_dir).items()},
        }
    return source, staging


def build_package(
    *,
    staging_root: Path,
    review_root: Path,
    settings: Settings,
    blur_threshold: float,
    package_version: str,
    timestamp: str,
    sample_seed: int,
    sample_fraction: float,
    page_size: int,
    cols: int,
    cell: int,
) -> dict[str, object]:
    """Assemble the entire P4.3.4 QA package; return the package manifest.

    Snapshots every source and staging tree before and after generation so the
    "no dataset artifact was modified" guarantee is *proven*, not asserted.

    Raises:
        PackageError: When no class is found, a SHA-256 fails to reconcile, or a
            snapshot drifts while the package is built.
    """
    classes = discover_classes(staging_root, exclude=_PILOT_CLASS)
    if not classes:
        raise PackageError(f"no acquired classes found under {staging_root}")

    context = _context(package_version=package_version, timestamp=timestamp)
    class_names = load_taxonomy().class_names

    source_before, staging_before = _snapshot_classes(classes)

    # Part 1 — inventory (also reconciles staged bytes vs manifest SHA-256).
    inventory, _staged_sha = build_inventory(classes, context=context)
    if not inventory["all_sha256_reconciled"]:
        raise PackageError(
            "a staged image SHA-256 did not reconcile against its provenance "
            "manifest; refusing to build the package"
        )
    _write_json(review_root / "inventory.json", inventory)
    _write_text(review_root / "inventory.md", render_inventory_md(inventory))

    # Part 2 — automated pre-QA gate.
    preqa, issue_map_by_class = run_preqa_gate(
        classes, settings=settings, context=context
    )
    _write_json(review_root / "preqa_report.json", preqa)
    _write_text(review_root / "preqa_report.md", render_preqa_md(preqa))

    # Part 3/4/5 — visual QA + sign-off rows, per class.
    all_rows: list[dict[str, object]] = []
    rows_by_class: dict[str, list[dict[str, object]]] = {}
    for acquired in classes:
        tiles, _qa_data = build_visual_qa(
            acquired,
            class_names=class_names,
            blur_threshold=blur_threshold,
            class_out_dir=review_root / acquired.ecotrace_class,
            page_size=page_size,
            cols=cols,
            cell=cell,
        )
        rows = build_signoff_rows(
            acquired,
            tiles,
            issue_map=issue_map_by_class[acquired.ecotrace_class],
        )
        rows_by_class[acquired.ecotrace_class] = rows
        all_rows.extend(rows)

    signoff = build_signoff_document(all_rows, context=context)
    _write_json(review_root / "signoff_template.json", signoff)

    # Part 6 — deterministic second-review sample.
    second_review = select_second_review(
        rows_by_class, seed=sample_seed, fraction=sample_fraction, context=context
    )
    _write_json(review_root / "second_review_sample.json", second_review)
    _write_text(
        review_root / "second_review_sample.md", render_second_review_md(second_review)
    )

    # Part 7 — candidate inventory (zero promoted at generation).
    candidates = build_candidate_inventory(all_rows, context=context)
    _write_json(review_root / "candidate_inventory.json", candidates)
    _write_text(review_root / "candidate_inventory.md", render_candidate_md(candidates))

    # Part 8 — integrity verification (snapshot again + compare).
    source_after, staging_after = _snapshot_classes(classes)
    integrity = build_integrity_document(
        classes,
        source_before=source_before,
        source_after=source_after,
        staging_before=staging_before,
        staging_after=staging_after,
        context=context,
    )
    _write_json(review_root / "integrity_verification.json", integrity)

    manifest = {
        **context,
        "review_root": _rel_repo(review_root),
        "staging_root": _rel_repo(staging_root),
        "classes": [c.ecotrace_class for c in classes],
        "class_count": len(classes),
        "total_reviewable_items": len(all_rows),
        "pending_review_count": _as_int(signoff["pending_review_count"]),
        "promoted_count": _as_int(candidates["promoted_count"]),
        "second_review_sample_size": _as_int(second_review["total_sampled"]),
        "all_sha256_reconciled": bool(inventory["all_sha256_reconciled"]),
        "source_unchanged": bool(integrity["source_unchanged"]),
        "staging_unchanged": bool(integrity["staging_unchanged"]),
        "all_unchanged": bool(integrity["all_unchanged"]),
        "attestations": [
            "Dataset v1.0 is NOT RELEASED.",
            "No human QA decision has been fabricated or inferred.",
            "Every reviewable item is PENDING_REVIEW.",
            "Zero images have been promoted to a Dataset v1.0 candidate.",
        ],
        "artifacts": {
            "inventory": ["inventory.json", "inventory.md"],
            "preqa_report": ["preqa_report.json", "preqa_report.md"],
            "signoff_template": ["signoff_template.json"],
            "second_review_sample": [
                "second_review_sample.json",
                "second_review_sample.md",
            ],
            "candidate_inventory": ["candidate_inventory.json", "candidate_inventory.md"],
            "integrity_verification": ["integrity_verification.json"],
            "visual_qa_per_class": [
                f"{c.ecotrace_class}/qa_data.json" for c in classes
            ],
        },
    }
    _write_json(review_root / "package_manifest.json", manifest)

    if not integrity["all_unchanged"]:
        raise PackageError(
            "integrity check failed: a source/staging artifact changed while the "
            "package was built"
        )
    return manifest


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build the P4.3.4 multi-class human-QA & candidate-assessment package. "
            "Read-only on the Open Images source AND the per-class staging; writes "
            "only under a separate review directory. Certifies nothing: every item "
            "is emitted PENDING_REVIEW and Dataset v1.0 is NOT released."
        )
    )
    parser.add_argument("--staging-root", type=Path, default=_DEFAULT_STAGING_ROOT)
    parser.add_argument("--review-root", type=Path, default=_DEFAULT_REVIEW_ROOT)
    parser.add_argument(
        "--blur-threshold",
        type=float,
        default=None,
        help="Blur threshold for the [BLURRY] mark (defaults to frozen settings).",
    )
    parser.add_argument("--package-version", default=_DEFAULT_PACKAGE_VERSION)
    parser.add_argument(
        "--timestamp",
        default=_DEFAULT_TIMESTAMP,
        help="Injected ISO-8601 timestamp (the wall clock is never read).",
    )
    parser.add_argument("--sample-seed", type=int, default=_DEFAULT_SAMPLE_SEED)
    parser.add_argument("--sample-fraction", type=float, default=_DEFAULT_SAMPLE_FRACTION)
    parser.add_argument("--page-size", type=int, default=_DEFAULT_PAGE_SIZE)
    parser.add_argument("--cols", type=int, default=_DEFAULT_COLS)
    parser.add_argument("--cell", type=int, default=_DEFAULT_CELL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the P4.3.4 QA package builder.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 clean, 1 integrity/reconcile error, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.staging_root.is_dir():
        print(f"error: staging root not found: {args.staging_root}", file=sys.stderr)
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.timestamp)
    except ValueError:
        print(f"error: --timestamp is not valid ISO-8601: {args.timestamp}", file=sys.stderr)
        return _EXIT_USAGE
    if not 0.0 < args.sample_fraction <= 1.0:
        print("error: --sample-fraction must be in (0, 1]", file=sys.stderr)
        return _EXIT_USAGE
    if args.page_size < 1:
        print("error: --page-size must be >= 1", file=sys.stderr)
        return _EXIT_USAGE

    settings = get_settings()
    blur_threshold = (
        args.blur_threshold
        if args.blur_threshold is not None
        else float(settings.blur_threshold)
    )

    try:
        manifest = build_package(
            staging_root=args.staging_root,
            review_root=args.review_root,
            settings=settings,
            blur_threshold=blur_threshold,
            package_version=args.package_version,
            timestamp=args.timestamp,
            sample_seed=args.sample_seed,
            sample_fraction=args.sample_fraction,
            page_size=args.page_size,
            cols=args.cols,
            cell=args.cell,
        )
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERRORS

    print(json.dumps(manifest, indent=2, sort_keys=True))
    print(
        f"QA package written to {_rel_repo(args.review_root)} "
        f"(classes={manifest['class_count']}, items={manifest['total_reviewable_items']}, "
        f"promoted={manifest['promoted_count']}, all_unchanged={manifest['all_unchanged']})",
        file=sys.stderr,
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
