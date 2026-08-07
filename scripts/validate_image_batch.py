"""Validate a batch of collected images before it enters the dataset.

Phase 4.2.1 — Production Image Collection Toolkit (PART 1).

A contributor drops a folder of images; this script tells them — before the
data engineer ever runs intake — whether the batch is clean. It checks:

* **filename convention** ``<class_name>_<source_tag>_<seq>.<ext>`` (new here);
* **extension** is a supported image type;
* **duplicate filename** across the batch;
* **duplicate content** (exact SHA-256);
* **resolution** within the configured min/max dimensions;
* **blur** (variance-of-Laplacian below threshold);
* **brightness** (mean luminance outside the dark/bright band);
* **aspect ratio** within bounds;
* **file size** within the configured maximum.

Every structural check reuses the **frozen** ``ImageValidator`` and every
quality check reuses ``MetadataGenerator``/``evaluate_quality`` from the
P4.1.2 pipeline — this script only *orchestrates* them and adds the filename
convention the pipeline does not encode. It reads the batch, writes nothing to
it, and touches no API.

Usage (from the repository root)::

    python scripts/validate_image_batch.py <batch_dir> [--json report.json]
                                           [--quiet] [--allow-quality-warnings]

Exit status is ``0`` when the batch is clean, ``1`` when any blocking issue is
found, and ``2`` on usage error (e.g. missing directory) — so it slots into a
pre-commit hook or CI check.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _ecotrace_toolkit import parse_collection_filename
from device_ai.configs.settings import Settings
from device_ai.dataset.image_validation import ImageValidator
from device_ai.dataset.layout import list_image_paths, relative_path
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.taxonomy import load_taxonomy

# Quality issue codes that the structural ImageValidator does NOT emit and that
# this script layers on from the quality metrics. Kept aligned with the
# QualityMetrics.issues vocabulary in records.py.
_QUALITY_CODES = {
    "blurry": "IMAGE_BLURRY",
    "dark": "IMAGE_TOO_DARK",
    "bright": "IMAGE_TOO_BRIGHT",
    "low_resolution": "RESOLUTION_TOO_SMALL",
}


@dataclass(frozen=True, slots=True)
class BatchIssue:
    """A single problem found while validating a collection batch.

    Attributes:
        file: ``relative_path`` of the offending image within the batch.
        code: Stable machine-readable issue code.
        message: Human-readable description.
        severity: ``"blocking"`` (fails the batch) or ``"warning"``.
    """

    file: str
    code: str
    message: str
    severity: str


def _check_filename_convention(
    batch_dir: Path, class_names: tuple[str, ...]
) -> list[BatchIssue]:
    """Flag images whose filename breaks the collection convention.

    Args:
        batch_dir: The batch directory being validated.
        class_names: Canonical taxonomy class names (code-owned).

    Returns:
        One blocking :class:`BatchIssue` per non-conforming filename.
    """
    issues: list[BatchIssue] = []
    for path in list_image_paths(batch_dir):
        parsed = parse_collection_filename(path.name, class_names)
        if not parsed.is_valid:
            issues.append(
                BatchIssue(
                    file=relative_path(path, batch_dir),
                    code="FILENAME_CONVENTION",
                    message=(
                        f"'{path.name}' violates "
                        f"<class_name>_<source_tag>_<seq>.<ext>: {parsed.reason}"
                    ),
                    severity="blocking",
                )
            )
    return issues


def _check_quality(
    batch_dir: Path, settings: Settings, *, quality_blocking: bool
) -> list[BatchIssue]:
    """Flag blur/brightness/low-resolution issues via the quality metrics.

    Reuses :class:`MetadataGenerator` (which decodes each image once and runs
    ``evaluate_quality``) rather than recomputing any metric here.

    Args:
        batch_dir: The batch directory being validated.
        settings: Injected application settings supplying thresholds.
        quality_blocking: Whether quality issues fail the batch (True) or are
            reported as warnings (False).

    Returns:
        One :class:`BatchIssue` per quality flag raised.
    """
    severity = "blocking" if quality_blocking else "warning"
    records = MetadataGenerator.from_settings(settings).analyze_directory(batch_dir)
    issues: list[BatchIssue] = []
    for record in records:
        if record.quality.is_corrupted:
            # Corruption is already reported (blocking) by ImageValidator.
            continue
        for flag in record.quality.issues:
            code = _QUALITY_CODES.get(flag)
            if code is None:
                continue
            if flag == "blurry":
                detail = f"blur score {record.quality.blur_score} below threshold"
            elif flag in {"dark", "bright"}:
                detail = f"brightness {record.quality.brightness} out of band"
            else:
                detail = f"{record.width}x{record.height} below minimum dimension"
            issues.append(
                BatchIssue(
                    file=record.relative_path,
                    code=code,
                    message=detail,
                    severity=severity,
                )
            )
    return issues


def _structural_issues(batch_dir: Path, settings: Settings) -> list[BatchIssue]:
    """Run the frozen ImageValidator and adapt its issues to BatchIssues.

    Args:
        batch_dir: The batch directory being validated.
        settings: Injected application settings.

    Returns:
        Blocking :class:`BatchIssue` objects mirroring the validator report.
    """
    report = ImageValidator(settings).validate(images_root=batch_dir)
    return [
        BatchIssue(
            file=issue.file,
            code=issue.code,
            message=issue.message,
            severity="blocking",
        )
        for issue in report.issues
    ]


def validate_batch(
    batch_dir: Path, settings: Settings, *, quality_blocking: bool
) -> list[BatchIssue]:
    """Validate a batch by composing the structural, filename and quality checks.

    Args:
        batch_dir: Directory of collected images to validate.
        settings: Injected application settings.
        quality_blocking: Whether blur/brightness issues fail the batch.

    Returns:
        Every issue found, ordered by file then code. Empty means clean.
    """
    class_names = load_taxonomy().class_names
    issues: list[BatchIssue] = []
    issues.extend(_structural_issues(batch_dir, settings))
    issues.extend(_check_filename_convention(batch_dir, class_names))
    issues.extend(_check_quality(batch_dir, settings, quality_blocking=quality_blocking))
    issues.sort(key=lambda i: (i.file, i.code))
    return issues


def build_report(batch_dir: Path, issues: list[BatchIssue]) -> dict[str, object]:
    """Assemble a JSON-serialisable validation report for a batch.

    Args:
        batch_dir: The validated batch directory.
        issues: The issues returned by :func:`validate_batch`.

    Returns:
        A primitive-only mapping suitable for ``json.dump``.
    """
    total_images = len(list_image_paths(batch_dir))
    blocking = [i for i in issues if i.severity == "blocking"]
    warnings = [i for i in issues if i.severity == "warning"]
    files_with_blocking = {i.file for i in blocking}
    by_code: dict[str, int] = {}
    for issue in issues:
        by_code[issue.code] = by_code.get(issue.code, 0) + 1
    return {
        "batch_dir": batch_dir.as_posix(),
        "total_images": total_images,
        "is_valid": not blocking,
        "summary": {
            "total_issues": len(issues),
            "blocking": len(blocking),
            "warnings": len(warnings),
            "images_with_blocking_issues": len(files_with_blocking),
            "clean_images": total_images - len(files_with_blocking),
            "by_code": dict(sorted(by_code.items())),
        },
        "issues": [
            {
                "file": issue.file,
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in issues
        ],
    }


def _print_human(report: dict[str, object]) -> None:
    """Print a concise human-readable summary of a validation report."""
    summary = report["summary"]
    status = "PASS" if report["is_valid"] else "FAIL"
    print(f"Batch: {report['batch_dir']}")
    print(f"Images: {report['total_images']}   Result: {status}")
    print(
        f"Issues: {summary['total_issues']} "
        f"({summary['blocking']} blocking, {summary['warnings']} warnings)"
    )
    if summary["by_code"]:
        print("By code:")
        for code, count in summary["by_code"].items():
            print(f"  {code}: {count}")
    for issue in report["issues"]:
        marker = "x" if issue["severity"] == "blocking" else "!"
        print(f"  [{marker}] {issue['file']}: {issue['code']} - {issue['message']}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate a batch of collected images (filename convention, "
            "extension, duplicates, resolution, blur, brightness, aspect "
            "ratio, file size) reusing the frozen dataset pipeline."
        )
    )
    parser.add_argument("batch_dir", type=Path, help="Directory of images to validate.")
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write the full JSON report to PATH.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable summary (still sets the exit code).",
    )
    parser.add_argument(
        "--allow-quality-warnings",
        action="store_true",
        help=(
            "Treat blur/brightness/low-resolution issues as warnings that do "
            "not fail the batch (default: they are blocking)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 clean, 1 blocking issues found, 2 usage error.
    """
    args = _parse_args(argv)
    batch_dir: Path = args.batch_dir
    if not batch_dir.is_dir():
        print(f"error: not a directory: {batch_dir}", file=sys.stderr)
        return 2

    settings = Settings()
    issues = validate_batch(
        batch_dir, settings, quality_blocking=not args.allow_quality_warnings
    )
    report = build_report(batch_dir, issues)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if not args.quiet:
        _print_human(report)

    return 0 if report["is_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


