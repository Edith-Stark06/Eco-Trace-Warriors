"""Annotation dashboard for Dataset v1.0 (Sprint P4.2.2, PART 5).

One page summarising the annotation effort, emitted as both Markdown and a
self-contained HTML document. It composes the sibling toolkit scripts and the
frozen pipeline — it computes no metric itself:

* **validation summary** — reuses PART 1 ``validate`` / ``report_to_dict``;
* **class distribution** and **missing labels** — reuse PART 2
  ``build_statistics`` (frozen ``AnnotationStatisticsCalculator``);
* **annotation progress** — read from the optional
  ``annotation_progress.csv`` template (per-class annotated vs targets);
* **review status** — summarised from the optional ``annotation_review.csv``;
* **QA failures** — summarised from the optional ``qa_report.csv``.

The CSV inputs are the P4.1.x templates under ``docs/ai/templates/``; comment
lines (``#``) and the shipped ``EXAMPLE-`` placeholder rows are skipped so a
freshly-copied template contributes nothing misleading. Every value is HTML
escaped. The dashboard reads only; it writes nothing back to the dataset.

Exit codes:
    0: dashboard rendered.
    2: usage error (missing directories).

Examples:
    python scripts/annotation_dashboard.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --html-out out/dashboard.html --md-out out/dashboard.md
    python scripts/annotation_dashboard.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --progress-csv docs/ai/templates/annotation_progress.csv \
        --review-csv docs/ai/templates/annotation_review.csv \
        --qa-csv docs/ai/templates/qa_report.csv
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path

from annotation_statistics import build_statistics
from validate_annotations import report_to_dict, validate

# Rows in the shipped templates are prefixed to mark them as illustrative.
_EXAMPLE_PREFIX = "EXAMPLE-"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a template CSV, skipping ``#`` comments and EXAMPLE rows.

    The P4.1.x templates prefix their header/notes with ``#`` and ship
    illustrative rows whose ids start with ``EXAMPLE-``; both are excluded so a
    freshly-copied template yields an empty (not misleading) section.

    Args:
        path: Path to a template CSV file.

    Returns:
        One dict per data row (empty when the file is missing/blank).
    """
    if not path.is_file():
        return []
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return []
    reader = csv.DictReader(lines)
    rows: list[dict[str, str]] = []
    for row in reader:
        first = next(iter(row.values()), "") or ""
        if first.startswith(_EXAMPLE_PREFIX):
            continue
        rows.append({k: (v or "").strip() for k, v in row.items() if k is not None})
    return rows


def _to_int(value: str) -> int:
    """Parse an integer from a CSV cell, returning 0 on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize_progress(rows: list[dict[str, str]]) -> dict[str, object]:
    """Summarise per-class annotation progress from ``annotation_progress.csv``.

    Args:
        rows: Parsed data rows.

    Returns:
        A JSON-serialisable progress summary.
    """
    classes: list[dict[str, object]] = []
    total_annotated = 0
    total_min_target = 0
    for row in rows:
        annotated = _to_int(row.get("annotated", "0"))
        min_target = _to_int(row.get("min_target", "0"))
        total_annotated += annotated
        total_min_target += min_target
        classes.append(
            {
                "class_id": _to_int(row.get("class_id", "0")),
                "class_name": row.get("class_name", ""),
                "annotated": annotated,
                "min_target": min_target,
                "recommended_target": _to_int(row.get("recommended_target", "0")),
                "status": row.get("status", ""),
            }
        )
    pct = (
        round(100 * total_annotated / total_min_target, 1)
        if total_min_target
        else 0.0
    )
    return {
        "classes": classes,
        "total_annotated": total_annotated,
        "total_min_target": total_min_target,
        "min_target_pct": pct,
    }


def summarize_review(rows: list[dict[str, str]]) -> dict[str, object]:
    """Summarise review events from ``annotation_review.csv``.

    Args:
        rows: Parsed data rows.

    Returns:
        A JSON-serialisable review summary (counts by stage and disposition).
    """
    by_stage: dict[str, int] = {}
    by_disposition: dict[str, int] = {}
    for row in rows:
        stage = row.get("review_stage", "") or "unknown"
        disp = row.get("disposition", "") or "unknown"
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_disposition[disp] = by_disposition.get(disp, 0) + 1
    return {
        "total_events": len(rows),
        "by_stage": dict(sorted(by_stage.items())),
        "by_disposition": dict(sorted(by_disposition.items())),
    }


def summarize_qa(rows: list[dict[str, str]]) -> dict[str, object]:
    """Summarise QA runs from ``qa_report.csv``, surfacing failures.

    Args:
        rows: Parsed data rows.

    Returns:
        A JSON-serialisable QA summary with the failing batches listed.
    """
    passed = 0
    failures: list[dict[str, str]] = []
    for row in rows:
        verdict = row.get("qa_verdict", "")
        if verdict == "qa_pass":
            passed += 1
        else:
            failures.append(
                {
                    "batch_id": row.get("batch_id", ""),
                    "verdict": verdict,
                    "notes": row.get("notes", ""),
                }
            )
    return {
        "total_runs": len(rows),
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


def build_dashboard(
    *,
    images_root: Path,
    labels_root: Path,
    progress_csv: Path | None,
    review_csv: Path | None,
    qa_csv: Path | None,
) -> dict[str, object]:
    """Assemble every dashboard section into one JSON-serialisable payload.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO ``.txt`` labels.
        progress_csv: Optional ``annotation_progress.csv``.
        review_csv: Optional ``annotation_review.csv``.
        qa_csv: Optional ``qa_report.csv``.

    Returns:
        A JSON-serialisable dashboard document.
    """
    report = validate(images_root=images_root, labels_root=labels_root)
    validation = report_to_dict(
        report, images_root=images_root, labels_root=labels_root
    )
    stats = build_statistics(
        images_root=images_root,
        labels_root=labels_root,
        bins=10,
        many_threshold=10,
    )
    core = stats["core"]
    assert isinstance(core, dict)

    return {
        "validation_summary": validation["summary"],
        "issue_counts_by_code": validation["issue_counts_by_code"],
        "class_distribution": core["class_distribution"],
        "missing_labels": {
            "images_without_labels": list(core["images_without_labels"]),
            "count": len(core["images_without_labels"]),
        },
        "missing_classes": list(core["missing_classes"]),
        "progress": summarize_progress(
            _read_csv_rows(progress_csv) if progress_csv else []
        ),
        "review": summarize_review(_read_csv_rows(review_csv) if review_csv else []),
        "qa": summarize_qa(_read_csv_rows(qa_csv) if qa_csv else []),
    }


def render_markdown(dash: dict[str, object]) -> str:
    """Render the dashboard payload as Markdown (ASCII only)."""
    val = dash["validation_summary"]
    assert isinstance(val, dict)
    progress = dash["progress"]
    assert isinstance(progress, dict)
    review = dash["review"]
    assert isinstance(review, dict)
    qa = dash["qa"]
    assert isinstance(qa, dict)

    verdict = "PASS" if val["is_valid"] else "FAIL"
    lines = [
        "# Dataset v1.0 - Annotation Dashboard",
        "",
        "## Validation summary",
        "",
        f"- Verdict: **{verdict}**",
        f"- Label files: {val['total_labels']}",
        f"- Bounding boxes: {val['total_boxes']}",
        f"- Images without labels: {val['images_without_labels']}",
        f"- Orphan labels: {val['labels_without_images']}",
        f"- Empty labels: {val['empty_labels']}",
        f"- Total issues: {val['issue_count']}",
        "",
        "## Annotation progress",
        "",
        f"- Annotated: {progress['total_annotated']} / "
        f"{progress['total_min_target']} min target "
        f"({progress['min_target_pct']}%)",
        "",
    ]
    prog_classes = progress["classes"]
    assert isinstance(prog_classes, list)
    if prog_classes:
        lines.append("| ID | Class | Annotated | Min | Status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in prog_classes:
            assert isinstance(row, dict)
            lines.append(
                f"| {row['class_id']} | {row['class_name']} | "
                f"{row['annotated']} | {row['min_target']} | {row['status']} |"
            )
    else:
        lines.append("No progress CSV supplied.")

    lines.extend(
        [
            "",
            "## Class distribution",
            "",
            "| ID | Class | Count |",
            "| --- | --- | --- |",
        ]
    )
    dist = dash["class_distribution"]
    assert isinstance(dist, list)
    for entry in dist:
        assert isinstance(entry, dict)
        lines.append(
            f"| {entry['class_id']} | {entry['class_name']} | {entry['count']} |"
        )

    missing = dash["missing_labels"]
    assert isinstance(missing, dict)
    lines.extend(
        [
            "",
            "## Missing labels",
            "",
            f"- Images without labels: {missing['count']}",
            f"- Missing classes: {', '.join(dash['missing_classes']) or 'none'}",
            "",
            "## Review status",
            "",
            f"- Review events: {review['total_events']}",
            f"- By stage: {json.dumps(review['by_stage'], sort_keys=True)}",
            f"- By disposition: {json.dumps(review['by_disposition'], sort_keys=True)}",
            "",
            "## QA failures",
            "",
            f"- QA runs: {qa['total_runs']} "
            f"(passed {qa['passed']}, failed {qa['failed']})",
            "",
        ]
    )
    failures = qa["failures"]
    assert isinstance(failures, list)
    if failures:
        lines.append("| Batch | Verdict | Notes |")
        lines.append("| --- | --- | --- |")
        for row in failures:
            assert isinstance(row, dict)
            lines.append(f"| {row['batch_id']} | {row['verdict']} | {row['notes']} |")
    else:
        lines.append("No QA failures.")
    lines.append("")
    return "\n".join(lines)


def _html_table(headers: list[str], rows: list[list[object]]) -> str:
    """Return an HTML table with every cell escaped."""
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(dash: dict[str, object]) -> str:
    """Render the dashboard payload as a self-contained HTML document."""
    val = dash["validation_summary"]
    assert isinstance(val, dict)
    progress = dash["progress"]
    assert isinstance(progress, dict)
    review = dash["review"]
    assert isinstance(review, dict)
    qa = dash["qa"]
    assert isinstance(qa, dict)
    dist = dash["class_distribution"]
    assert isinstance(dist, list)
    missing = dash["missing_labels"]
    assert isinstance(missing, dict)

    verdict = "PASS" if val["is_valid"] else "FAIL"
    verdict_color = "#137333" if val["is_valid"] else "#c5221f"

    prog_classes = progress["classes"]
    assert isinstance(prog_classes, list)
    progress_table = (
        _html_table(
            ["ID", "Class", "Annotated", "Min", "Status"],
            [
                [
                    r["class_id"],
                    r["class_name"],
                    r["annotated"],
                    r["min_target"],
                    r["status"],
                ]
                for r in prog_classes
            ],
        )
        if prog_classes
        else "<p>No progress CSV supplied.</p>"
    )
    dist_table = _html_table(
        ["ID", "Class", "Count"],
        [[e["class_id"], e["class_name"], e["count"]] for e in dist],
    )
    failures = qa["failures"]
    assert isinstance(failures, list)
    qa_table = (
        _html_table(
            ["Batch", "Verdict", "Notes"],
            [[r["batch_id"], r["verdict"], r["notes"]] for r in failures],
        )
        if failures
        else "<p>No QA failures.</p>"
    )

    style = (
        "body{font-family:system-ui,Arial,sans-serif;margin:2rem;max-width:60rem}"
        "table{border-collapse:collapse;margin:0.5rem 0}"
        "th,td{border:1px solid #ccc;padding:0.3rem 0.6rem;text-align:left}"
        "th{background:#f2f2f2}h1{margin-bottom:0.2rem}"
        ".verdict{font-weight:bold}"
    )
    missing_classes = ", ".join(dash["missing_classes"]) or "none"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Dataset v1.0 Annotation Dashboard</title>"
        f"<style>{style}</style></head><body>"
        "<h1>Dataset v1.0 &mdash; Annotation Dashboard</h1>"
        "<h2>Validation summary</h2>"
        f"<p class='verdict' style='color:{verdict_color}'>Verdict: {verdict}</p>"
        f"<p>Label files: {val['total_labels']} &middot; "
        f"Bounding boxes: {val['total_boxes']} &middot; "
        f"Images without labels: {val['images_without_labels']} &middot; "
        f"Orphan labels: {val['labels_without_images']} &middot; "
        f"Empty labels: {val['empty_labels']} &middot; "
        f"Total issues: {val['issue_count']}</p>"
        "<h2>Annotation progress</h2>"
        f"<p>Annotated: {progress['total_annotated']} / "
        f"{progress['total_min_target']} min target "
        f"({progress['min_target_pct']}%)</p>" + progress_table
        + "<h2>Class distribution</h2>" + dist_table
        + "<h2>Missing labels</h2>"
        f"<p>Images without labels: {missing['count']} &middot; "
        f"Missing classes: {html.escape(missing_classes)}</p>"
        "<h2>Review status</h2>"
        f"<p>Review events: {review['total_events']} &middot; "
        f"By stage: "
        f"{html.escape(json.dumps(review['by_stage'], sort_keys=True))} &middot; "
        f"By disposition: "
        f"{html.escape(json.dumps(review['by_disposition'], sort_keys=True))}</p>"
        "<h2>QA failures</h2>"
        f"<p>QA runs: {qa['total_runs']} (passed {qa['passed']}, "
        f"failed {qa['failed']})</p>" + qa_table
        + "</body></html>"
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Render a Dataset v1.0 annotation dashboard (HTML + Markdown).",
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
        "--progress-csv",
        type=Path,
        default=None,
        help="Optional annotation_progress.csv for per-class progress.",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=None,
        help="Optional annotation_review.csv for review status.",
    )
    parser.add_argument(
        "--qa-csv",
        type=Path,
        default=None,
        help="Optional qa_report.csv for QA failures.",
    )
    parser.add_argument(
        "--html-out",
        type=Path,
        default=None,
        help="Optional path to write the HTML dashboard.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path to write the Markdown dashboard.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the raw dashboard data as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the annotation dashboard.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return 2
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return 2

    dash = build_dashboard(
        images_root=args.images_root,
        labels_root=args.labels_root,
        progress_csv=args.progress_csv,
        review_csv=args.review_csv,
        qa_csv=args.qa_csv,
    )
    markdown = render_markdown(dash)
    html_doc = render_html(dash)

    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(markdown, encoding="utf-8")
    if args.html_out is not None:
        args.html_out.parent.mkdir(parents=True, exist_ok=True)
        args.html_out.write_text(html_doc + "\n", encoding="utf-8")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(dash, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

