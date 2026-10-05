"""Validate YOLO annotations for Dataset v1.0 (Sprint P4.2.2, PART 1).

This CLI wraps the **frozen** P4.1.2
:class:`~device_ai.dataset.validator.AnnotationValidator` and layers the three
checks the frozen validator does not itself encode, so the full P4.2.2 checklist
is covered without duplicating any parsing or re-implementing the pipeline:

===========================  =====================================  ============
Requirement                  Issue code(s)                          Source
===========================  =====================================  ============
YOLO syntax                  ``MALFORMED_LINE``                     frozen
class ids                    ``NEGATIVE_CLASS_ID`` /                frozen
                             ``CLASS_ID_OUT_OF_RANGE``
normalised coordinates       ``COORD_OUT_OF_RANGE``                 frozen
zero-area boxes              ``NON_POSITIVE_SIZE``                  frozen
missing annotation files     ``MISSING_LABEL``                      frozen
orphan label files           ``ORPHAN_LABEL``                       frozen
boxes inside the image       ``BOX_OUT_OF_BOUNDS``                  layered here
duplicate annotations        ``DUPLICATE_BOX``                      layered here
empty labels                 ``EMPTY_LABEL``                        layered here
===========================  =====================================  ============

Validation is strictly read-only. Results are emitted as machine-readable JSON
and a human-readable Markdown report.

Exit codes:
    0: validation passed (no issues).
    1: validation failures were found.
    2: usage error (bad arguments / missing directories).

Examples:
    python scripts/validate_annotations.py \
        --images-root datasets/raw --labels-root datasets/labels
    python scripts/validate_annotations.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --json-out out.json --md-out out.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _annotation_toolkit import iter_label_boxes

from device_ai.dataset.layout import label_path_for, list_image_paths, relative_path
from device_ai.dataset.records import AnnotationIssue, AnnotationReport
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.validator import AnnotationValidator, YoloBox

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_FAILURES = 1
_EXIT_USAGE = 2


def _box_out_of_bounds(box: YoloBox) -> bool:
    """Return whether a box rectangle extends beyond the image frame.

    The frozen validator range-checks the *centre* and *size* individually
    (``COORD_OUT_OF_RANGE``); this checks the derived *edges* so a box that is
    in-range per field but still spills past an edge is caught.

    Args:
        box: A parsed YOLO bounding box.

    Returns:
        ``True`` when any edge falls outside ``[0, 1]`` (small tolerance).
    """
    half_w = box.width / 2.0
    half_h = box.height / 2.0
    tol = 1e-6
    return (
        box.x_center - half_w < -tol
        or box.x_center + half_w > 1.0 + tol
        or box.y_center - half_h < -tol
        or box.y_center + half_h > 1.0 + tol
    )


def _layered_issues(*, images_root: Path, labels_root: Path) -> list[AnnotationIssue]:
    """Compute the checks the frozen validator does not encode.

    Covers empty labels, out-of-bounds boxes and duplicate boxes by re-reading
    each paired label file through the shared, frozen-backed reader.

    Args:
        images_root: Directory containing the images.
        labels_root: Directory containing the YOLO ``.txt`` labels.

    Returns:
        Every layered :class:`AnnotationIssue` found.
    """
    issues: list[AnnotationIssue] = []
    for image_path in list_image_paths(images_root):
        label_path = label_path_for(image_path, images_root, labels_root)
        if not label_path.exists():
            continue
        file = relative_path(label_path, labels_root)
        seen: dict[tuple[int, float, float, float, float], int] = {}
        box_count = 0
        for line_no, box in iter_label_boxes(label_path):
            box_count += 1
            if _box_out_of_bounds(box):
                issues.append(
                    AnnotationIssue(
                        file=file,
                        line=line_no,
                        code="BOX_OUT_OF_BOUNDS",
                        message="bounding box extends beyond the image frame",
                    )
                )
            key = (
                box.class_id,
                box.x_center,
                box.y_center,
                box.width,
                box.height,
            )
            if key in seen:
                issues.append(
                    AnnotationIssue(
                        file=file,
                        line=line_no,
                        code="DUPLICATE_BOX",
                        message=f"duplicate of the box on line {seen[key]}",
                    )
                )
            else:
                seen[key] = line_no
        if box_count == 0:
            issues.append(
                AnnotationIssue(
                    file=file,
                    line=0,
                    code="EMPTY_LABEL",
                    message="label file exists but contains no bounding boxes",
                )
            )
    return issues


def _sort_key(issue: AnnotationIssue) -> tuple[str, int, str]:
    """Return a stable, deterministic ordering key for an issue."""
    return (issue.file, issue.line, issue.code)


def validate(*, images_root: Path, labels_root: Path) -> AnnotationReport:
    """Run the frozen validator plus the layered checks into one report.

    Args:
        images_root: Directory containing the images.
        labels_root: Directory containing the YOLO ``.txt`` labels.

    Returns:
        A merged :class:`AnnotationReport` carrying every issue found.
    """
    taxonomy = load_taxonomy()
    validator = AnnotationValidator(num_classes=taxonomy.num_classes)
    base = validator.validate(images_root=images_root, labels_root=labels_root)
    layered = _layered_issues(images_root=images_root, labels_root=labels_root)
    merged = tuple(sorted((*base.issues, *layered), key=_sort_key))
    return AnnotationReport(
        total_labels=base.total_labels,
        total_boxes=base.total_boxes,
        images_without_labels=base.images_without_labels,
        labels_without_images=base.labels_without_images,
        class_counts=base.class_counts,
        issues=merged,
    )


def _issue_counts_by_code(report: AnnotationReport) -> dict[str, int]:
    """Return a sorted mapping of issue code -> occurrence count."""
    counts: dict[str, int] = {}
    for issue in report.issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1
    return dict(sorted(counts.items()))


def report_to_dict(
    report: AnnotationReport, *, images_root: Path, labels_root: Path
) -> dict[str, object]:
    """Convert the merged report into a JSON-serialisable dict.

    Args:
        report: The merged annotation report.
        images_root: Images root (echoed for provenance).
        labels_root: Labels root (echoed for provenance).

    Returns:
        A primitive-only mapping.
    """
    taxonomy = load_taxonomy()
    empty_labels = sum(1 for i in report.issues if i.code == "EMPTY_LABEL")
    return {
        "images_root": images_root.as_posix(),
        "labels_root": labels_root.as_posix(),
        "taxonomy_version": taxonomy.version,
        "num_classes": taxonomy.num_classes,
        "summary": {
            "total_labels": report.total_labels,
            "total_boxes": report.total_boxes,
            "images_without_labels": len(report.images_without_labels),
            "labels_without_images": len(report.labels_without_images),
            "empty_labels": empty_labels,
            "issue_count": len(report.issues),
            "is_valid": report.is_valid,
        },
        "issue_counts_by_code": _issue_counts_by_code(report),
        "class_counts": {str(k): v for k, v in report.class_counts.items()},
        "issues": [
            {
                "file": issue.file,
                "line": issue.line,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in report.issues
        ],
    }


def render_markdown(payload: dict[str, object]) -> str:
    """Render the JSON payload as a human-readable Markdown report.

    Args:
        payload: The dict produced by :func:`report_to_dict`.

    Returns:
        A Markdown document (ASCII only).
    """
    summary = payload["summary"]
    assert isinstance(summary, dict)
    verdict = "PASS" if summary["is_valid"] else "FAIL"
    lines = [
        "# Annotation Validation Report",
        "",
        f"- Verdict: **{verdict}**",
        f"- Images root: `{payload['images_root']}`",
        f"- Labels root: `{payload['labels_root']}`",
        f"- Taxonomy version: {payload['taxonomy_version']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Label files | {summary['total_labels']} |",
        f"| Bounding boxes | {summary['total_boxes']} |",
        f"| Images without labels | {summary['images_without_labels']} |",
        f"| Orphan label files | {summary['labels_without_images']} |",
        f"| Empty label files | {summary['empty_labels']} |",
        f"| Total issues | {summary['issue_count']} |",
        "",
        "## Issues by code",
        "",
    ]
    counts = payload["issue_counts_by_code"]
    assert isinstance(counts, dict)
    if counts:
        lines.append("| Code | Count |")
        lines.append("| --- | --- |")
        lines.extend(f"| {code} | {count} |" for code, count in counts.items())
    else:
        lines.append("No issues found.")
    lines.extend(["", "## Issue detail", ""])
    issues = payload["issues"]
    assert isinstance(issues, list)
    if issues:
        lines.append("| File | Line | Code | Message |")
        lines.append("| --- | --- | --- | --- |")
        for issue in issues:
            assert isinstance(issue, dict)
            lines.append(
                f"| `{issue['file']}` | {issue['line']} | "
                f"{issue['code']} | {issue['message']} |"
            )
    else:
        lines.append("No issues found.")
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate YOLO annotations for Dataset v1.0.",
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
        help="Optional path to write the machine-readable JSON report.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path to write the Markdown report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the annotation validator.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 pass, 1 failures, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return _EXIT_USAGE
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return _EXIT_USAGE

    report = validate(images_root=args.images_root, labels_root=args.labels_root)
    payload = report_to_dict(
        report, images_root=args.images_root, labels_root=args.labels_root
    )

    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(payload), encoding="utf-8")

    print(text)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    return _EXIT_OK if summary["is_valid"] else _EXIT_FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
