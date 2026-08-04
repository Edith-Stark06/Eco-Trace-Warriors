"""Dataset report generation (JSON + HTML).

:class:`ReportBuilder` assembles a single report document from the dataset's
statistics, duplicate report and annotation report, then renders it either as
JSON (machine-readable) or a self-contained HTML page (human-readable, no
external assets or JavaScript).

The builder is pure: it takes already-computed value objects and a timestamp
(injected for reproducibility) and returns strings. Persisting the output is
left to the dataset service.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from .records import AnnotationReport, DatasetStatistics, DuplicateReport
from .statistics import statistics_to_dict


def build_report_document(
    *,
    statistics: DatasetStatistics,
    duplicates: DuplicateReport | None,
    annotations: AnnotationReport | None,
    generated_at: datetime,
    source: str,
) -> dict[str, object]:
    """Assemble the combined report document.

    Args:
        statistics: The dataset statistics snapshot.
        duplicates: Optional duplicate-detection result.
        annotations: Optional annotation-validation result.
        generated_at: Timestamp to embed (injected for reproducibility).
        source: Human-readable source identifier.

    Returns:
        A JSON-serialisable report document.
    """
    document: dict[str, object] = {
        "source": source,
        "generated_at": generated_at.isoformat(),
        "statistics": statistics_to_dict(statistics),
    }
    if duplicates is not None:
        document["duplicates"] = {
            "total_images": duplicates.total_images,
            "num_duplicates": duplicates.num_duplicates,
            "num_unique": duplicates.num_unique,
            "pairs": [
                {
                    "source": pair.source,
                    "duplicate": pair.duplicate,
                    "distance": pair.distance,
                    "exact": pair.exact,
                }
                for pair in duplicates.pairs
            ],
        }
    if annotations is not None:
        document["annotations"] = {
            "total_labels": annotations.total_labels,
            "total_boxes": annotations.total_boxes,
            "is_valid": annotations.is_valid,
            "class_counts": annotations.class_counts,
            "images_without_labels": list(annotations.images_without_labels),
            "labels_without_images": list(annotations.labels_without_images),
            "issues": [
                {
                    "file": issue.file,
                    "line": issue.line,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in annotations.issues
            ],
        }
    return document


def _table(rows: list[tuple[str, object]]) -> str:
    """Render a two-column key/value HTML table body."""
    cells = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in rows
    )
    return f"<table>{cells}</table>"


class ReportBuilder:
    """Render report documents to JSON-ready dicts and HTML."""

    def build(
        self,
        *,
        statistics: DatasetStatistics,
        duplicates: DuplicateReport | None,
        annotations: AnnotationReport | None,
        generated_at: datetime,
        source: str,
    ) -> dict[str, object]:
        """Assemble the combined report document (see module function).

        Args:
            statistics: The dataset statistics snapshot.
            duplicates: Optional duplicate-detection result.
            annotations: Optional annotation-validation result.
            generated_at: Timestamp to embed.
            source: Human-readable source identifier.

        Returns:
            A JSON-serialisable report document.
        """
        return build_report_document(
            statistics=statistics,
            duplicates=duplicates,
            annotations=annotations,
            generated_at=generated_at,
            source=source,
        )

    def to_html(self, document: dict[str, object]) -> str:
        """Render a report document as a self-contained HTML page.

        Args:
            document: A document produced by :meth:`build`.

        Returns:
            A complete HTML string.
        """
        stats = document.get("statistics", {})
        assert isinstance(stats, dict)
        quality = stats.get("quality", {})
        assert isinstance(quality, dict)

        sections: list[str] = []
        sections.append(
            _table(
                [
                    ("Source", document.get("source", "")),
                    ("Generated at", document.get("generated_at", "")),
                    ("Total images", stats.get("total_images", 0)),
                    ("Total size (MB)", stats.get("total_size_mb", 0)),
                ]
            )
        )
        sections.append("<h2>Quality</h2>")
        sections.append(
            _table(
                [
                    ("Blurry", quality.get("blurry", 0)),
                    ("Dark", quality.get("dark", 0)),
                    ("Bright", quality.get("bright", 0)),
                    ("Low resolution", quality.get("low_resolution", 0)),
                    ("Corrupted", quality.get("corrupted", 0)),
                    ("Mean blur score", quality.get("mean_blur_score", 0)),
                    ("Mean brightness", quality.get("mean_brightness", 0)),
                ]
            )
        )
        sections.append("<h2>Formats</h2>")
        sections.append(_table(list(dict(stats.get("format_counts", {})).items())))

        duplicates = document.get("duplicates")
        if isinstance(duplicates, dict):
            sections.append("<h2>Duplicates</h2>")
            sections.append(
                _table(
                    [
                        ("Total images", duplicates.get("total_images", 0)),
                        ("Duplicates", duplicates.get("num_duplicates", 0)),
                        ("Unique", duplicates.get("num_unique", 0)),
                    ]
                )
            )

        annotations = document.get("annotations")
        if isinstance(annotations, dict):
            sections.append("<h2>Annotations</h2>")
            sections.append(
                _table(
                    [
                        ("Total labels", annotations.get("total_labels", 0)),
                        ("Total boxes", annotations.get("total_boxes", 0)),
                        ("Valid", annotations.get("is_valid", False)),
                        (
                            "Issues",
                            len(annotations.get("issues", [])),  # type: ignore[arg-type]
                        ),
                    ]
                )
            )

        body = "\n".join(sections)
        return _HTML_TEMPLATE.format(body=body)


# Minimal, dependency-free HTML shell with inline styling.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EcoTrace DIE — Dataset Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ color: #0b6b3a; }}
  h2 {{ margin-top: 1.5rem; color: #0b6b3a; }}
  table {{ border-collapse: collapse; margin: 0.5rem 0; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 10px; text-align: left; }}
  th {{ background: #f0f7f2; }}
</style>
</head>
<body>
<h1>Dataset Intelligence Report</h1>
{body}
</body>
</html>
"""
