"""Model evaluation reporting for the training platform (milestone M1.3).

:class:`Evaluator` turns a set of predictions (or pre-computed metrics) into a
single evaluation document and renders it as machine-readable JSON and a
self-contained HTML page — no external assets, no JavaScript — mirroring
:class:`~device_ai.dataset.reporting.ReportBuilder`.

A report has three sections:

* **Metrics summary** — accuracy plus averaged precision / recall / F1 and mAP.
* **Confusion matrix** — an HTML table (true rows × predicted columns).
* **Inference benchmark** — a *placeholder* section. Real latency/throughput
  numbers require an executing model, which does not exist in M1.3; the
  evaluator records a clearly-labelled placeholder so the report shape is final
  and future trainers only need to fill in real numbers.

The builder is pure: it consumes value objects / arrays and an injected
timestamp and returns a dict and a string. Persisting the output is the caller's
responsibility (e.g. the CLI via :class:`ArtifactManager`).
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import numpy as np
from numpy.typing import NDArray

from . import metrics as metric_utils
from .metrics import Labels


def build_benchmark_placeholder() -> dict[str, Any]:
    """Return the inference-benchmark placeholder section.

    The real benchmark (latency percentiles, throughput, device) requires an
    executing model and is deferred to the model-implementation milestones. The
    placeholder fixes the report's shape and is explicitly flagged so no reader
    mistakes it for a measured result.

    Returns:
        A primitive-only mapping describing an unmeasured benchmark.
    """
    return {
        "status": "placeholder",
        "note": (
            "Inference benchmarking is deferred to model implementation; no "
            "model is trained in this milestone."
        ),
        "latency_ms": None,
        "throughput_fps": None,
        "device": "",
        "batch_size": None,
    }


def build_evaluation_document(
    *,
    model_name: str,
    model_version: str,
    metrics: dict[str, float],
    confusion: NDArray[np.int64] | None,
    class_names: list[str] | None,
    generated_at: datetime,
    dataset_version: str = "",
    benchmark: dict[str, Any] | None = None,
    num_samples: int = 0,
) -> dict[str, object]:
    """Assemble the combined evaluation document.

    Args:
        model_name: Logical model name under evaluation.
        model_version: Version tag of the evaluated artifact.
        metrics: Scalar metric mapping (accuracy/precision/recall/f1/…).
        confusion: Optional confusion matrix (true rows × predicted columns).
        class_names: Optional labels for the confusion-matrix axes.
        generated_at: Timestamp to embed (injected for reproducibility).
        dataset_version: Dataset snapshot the evaluation ran against.
        benchmark: Optional benchmark section; defaults to the placeholder.
        num_samples: Number of samples the metrics were computed over.

    Returns:
        A JSON-serialisable evaluation document.
    """
    document: dict[str, object] = {
        "model_name": model_name,
        "model_version": model_version,
        "dataset_version": dataset_version,
        "generated_at": generated_at.isoformat(),
        "num_samples": num_samples,
        "metrics": {key: float(value) for key, value in metrics.items()},
        "benchmark": (
            benchmark if benchmark is not None else build_benchmark_placeholder()
        ),
    }
    if confusion is not None:
        matrix = np.asarray(confusion, dtype=np.int64)
        labels = class_names or [str(index) for index in range(matrix.shape[0])]
        document["confusion_matrix"] = {
            "labels": labels,
            "matrix": matrix.tolist(),
        }
    return document


def _table(rows: list[tuple[str, object]]) -> str:
    """Render a two-column key/value HTML table."""
    cells = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in rows
    )
    return f"<table>{cells}</table>"


def _confusion_table(confusion: dict[str, Any]) -> str:
    """Render a confusion matrix mapping as an HTML table."""
    labels = [str(label) for label in confusion.get("labels", [])]
    matrix = confusion.get("matrix", [])
    header = "".join(f"<th>{escape(label)}</th>" for label in labels)
    body_rows: list[str] = []
    for label, row in zip(labels, matrix, strict=False):
        data_cells = "".join(f"<td>{escape(str(value))}</td>" for value in row)
        body_rows.append(f"<tr><th>{escape(label)}</th>{data_cells}</tr>")
    body = "".join(body_rows)
    return "<table><tr><th>true \\ pred</th>" f"{header}</tr>{body}</table>"


class Evaluator:
    """Build evaluation documents and render them to JSON-ready dicts and HTML.

    The evaluator computes classification metrics from raw labels (via
    :mod:`device_ai.training.core.metrics`) or accepts pre-computed metrics, then
    renders a self-contained report.
    """

    def evaluate(
        self,
        *,
        model_name: str,
        model_version: str,
        y_true: Labels,
        y_pred: Labels,
        class_names: list[str] | None,
        generated_at: datetime,
        dataset_version: str = "",
        num_classes: int | None = None,
        average: str = "macro",
    ) -> dict[str, object]:
        """Compute metrics from labels and build the evaluation document.

        Args:
            model_name: Logical model name under evaluation.
            model_version: Version tag of the evaluated artifact.
            y_true: Ground-truth class labels.
            y_pred: Predicted class labels.
            class_names: Optional confusion-matrix axis labels.
            generated_at: Timestamp to embed.
            dataset_version: Dataset snapshot the evaluation ran against.
            num_classes: Number of classes (inferred when ``None``).
            average: Averaging strategy for precision/recall/F1.

        Returns:
            A JSON-serialisable evaluation document.
        """
        summary = metric_utils.classification_metrics(
            y_true, y_pred, num_classes=num_classes, average=average
        )
        confusion = metric_utils.confusion_matrix(
            y_true, y_pred, num_classes=num_classes
        )
        num_samples = int(np.asarray(y_true).size)
        return build_evaluation_document(
            model_name=model_name,
            model_version=model_version,
            metrics=summary,
            confusion=confusion,
            class_names=class_names,
            generated_at=generated_at,
            dataset_version=dataset_version,
            num_samples=num_samples,
        )

    def to_html(self, document: dict[str, object]) -> str:
        """Render an evaluation document as a self-contained HTML page.

        Args:
            document: A document produced by :meth:`evaluate` or
                :func:`build_evaluation_document`.

        Returns:
            A complete HTML string (inline CSS, no JavaScript).
        """
        metrics = document.get("metrics", {})
        assert isinstance(metrics, dict)
        benchmark = document.get("benchmark", {})
        assert isinstance(benchmark, dict)

        sections: list[str] = []
        sections.append(
            _table(
                [
                    ("Model", document.get("model_name", "")),
                    ("Version", document.get("model_version", "")),
                    ("Dataset version", document.get("dataset_version", "")),
                    ("Generated at", document.get("generated_at", "")),
                    ("Samples", document.get("num_samples", 0)),
                ]
            )
        )
        sections.append("<h2>Metrics</h2>")
        sections.append(
            _table([(key, round(value, 4)) for key, value in metrics.items()])
        )

        confusion = document.get("confusion_matrix")
        if isinstance(confusion, dict):
            sections.append("<h2>Confusion matrix</h2>")
            sections.append(_confusion_table(confusion))

        sections.append("<h2>Inference benchmark</h2>")
        sections.append(
            _table(
                [
                    ("Status", benchmark.get("status", "")),
                    ("Latency (ms)", benchmark.get("latency_ms", "n/a")),
                    ("Throughput (fps)", benchmark.get("throughput_fps", "n/a")),
                    ("Note", benchmark.get("note", "")),
                ]
            )
        )

        body = "\n".join(sections)
        return _HTML_TEMPLATE.format(body=body)


# Minimal, dependency-free HTML shell with inline styling (shared visual
# language with the dataset report: green EcoTrace theme, no external assets).
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EcoTrace DIE — Evaluation Report</title>
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
<h1>Model Evaluation Report</h1>
{body}
</body>
</html>
"""
