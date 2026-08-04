"""Detection evaluation: Ultralytics metrics → platform report (milestone M1.4).

Ultralytics' ``model.val()`` returns a rich metrics object (a ``DetMetrics``);
:class:`DetectionEvaluator` distils it into the *same* evaluation document the
training platform already produces for classification models
(:func:`~device_ai.training.core.evaluator.build_evaluation_document`) and
renders it with the *same* HTML template
(:class:`~device_ai.training.core.evaluator.Evaluator`). Nothing about the
report surface is duplicated — only the detection-specific *extraction* of mAP /
precision / recall / F1 and the confusion matrix lives here.

The extractors are pure and defensive: they read from the metrics object's
``results_dict`` (Ultralytics' stable public mapping) with attribute fallbacks,
so they can be unit-tested with a tiny fake in the base environment — no torch,
no Ultralytics, no trained weights.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..core.evaluator import Evaluator, build_evaluation_document

#: Friendly metric name → the Ultralytics ``results_dict`` keys it may appear
#: under (newest key first). Detection metrics are suffixed ``(B)`` for the
#: bounding-box task in recent Ultralytics releases.
_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "precision": ("metrics/precision(B)", "metrics/precision"),
    "recall": ("metrics/recall(B)", "metrics/recall"),
    "mAP50": ("metrics/mAP50(B)", "metrics/mAP50", "metrics/mAP_0.5"),
    "mAP50_95": (
        "metrics/mAP50-95(B)",
        "metrics/mAP50-95",
        "metrics/mAP_0.5:0.95",
    ),
}

#: Attribute fallbacks on the metrics object's ``box`` member, used when the
#: corresponding ``results_dict`` key is absent.
_BOX_FALLBACKS: dict[str, str] = {
    "precision": "mp",
    "recall": "mr",
    "mAP50": "map50",
    "mAP50_95": "map",
}

#: Extra class appended by Ultralytics' confusion matrix (predicted/true
#: background), reported when the matrix is one larger than the class list.
_BACKGROUND_CLASS = "background"


def _metric_source(results: Any) -> Mapping[str, Any]:
    """Return the metric mapping from a val result or a plain mapping.

    Args:
        results: An Ultralytics metrics object (with ``results_dict``) or a
            plain mapping of metric name → value.

    Returns:
        The underlying metric mapping (empty when none is available).
    """
    source = getattr(results, "results_dict", None)
    if source is None and isinstance(results, Mapping):
        source = results
    return source or {}


def extract_metrics(results: Any) -> dict[str, float]:
    """Extract precision/recall/mAP/F1 from an Ultralytics val result.

    Args:
        results: The object returned by ``model.val()`` (or a compatible fake /
            plain mapping).

    Returns:
        A metric mapping with friendly keys (``precision``, ``recall``,
        ``mAP50``, ``mAP50_95`` and a derived ``f1``); absent metrics are
        simply omitted.
    """
    source = _metric_source(results)
    box = getattr(results, "box", None)
    metrics: dict[str, float] = {}
    for friendly, aliases in _METRIC_ALIASES.items():
        value = next((source[key] for key in aliases if key in source), None)
        if value is None and box is not None:
            value = getattr(box, _BOX_FALLBACKS[friendly], None)
        if value is not None:
            metrics[friendly] = round(float(value), 4)

    precision = metrics.get("precision")
    recall = metrics.get("recall")
    if precision is not None and recall is not None:
        denominator = precision + recall
        metrics["f1"] = (
            round(2 * precision * recall / denominator, 4) if denominator else 0.0
        )
    return metrics


def extract_confusion(results: Any) -> NDArray[np.int64] | None:
    """Extract the confusion matrix from an Ultralytics val result.

    Args:
        results: The object returned by ``model.val()`` (or a compatible fake).

    Returns:
        The confusion matrix as an integer array, or ``None`` when the result
        exposes none.
    """
    confusion = getattr(results, "confusion_matrix", None)
    matrix = getattr(confusion, "matrix", None) if confusion is not None else None
    if matrix is None:
        return None
    return np.asarray(matrix).round().astype(np.int64)


def names_to_list(names: Any) -> list[str] | None:
    """Normalise an Ultralytics ``names`` mapping/sequence to an ordered list.

    Args:
        names: A ``{index: name}`` mapping, a sequence of names, or ``None``.

    Returns:
        Class names ordered by index, or ``None`` when ``names`` is empty.
    """
    if not names:
        return None
    if isinstance(names, Mapping):
        return [str(names[key]) for key in sorted(names)]
    return [str(name) for name in names]


def _align_labels(
    class_names: list[str] | None, confusion: NDArray[np.int64] | None
) -> list[str] | None:
    """Extend class names with a background row/col when the matrix is larger.

    Ultralytics' confusion matrix has an extra ``background`` row and column, so
    it is one wider than the class list. Appending the background label keeps the
    confusion-matrix axes aligned in the rendered report.

    Args:
        class_names: The model's class names (or ``None``).
        confusion: The extracted confusion matrix (or ``None``).

    Returns:
        The (possibly extended) class-name list, or ``None`` when unavailable.
    """
    if class_names is None or confusion is None:
        return class_names
    if confusion.shape[0] == len(class_names) + 1:
        return [*class_names, _BACKGROUND_CLASS]
    return class_names


class DetectionEvaluator:
    """Build detection evaluation documents and render them to HTML.

    A thin adapter over the shared evaluation surface: it extracts detection
    metrics/confusion from an Ultralytics val result and defers document
    assembly and HTML rendering to the platform's
    :func:`~device_ai.training.core.evaluator.build_evaluation_document` and
    :class:`~device_ai.training.core.evaluator.Evaluator`.
    """

    def __init__(self) -> None:
        self._renderer = Evaluator()

    def build_document(
        self,
        *,
        model_name: str,
        model_version: str,
        results: Any,
        generated_at: datetime,
        class_names: Any = None,
        dataset_version: str = "",
        num_samples: int = 0,
    ) -> dict[str, object]:
        """Assemble the detection evaluation document from a val result.

        Args:
            model_name: Logical model name under evaluation.
            model_version: Version tag of the evaluated artifact.
            results: The object returned by ``model.val()`` (or a fake).
            generated_at: Timestamp to embed (injected for reproducibility).
            class_names: The model's class names (mapping/sequence/``None``).
            dataset_version: Dataset snapshot the evaluation ran against.
            num_samples: Number of validation images the metrics cover.

        Returns:
            A JSON-serialisable evaluation document.
        """
        metrics = extract_metrics(results)
        confusion = extract_confusion(results)
        labels = _align_labels(names_to_list(class_names), confusion)
        return build_evaluation_document(
            model_name=model_name,
            model_version=model_version,
            metrics=metrics,
            confusion=confusion,
            class_names=labels,
            generated_at=generated_at,
            dataset_version=dataset_version,
            num_samples=num_samples,
        )

    def to_html(self, document: dict[str, object]) -> str:
        """Render a detection evaluation document as self-contained HTML.

        Args:
            document: A document produced by :meth:`build_document`.

        Returns:
            A complete HTML string (inline CSS, no JavaScript).
        """
        return self._renderer.to_html(document)
