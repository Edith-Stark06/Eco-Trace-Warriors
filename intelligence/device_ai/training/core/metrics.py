"""Pure-NumPy classification metrics for the training platform (milestone M1.3).

These helpers compute the standard classification metrics — accuracy, a
confusion matrix and macro/micro/weighted precision, recall and F1 — using only
NumPy, so evaluation works in the base environment with no ML framework
installed. They are deliberately framework-agnostic: every future model
(condition classifier, material estimator, …) feeds integer label arrays in and
gets primitive floats out, ready to embed in an experiment record or report.

:func:`mean_average_precision` is an honest *placeholder*: it averages
already-computed per-class average-precision values (a correct, model-agnostic
operation). The detection-specific per-class AP computation — IoU matching of
predicted and ground-truth boxes — is deferred to the detector milestone and is
intentionally **not** implemented here (no model ships in M1.3).

:class:`MetricTracker` accumulates named scalar metrics across the steps of an
epoch and reports their running averages, which is exactly what the trainer's
``fit()`` loop needs to aggregate per-step losses and metrics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

#: Accepted label containers: a Python sequence of ints or a NumPy array.
Labels = Sequence[int] | NDArray[Any]

#: Averaging strategies supported when reducing per-class metrics to a scalar.
_AVERAGES = ("macro", "micro", "weighted")


def _as_label_array(values: Labels, *, name: str) -> NDArray[np.int64]:
    """Return ``values`` as a flat non-negative int64 array.

    Args:
        values: A sequence or array of integer class labels.
        name: Argument name, used only for error messages.

    Returns:
        A one-dimensional ``int64`` array.

    Raises:
        ValueError: If any label is negative.
    """
    array = np.asarray(values, dtype=np.int64).ravel()
    if array.size and int(array.min()) < 0:
        raise ValueError(f"{name} must contain non-negative class labels")
    return array


def _safe_divide(
    numerator: NDArray[np.float64], denominator: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Element-wise divide, yielding ``0.0`` wherever the denominator is zero.

    Args:
        numerator: Dividend array.
        denominator: Divisor array; zeros map the result to ``0.0``.

    Returns:
        The quotient with divide-by-zero positions set to ``0.0``.
    """
    return np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator, dtype=np.float64),
        where=denominator != 0,
    )


def accuracy(y_true: Labels, y_pred: Labels) -> float:
    """Return the fraction of predictions that exactly match the labels.

    Args:
        y_true: Ground-truth class labels.
        y_pred: Predicted class labels (same length as ``y_true``).

    Returns:
        Accuracy in ``[0, 1]``; ``0.0`` for empty input.

    Raises:
        ValueError: If the inputs differ in length.
    """
    yt = _as_label_array(y_true, name="y_true")
    yp = _as_label_array(y_pred, name="y_pred")
    if yt.shape != yp.shape:
        raise ValueError(
            f"y_true and y_pred must have the same length, "
            f"got {yt.size} and {yp.size}"
        )
    if yt.size == 0:
        return 0.0
    return float(np.mean(yt == yp))


def confusion_matrix(
    y_true: Labels, y_pred: Labels, *, num_classes: int | None = None
) -> NDArray[np.int64]:
    """Return the confusion matrix with true labels as rows, predictions as cols.

    Args:
        y_true: Ground-truth class labels.
        y_pred: Predicted class labels (same length as ``y_true``).
        num_classes: Number of classes; inferred from the data (``max + 1``)
            when ``None``.

    Returns:
        An ``(num_classes, num_classes)`` ``int64`` matrix where entry
        ``[t, p]`` counts samples of true class ``t`` predicted as ``p``.

    Raises:
        ValueError: If the inputs differ in length, contain negative labels, or
            exceed an explicitly supplied ``num_classes``.
    """
    yt = _as_label_array(y_true, name="y_true")
    yp = _as_label_array(y_pred, name="y_pred")
    if yt.shape != yp.shape:
        raise ValueError(
            f"y_true and y_pred must have the same length, "
            f"got {yt.size} and {yp.size}"
        )

    inferred = int(max(yt.max(initial=-1), yp.max(initial=-1))) + 1
    if num_classes is None:
        num_classes = inferred
    elif num_classes < inferred:
        raise ValueError(
            f"num_classes={num_classes} is too small for labels up to "
            f"{inferred - 1}"
        )
    size = max(num_classes, 1)

    matrix = np.zeros((size, size), dtype=np.int64)
    if yt.size:
        np.add.at(matrix, (yt, yp), 1)
    return matrix


def _per_class_prf(
    matrix: NDArray[np.int64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return per-class precision, recall and F1 arrays from a confusion matrix.

    Args:
        matrix: A square confusion matrix (rows = true, cols = predicted).

    Returns:
        A ``(precision, recall, f1)`` tuple of per-class ``float64`` arrays.
    """
    true_positives = np.diag(matrix).astype(np.float64)
    predicted = matrix.sum(axis=0).astype(np.float64)
    actual = matrix.sum(axis=1).astype(np.float64)
    precision = _safe_divide(true_positives, predicted)
    recall = _safe_divide(true_positives, actual)
    f1 = _safe_divide(2.0 * precision * recall, precision + recall)
    return precision, recall, f1


def precision_recall_f1(
    y_true: Labels,
    y_pred: Labels,
    *,
    num_classes: int | None = None,
    average: str = "macro",
) -> tuple[float, float, float]:
    """Return scalar precision, recall and F1 under the chosen averaging.

    Args:
        y_true: Ground-truth class labels.
        y_pred: Predicted class labels.
        num_classes: Number of classes (inferred when ``None``).
        average: One of ``"macro"`` (unweighted class mean), ``"micro"``
            (global counts) or ``"weighted"`` (support-weighted class mean).

    Returns:
        A ``(precision, recall, f1)`` tuple of floats in ``[0, 1]``.

    Raises:
        ValueError: If ``average`` is not a recognised strategy.
    """
    if average not in _AVERAGES:
        raise ValueError(f"average must be one of {_AVERAGES}, got {average!r}")

    matrix = confusion_matrix(y_true, y_pred, num_classes=num_classes)
    if matrix.sum() == 0:
        return 0.0, 0.0, 0.0

    if average == "micro":
        true_positives = float(np.trace(matrix))
        total = float(matrix.sum())
        # For single-label classification micro-P == micro-R == accuracy.
        value = true_positives / total if total else 0.0
        return value, value, value

    precision, recall, f1 = _per_class_prf(matrix)
    if average == "weighted":
        support = matrix.sum(axis=1).astype(np.float64)
        weights = _safe_divide(support, np.full_like(support, support.sum()))
        return (
            float(np.sum(precision * weights)),
            float(np.sum(recall * weights)),
            float(np.sum(f1 * weights)),
        )

    # "macro": unweighted mean across classes.
    return float(np.mean(precision)), float(np.mean(recall)), float(np.mean(f1))


def precision_score(
    y_true: Labels,
    y_pred: Labels,
    *,
    num_classes: int | None = None,
    average: str = "macro",
) -> float:
    """Return precision only (see :func:`precision_recall_f1`)."""
    return precision_recall_f1(
        y_true, y_pred, num_classes=num_classes, average=average
    )[0]


def recall_score(
    y_true: Labels,
    y_pred: Labels,
    *,
    num_classes: int | None = None,
    average: str = "macro",
) -> float:
    """Return recall only (see :func:`precision_recall_f1`)."""
    return precision_recall_f1(
        y_true, y_pred, num_classes=num_classes, average=average
    )[1]


def f1_score(
    y_true: Labels,
    y_pred: Labels,
    *,
    num_classes: int | None = None,
    average: str = "macro",
) -> float:
    """Return the F1 score only (see :func:`precision_recall_f1`)."""
    return precision_recall_f1(
        y_true, y_pred, num_classes=num_classes, average=average
    )[2]


def mean_average_precision(per_class_ap: Sequence[float] | None = None) -> float:
    """Return the mean of already-computed per-class average-precision values.

    This is a deliberate placeholder for the detection milestone. Computing each
    class's average precision requires IoU matching of predicted and
    ground-truth boxes, which is model-specific and out of scope for M1.3;
    supplying those AP values here yields their mean (the "mAP"). With no values
    the metric is a well-defined ``0.0``.

    Args:
        per_class_ap: Optional per-class average-precision values in ``[0, 1]``.

    Returns:
        The mean average precision, or ``0.0`` when no values are supplied.
    """
    if not per_class_ap:
        return 0.0
    values = np.asarray(list(per_class_ap), dtype=np.float64)
    return float(values.mean())


def classification_metrics(
    y_true: Labels,
    y_pred: Labels,
    *,
    num_classes: int | None = None,
    average: str = "macro",
) -> dict[str, float]:
    """Return the standard classification metrics as a primitive-only mapping.

    A convenience aggregate used by the evaluator: it bundles accuracy together
    with averaged precision, recall and F1 into one JSON-ready dict.

    Args:
        y_true: Ground-truth class labels.
        y_pred: Predicted class labels.
        num_classes: Number of classes (inferred when ``None``).
        average: Averaging strategy for precision/recall/F1.

    Returns:
        A mapping with keys ``accuracy``, ``precision``, ``recall`` and ``f1``.
    """
    precision, recall, f1 = precision_recall_f1(
        y_true, y_pred, num_classes=num_classes, average=average
    )
    return {
        "accuracy": accuracy(y_true, y_pred),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


class MetricTracker:
    """Accumulate named scalar metrics and report their running averages.

    The trainer updates a tracker once per training/validation step and reads
    :meth:`averages` at the end of each epoch, then :meth:`reset` for the next.
    Values are weighted by an optional ``count`` (e.g. the batch size) so an
    average over unequal batches remains correct.
    """

    def __init__(self) -> None:
        self._sums: dict[str, float] = {}
        self._counts: dict[str, float] = {}

    def update(self, name: str, value: float, *, count: float = 1.0) -> None:
        """Add a single observation of a metric.

        Args:
            name: Metric identifier (e.g. ``"loss"``).
            value: Observed value for this step.
            count: Weight of the observation (e.g. the batch size); must be
                positive.

        Raises:
            ValueError: If ``count`` is not positive.
        """
        if count <= 0:
            raise ValueError(f"count must be positive, got {count}")
        self._sums[name] = self._sums.get(name, 0.0) + float(value) * count
        self._counts[name] = self._counts.get(name, 0.0) + count

    def update_many(self, metrics: Mapping[str, float], *, count: float = 1.0) -> None:
        """Update several metrics at once.

        Args:
            metrics: Mapping of metric name → observed value.
            count: Shared weight applied to every observation.
        """
        for name, value in metrics.items():
            self.update(name, value, count=count)

    def average(self, name: str) -> float:
        """Return the running average of one metric.

        Args:
            name: Metric identifier.

        Returns:
            The weighted mean, or ``0.0`` if the metric was never updated.
        """
        total = self._counts.get(name, 0.0)
        if total == 0.0:
            return 0.0
        return self._sums[name] / total

    def averages(self) -> dict[str, float]:
        """Return the running average of every tracked metric.

        Returns:
            A mapping of metric name → weighted mean (insertion order).
        """
        return {name: self.average(name) for name in self._sums}

    def reset(self) -> None:
        """Discard all accumulated observations."""
        self._sums.clear()
        self._counts.clear()

    @property
    def names(self) -> tuple[str, ...]:
        """The names of every metric seen since the last :meth:`reset`."""
        return tuple(self._sums)

    def __contains__(self, name: object) -> bool:
        """Return whether ``name`` has been observed at least once."""
        return name in self._sums
