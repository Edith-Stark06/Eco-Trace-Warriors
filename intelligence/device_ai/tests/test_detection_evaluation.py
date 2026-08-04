"""Unit tests for the detection evaluation adapter (milestone M1.4).

The extractors read from an Ultralytics ``model.val()`` result. These tests use
small fakes mirroring that object's public shape (``results_dict``, ``box``,
``confusion_matrix.matrix``) plus a plain-mapping variant, so they run in the
base environment with no torch/Ultralytics.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from device_ai.training.detector.evaluation import (
    DetectionEvaluator,
    extract_confusion,
    extract_metrics,
    names_to_list,
)


class _FakeBox:
    """Stand-in for the ``box`` member of an Ultralytics metrics object."""

    def __init__(self, mp: float, mr: float, map50: float, map95: float) -> None:
        self.mp = mp
        self.mr = mr
        self.map50 = map50
        self.map = map95


class _FakeConfusion:
    """Stand-in for an Ultralytics ``ConfusionMatrix``."""

    def __init__(self, matrix: list[list[float]]) -> None:
        self.matrix = matrix


class _FakeValResult:
    """Stand-in for the object returned by ``model.val()``."""

    def __init__(
        self,
        results_dict: dict[str, float],
        box: _FakeBox | None = None,
        confusion: _FakeConfusion | None = None,
    ) -> None:
        self.results_dict = results_dict
        self.box = box
        self.confusion_matrix = confusion


def test_extract_metrics_from_results_dict() -> None:
    """Friendly metrics are read from the ``results_dict`` aliases."""
    result = _FakeValResult(
        results_dict={
            "metrics/precision(B)": 0.8,
            "metrics/recall(B)": 0.6,
            "metrics/mAP50(B)": 0.75,
            "metrics/mAP50-95(B)": 0.55,
        }
    )

    metrics = extract_metrics(result)

    assert metrics["precision"] == 0.8
    assert metrics["recall"] == 0.6
    assert metrics["mAP50"] == 0.75
    assert metrics["mAP50_95"] == 0.55
    # F1 is derived from precision and recall.
    assert metrics["f1"] == round(2 * 0.8 * 0.6 / (0.8 + 0.6), 4)


def test_extract_metrics_box_fallback() -> None:
    """Metrics fall back to the ``box`` attributes when keys are absent."""
    result = _FakeValResult(
        results_dict={},
        box=_FakeBox(mp=0.5, mr=0.5, map50=0.4, map95=0.3),
    )

    metrics = extract_metrics(result)

    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["mAP50"] == 0.4
    assert metrics["mAP50_95"] == 0.3
    assert metrics["f1"] == 0.5


def test_extract_metrics_zero_precision_recall_f1_is_zero() -> None:
    """F1 is 0.0 (not a division error) when precision+recall is zero."""
    result = _FakeValResult(
        results_dict={"metrics/precision(B)": 0.0, "metrics/recall(B)": 0.0}
    )
    assert extract_metrics(result)["f1"] == 0.0


def test_extract_metrics_from_plain_mapping() -> None:
    """A plain mapping (no ``results_dict``) is accepted directly."""
    metrics = extract_metrics({"metrics/precision": 0.9, "metrics/recall": 0.7})
    assert metrics["precision"] == 0.9
    assert metrics["recall"] == 0.7


def test_extract_confusion_rounds_to_int() -> None:
    """The confusion matrix is returned as a rounded int64 array."""
    result = _FakeValResult(
        results_dict={},
        confusion=_FakeConfusion([[3.0, 0.0], [1.0, 4.0]]),
    )

    matrix = extract_confusion(result)

    assert matrix is not None
    assert matrix.dtype == np.int64
    assert matrix.tolist() == [[3, 0], [1, 4]]


def test_extract_confusion_none_when_absent() -> None:
    """No confusion matrix yields ``None`` rather than raising."""
    assert extract_confusion(_FakeValResult(results_dict={})) is None


def test_names_to_list_from_mapping_and_sequence() -> None:
    """Class names normalise from a ``{idx: name}`` mapping or a sequence."""
    assert names_to_list({0: "laptop", 1: "phone"}) == ["laptop", "phone"]
    assert names_to_list(["laptop", "phone"]) == ["laptop", "phone"]
    assert names_to_list(None) is None
    assert names_to_list({}) is None


def test_build_document_aligns_background_class() -> None:
    """A background row/col is appended to the labels when the matrix is wider."""
    result = _FakeValResult(
        results_dict={
            "metrics/precision(B)": 0.8,
            "metrics/recall(B)": 0.7,
            "metrics/mAP50(B)": 0.75,
            "metrics/mAP50-95(B)": 0.6,
        },
        # 3x3 for two classes → one extra background row/col.
        confusion=_FakeConfusion([[5, 0, 1], [0, 4, 1], [1, 1, 0]]),
    )
    evaluator = DetectionEvaluator()

    document = evaluator.build_document(
        model_name="device-detector",
        model_version="1.0.0",
        results=result,
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        class_names={0: "laptop", 1: "smartphone"},
        dataset_version="v1",
        num_samples=42,
    )

    assert document["model_name"] == "device-detector"
    assert document["num_samples"] == 42
    confusion = document["confusion_matrix"]
    assert isinstance(confusion, dict)
    assert confusion["labels"] == ["laptop", "smartphone", "background"]


def test_to_html_renders_metrics() -> None:
    """The adapter renders a self-contained HTML report via the platform."""
    result = _FakeValResult(
        results_dict={"metrics/precision(B)": 0.8, "metrics/recall(B)": 0.7}
    )
    evaluator = DetectionEvaluator()
    document = evaluator.build_document(
        model_name="device-detector",
        model_version="1.0.0",
        results=result,
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    html = evaluator.to_html(document)

    assert "<html" in html.lower()
    assert "device-detector" in html
