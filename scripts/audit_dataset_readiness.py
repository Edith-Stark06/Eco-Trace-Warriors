"""Dataset v1.0 readiness audit and gated release (Sprint P4.2.3).

This CLI is the **freeze gate** for Dataset v1.0. It composes the **frozen**
P4.1.2 pipeline and the P4.2.1/P4.2.2 toolkit scripts into a single, ordered set
of readiness gates and emits a machine-readable readiness report. It adds **no**
domain logic, mutates no dataset artefact, and touches no API surface — every
metric still comes from an existing component:

* taxonomy (PART 2) -> :func:`device_ai.dataset.taxonomy.load_taxonomy`;
* image validation (PART 3) ->
  :class:`device_ai.dataset.image_validation.ImageValidator`;
* annotation validation (PART 3) -> ``validate_annotations.validate``
  (frozen ``AnnotationValidator`` + the P4.2.2 layered checks);
* annotation statistics / coverage (PART 3) ->
  ``annotation_statistics.build_statistics``
  (frozen ``AnnotationStatisticsCalculator``);
* duplicate limits (PART 3) ->
  :class:`device_ai.dataset.duplicates.DuplicateDetector`;
* split verification (PART 4) ->
  :class:`device_ai.dataset.splitter.DatasetSplitter` (70/20/10, seed 42);
* release + manifest (PART 5/6) -> ``build_dataset_release.build_manifest``
  (frozen ``build_release`` / ``release_to_dict``).

The audit is **non-fabricating**: it never invents images, labels, counts or
quality metrics. When the repository holds no real dataset (the current state),
the audit reports ``BLOCKED`` and refuses to emit an official Dataset v1.0
release. A release manifest is produced **only** when every gate passes
(``READY``); the manifest is deterministic (injected timestamp, content-addressed
hash), so identical inputs yield byte-identical output.

Readiness states (most-severe first):

* ``INVALID`` — a hard defect makes the dataset unreleasable as-is (validation
  failures, orphan labels, duplicates, split leakage). Fix and re-run.
* ``BLOCKED`` — real data is absent or a prerequisite directory is missing;
  nothing to release yet.
* ``INCOMPLETE`` — data exists and is internally valid, but coverage/completeness
  gates are not all met (e.g. missing classes, gaps).
* ``READY`` — every gate passes; an official release may be built.

Exit codes:
    0: READY (all gates passed).
    1: not ready (INVALID / BLOCKED / INCOMPLETE).
    2: usage error (bad arguments / missing roots).

Examples:
    python scripts/audit_dataset_readiness.py \
        --images-root intelligence/device_ai/datasets/raw \
        --labels-root intelligence/device_ai/datasets/labels
    python scripts/audit_dataset_readiness.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --json-out datasets/quality/readiness.json \
        --md-out datasets/quality/readiness.md \
        --release-out datasets/exports/dataset_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse the P4.2.1 bootstrap (prepends ``intelligence/`` to ``sys.path``) so
# ``import device_ai...`` and the sibling toolkit scripts resolve from the repo
# root. ``REPO_ROOT`` is imported for its import-time side effect and re-exported
# for provenance; ``iter_label_boxes`` is the shared frozen-backed label reader.
from _annotation_toolkit import REPO_ROOT, iter_label_boxes  # noqa: F401
from annotation_statistics import build_statistics
from build_dataset_release import build_manifest
from validate_annotations import report_to_dict, validate

from device_ai.configs.settings import get_settings
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.image_validation import ImageValidator, image_validation_to_dict
from device_ai.dataset.layout import label_path_for, list_image_paths, relative_path
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.splitter import DatasetSplitter
from device_ai.dataset.taxonomy import load_taxonomy

# Exit codes (documented in the module docstring).
_EXIT_READY = 0
_EXIT_NOT_READY = 1
_EXIT_USAGE = 2

# Readiness states, ordered most-severe first for deterministic aggregation.
_STATE_INVALID = "INVALID"
_STATE_BLOCKED = "BLOCKED"
_STATE_INCOMPLETE = "INCOMPLETE"
_STATE_READY = "READY"
_STATE_SEVERITY = (_STATE_INVALID, _STATE_BLOCKED, _STATE_INCOMPLETE, _STATE_READY)

# Gate verdicts.
_PASS = "pass"
_FAIL = "fail"
_BLOCK = "block"

# Expected taxonomy contract (frozen). Mismatch is an INVALID condition — the
# values are asserted against the code-owned taxonomy, never redefined here.
_EXPECTED_TAXONOMY_VERSION = "1.0.0"
_EXPECTED_NUM_CLASSES = 19


def _worst_state(states: list[str]) -> str:
    """Return the most-severe readiness state present.

    Args:
        states: Per-gate readiness states.

    Returns:
        The most-severe state by :data:`_STATE_SEVERITY` ordering; ``READY``
        when the list is empty.
    """
    for state in _STATE_SEVERITY:
        if state in states:
            return state
    return _STATE_READY


def _gate(
    name: str,
    state: str,
    verdict: str,
    summary: str,
    detail: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one readiness-gate record.

    Args:
        name: Stable gate identifier.
        state: The gate's readiness state (one of :data:`_STATE_SEVERITY`).
        verdict: ``pass`` / ``fail`` / ``block``.
        summary: One-line human-readable outcome (ASCII).
        detail: Optional structured evidence.

    Returns:
        A JSON-serialisable gate record.
    """
    return {
        "name": name,
        "state": state,
        "verdict": verdict,
        "summary": summary,
        "detail": detail or {},
    }


def _taxonomy_gate() -> dict[str, object]:
    """PART 2 — verify the canonical taxonomy without redefining it.

    Returns:
        The taxonomy gate: ``pass`` when the code-owned taxonomy reports the
        frozen version and 19 contiguous class ids, else ``fail`` (``INVALID``).
    """
    taxonomy = load_taxonomy()
    ids_ok = tuple(range(taxonomy.num_classes)) == tuple(
        range(len(taxonomy.class_names))
    )
    version_ok = taxonomy.version == _EXPECTED_TAXONOMY_VERSION
    count_ok = taxonomy.num_classes == _EXPECTED_NUM_CLASSES
    ok = version_ok and count_ok and ids_ok and bool(taxonomy.class_names)
    detail: dict[str, object] = {
        "version": taxonomy.version,
        "expected_version": _EXPECTED_TAXONOMY_VERSION,
        "num_classes": taxonomy.num_classes,
        "expected_num_classes": _EXPECTED_NUM_CLASSES,
        "class_names": list(taxonomy.class_names),
        "version_ok": version_ok,
        "count_ok": count_ok,
        "contiguous_ids_ok": ids_ok,
    }
    if ok:
        return _gate(
            "taxonomy",
            _STATE_READY,
            _PASS,
            (
                f"taxonomy v{taxonomy.version} with {taxonomy.num_classes} "
                "classes (ids 0-18) verified"
            ),
            detail,
        )
    return _gate(
        "taxonomy",
        _STATE_INVALID,
        _FAIL,
        "taxonomy does not match the frozen 19-class v1.0.0 contract",
        detail,
    )


def _data_presence_gate(*, images_root: Path, labels_root: Path) -> dict[str, object]:
    """Confirm real dataset data exists before any content gate runs.

    Args:
        images_root: Directory that should contain the dataset images.
        labels_root: Directory that should contain the YOLO labels.

    Returns:
        A ``block`` gate (``BLOCKED``) when no images are present, else a
        ``pass`` gate carrying the discovered counts.
    """
    image_paths = list_image_paths(images_root)
    label_files = (
        list(labels_root.rglob("*.txt")) if labels_root.is_dir() else []
    )
    detail: dict[str, object] = {
        "images_root": images_root.as_posix(),
        "labels_root": labels_root.as_posix(),
        "image_count": len(image_paths),
        "label_file_count": len(label_files),
    }
    if not image_paths:
        return _gate(
            "data_presence",
            _STATE_BLOCKED,
            _BLOCK,
            "no dataset images found; nothing to release (BLOCKED)",
            detail,
        )
    return _gate(
        "data_presence",
        _STATE_READY,
        _PASS,
        f"{len(image_paths)} images and {len(label_files)} label files present",
        detail,
    )


def _image_validation_gate(*, images_root: Path) -> dict[str, object]:
    """PART 3 — structural image validation via the frozen ``ImageValidator``.

    Args:
        images_root: Directory containing the dataset images.

    Returns:
        A ``pass`` gate when the image set is free of blocking issues, else a
        ``fail`` gate (``INVALID``) carrying the serialised report summary.
    """
    settings = get_settings()
    report = ImageValidator(settings).validate(images_root=images_root)
    payload = image_validation_to_dict(report)
    detail = {
        "total_files_scanned": payload["total_files_scanned"],
        "total_images": payload["total_images"],
        "is_valid": payload["is_valid"],
        "summary": payload["summary"],
    }
    if report.is_valid:
        return _gate(
            "image_validation",
            _STATE_READY,
            _PASS,
            f"{report.total_images} images passed structural validation",
            detail,
        )
    return _gate(
        "image_validation",
        _STATE_INVALID,
        _FAIL,
        f"{len(report.issues)} structural image issue(s) found",
        detail,
    )


def _annotation_validation_gate(
    *, images_root: Path, labels_root: Path
) -> dict[str, object]:
    """PART 3 — annotation validation via the frozen validator + layered checks.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO labels.

    Returns:
        A ``pass`` gate when annotations are valid, else a ``fail`` gate
        (``INVALID``) carrying the issue-code histogram.
    """
    report = validate(images_root=images_root, labels_root=labels_root)
    payload = report_to_dict(report, images_root=images_root, labels_root=labels_root)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    detail = {
        "summary": summary,
        "issue_counts_by_code": payload["issue_counts_by_code"],
    }
    if report.is_valid:
        return _gate(
            "annotation_validation",
            _STATE_READY,
            _PASS,
            f"{report.total_boxes} boxes across {report.total_labels} labels valid",
            detail,
        )
    return _gate(
        "annotation_validation",
        _STATE_INVALID,
        _FAIL,
        f"{len(report.issues)} annotation issue(s) found",
        detail,
    )


def _coverage_gate(*, images_root: Path, labels_root: Path) -> dict[str, object]:
    """PART 3 — coverage/completeness via the frozen statistics calculator.

    Missing classes or annotation gaps are a completeness shortfall
    (``INCOMPLETE``), not a hard defect: the data present is internally usable
    but the dataset is not yet whole. Orphan labels are surfaced here for the
    report but are graded as an ``INVALID`` condition by the annotation gate.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO labels.

    Returns:
        The coverage gate record.
    """
    stats = build_statistics(
        images_root=images_root, labels_root=labels_root, bins=10, many_threshold=10
    )
    core = stats["core"]
    assert isinstance(core, dict)
    missing = core["missing_classes"]
    assert isinstance(missing, list)
    without_labels = core["images_without_labels"]
    assert isinstance(without_labels, list)
    completeness = core["annotation_completeness"]
    detail = {
        "total_images": core["total_images"],
        "total_labelled_images": core["total_labelled_images"],
        "total_boxes": core["total_boxes"],
        "annotation_completeness": completeness,
        "missing_classes": missing,
        "images_without_labels": len(without_labels),
    }
    complete = not missing and completeness == 1.0 and not without_labels
    if complete:
        return _gate(
            "coverage",
            _STATE_READY,
            _PASS,
            "all classes present and every image labelled",
            detail,
        )
    reasons = []
    if missing:
        reasons.append(f"{len(missing)} class(es) missing")
    if without_labels:
        reasons.append(f"{len(without_labels)} image(s) without labels")
    if completeness != 1.0:
        reasons.append(f"completeness {completeness}")
    return _gate(
        "coverage",
        _STATE_INCOMPLETE,
        _FAIL,
        "coverage incomplete: " + ", ".join(reasons),
        detail,
    )


def _duplicate_gate(*, images_root: Path) -> dict[str, object]:
    """PART 3 — duplicate limits via the frozen ``DuplicateDetector``.

    Args:
        images_root: Directory containing the dataset images.

    Returns:
        A ``pass`` gate when no exact/near duplicate is found, else a ``fail``
        gate (``INVALID``) listing the duplicate paths.
    """
    settings = get_settings()
    records = MetadataGenerator.from_settings(settings).analyze_directory(images_root)
    report = DuplicateDetector.from_settings(settings).detect(records)
    detail = {
        "total_images": report.total_images,
        "num_duplicates": report.num_duplicates,
        "hamming_threshold": settings.duplicate_hamming_threshold,
        "duplicate_paths": list(report.duplicate_paths),
    }
    if report.num_duplicates == 0:
        return _gate(
            "duplicates",
            _STATE_READY,
            _PASS,
            f"no duplicates among {report.total_images} images",
            detail,
        )
    return _gate(
        "duplicates",
        _STATE_INVALID,
        _FAIL,
        f"{report.num_duplicates} duplicate image(s) found",
        detail,
    )


def _split_gate(*, images_root: Path, labels_root: Path) -> dict[str, object]:
    """PART 4 — verify the deterministic 70/20/10, seed-42 split.

    Checks that the frozen :class:`DatasetSplitter` (settings ratios + seed)
    partitions the discovered images with no cross-split leakage and that every
    annotated class is represented in each of train/val/test.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO labels.

    Returns:
        The split gate record; ``INVALID`` on leakage, ``INCOMPLETE`` when a
        class is absent from a split.
    """
    settings = get_settings()
    identifiers = [relative_path(p, images_root) for p in list_image_paths(images_root)]
    splitter = DatasetSplitter.from_settings(settings)
    assignment = splitter.split_identifiers(identifiers)

    train = set(assignment.train)
    val = set(assignment.val)
    test = set(assignment.test)
    leakage = sorted((train & val) | (train & test) | (val & test))
    covered = train | val | test
    dropped = sorted(set(identifiers) - covered)

    detail: dict[str, object] = {
        "ratios": list(assignment.ratios),
        "seed": assignment.seed,
        "counts": assignment.counts,
        "leakage": leakage,
        "uncovered": dropped,
    }

    if leakage or dropped:
        return _gate(
            "split",
            _STATE_INVALID,
            _FAIL,
            f"split defect: {len(leakage)} leaked, {len(dropped)} uncovered",
            detail,
        )

    # Per-split class coverage: every class that appears anywhere must appear in
    # each non-empty split. Each identifier's label file maps to its class ids
    # through the shared frozen-backed reader.
    def _classes_for(ids: set[str]) -> set[int]:
        found: set[int] = set()
        for rel in ids:
            label = (labels_root / rel).with_suffix(".txt")
            if not label.exists():
                # Resolve via the image path to honour nested layouts.
                for image in list_image_paths(images_root):
                    if relative_path(image, images_root) == rel:
                        label = label_path_for(image, images_root, labels_root)
                        break
            if label.exists():
                for _, box in iter_label_boxes(label):
                    found.add(box.class_id)
        return found

    all_classes = _classes_for(covered)
    per_split = {
        "train": sorted(_classes_for(train)),
        "val": sorted(_classes_for(val)),
        "test": sorted(_classes_for(test)),
    }
    detail["classes_present"] = sorted(all_classes)
    detail["classes_per_split"] = per_split

    absent = {
        name: sorted(all_classes - set(ids))
        for name, ids in per_split.items()
        if all_classes - set(ids)
    }
    detail["classes_absent_from_split"] = absent

    if absent:
        return _gate(
            "split",
            _STATE_INCOMPLETE,
            _FAIL,
            "one or more classes absent from a split",
            detail,
        )
    return _gate(
        "split",
        _STATE_READY,
        _PASS,
        "70/20/10 seed-42 split verified: no leakage, all classes per split",
        detail,
    )


def audit(*, images_root: Path, labels_root: Path) -> dict[str, object]:
    """Run every readiness gate and aggregate an overall verdict.

    Gates short-circuit sensibly: taxonomy and data-presence run first; the
    content gates (image/annotation/coverage/duplicate/split) run only when real
    data is present, so an empty repository reports a clean ``BLOCKED`` rather
    than a cascade of spurious failures.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO labels.

    Returns:
        A JSON-serialisable readiness document with an ``overall`` state, the
        ordered ``gates`` and provenance echoes.
    """
    gates: list[dict[str, object]] = [_taxonomy_gate()]

    presence = _data_presence_gate(images_root=images_root, labels_root=labels_root)
    gates.append(presence)

    if presence["verdict"] == _PASS:
        gates.append(_image_validation_gate(images_root=images_root))
        gates.append(
            _annotation_validation_gate(
                images_root=images_root, labels_root=labels_root
            )
        )
        gates.append(_coverage_gate(images_root=images_root, labels_root=labels_root))
        gates.append(_duplicate_gate(images_root=images_root))
        gates.append(_split_gate(images_root=images_root, labels_root=labels_root))

    overall = _worst_state([str(g["state"]) for g in gates])
    return {
        "sprint": "P4.2.3",
        "images_root": images_root.as_posix(),
        "labels_root": labels_root.as_posix(),
        "overall": overall,
        "is_ready": overall == _STATE_READY,
        "gate_states": {str(g["name"]): g["state"] for g in gates},
        "gates": gates,
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render the readiness document as a human-readable Markdown report.

    Args:
        report: The dict produced by :func:`audit`.

    Returns:
        A Markdown document (ASCII only).
    """
    overall = report["overall"]
    lines = [
        "# Dataset v1.0 Readiness Audit",
        "",
        f"- Sprint: {report['sprint']}",
        f"- Overall: **{overall}**",
        f"- Images root: `{report['images_root']}`",
        f"- Labels root: `{report['labels_root']}`",
        "",
        "## Gates",
        "",
        "| Gate | State | Verdict | Summary |",
        "| --- | --- | --- | --- |",
    ]
    gates = report["gates"]
    assert isinstance(gates, list)
    for gate in gates:
        assert isinstance(gate, dict)
        lines.append(
            f"| {gate['name']} | {gate['state']} | {gate['verdict']} | "
            f"{gate['summary']} |"
        )
    lines.extend(["", "## Verdict", ""])
    if overall == _STATE_READY:
        lines.append("All gates passed. An official Dataset v1.0 release may be built.")
    elif overall == _STATE_BLOCKED:
        lines.append(
            "Dataset v1.0 is **BLOCKED**: no real dataset data is present. "
            "Release tooling is verified, but nothing can be released yet."
        )
    elif overall == _STATE_INVALID:
        lines.append(
            "Dataset v1.0 is **INVALID**: a hard defect must be fixed before "
            "release. See the failing gate detail."
        )
    else:
        lines.append(
            "Dataset v1.0 is **INCOMPLETE**: data is valid but coverage or "
            "completeness gates are unmet."
        )
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit Dataset v1.0 readiness and gate the official release.",
    )
    parser.add_argument(
        "--images-root",
        required=True,
        type=Path,
        help="Directory containing the dataset images.",
    )
    parser.add_argument(
        "--labels-root",
        required=True,
        type=Path,
        help="Directory containing the YOLO .txt label files.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the JSON readiness report.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path to write the Markdown readiness report.",
    )
    parser.add_argument(
        "--release-out",
        type=Path,
        default=None,
        help=(
            "Optional path to write the official dataset_manifest.json. The "
            "release is built ONLY when the audit is READY; otherwise the audit "
            "refuses and writes nothing here."
        ),
    )
    parser.add_argument(
        "--version",
        default="v1.0",
        help="Release version label used only when READY (default v1.0).",
    )
    parser.add_argument(
        "--created-at",
        default="2026-08-07T00:00:00+00:00",
        help=(
            "ISO-8601 release timestamp, injected for reproducibility and used "
            "only when READY (default 2026-08-07T00:00:00+00:00)."
        ),
    )
    parser.add_argument(
        "--note",
        default="",
        help="Optional human-readable release note (used only when READY).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the readiness audit.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 READY, 1 not ready, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return _EXIT_USAGE
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return _EXIT_USAGE

    report = audit(images_root=args.images_root, labels_root=args.labels_root)

    # PART 5/6 — build the official release ONLY when every gate passed. This is
    # the anti-fabrication guard: a non-READY dataset never yields a v1.0
    # manifest, on disk or otherwise.
    if args.release_out is not None:
        if report["is_ready"]:
            manifest = build_manifest(
                images_root=args.images_root,
                labels_root=args.labels_root,
                version=args.version,
                created_at=args.created_at,
                note=args.note,
            )
            args.release_out.parent.mkdir(parents=True, exist_ok=True)
            args.release_out.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report["release"] = {
                "written": True,
                "path": args.release_out.as_posix(),
                "content_hash": manifest["checksums"]["content_hash"]  # type: ignore[index]
                if isinstance(manifest.get("checksums"), dict)
                else None,
            }
        else:
            report["release"] = {
                "written": False,
                "reason": (
                    f"dataset is {report['overall']}, not READY; refusing to "
                    "build an official Dataset v1.0 release"
                ),
            }

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(report), encoding="utf-8")

    print(text)
    return _EXIT_READY if report["is_ready"] else _EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
