"""Tests for the pure-NumPy training metrics (milestone M1.3)."""

from __future__ import annotations

import numpy as np
import pytest

from device_ai.training.core.metrics import (
    MetricTracker,
    accuracy,
    classification_metrics,
    confusion_matrix,
    f1_score,
    mean_average_precision,
    precision_recall_f1,
    precision_score,
    recall_score,
)


def test_accuracy_perfect_and_empty() -> None:
    assert accuracy([0, 1, 2], [0, 1, 2]) == 1.0
    assert accuracy([], []) == 0.0


def test_accuracy_partial() -> None:
    assert accuracy([0, 1, 2, 2], [0, 1, 2, 1]) == pytest.approx(0.75)


def test_accuracy_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        accuracy([0, 1], [0])


def test_negative_labels_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        confusion_matrix([-1, 0], [0, 0])


def test_confusion_matrix_shape_and_counts() -> None:
    matrix = confusion_matrix([0, 1, 2, 2, 1], [0, 1, 2, 1, 1])
    assert matrix.shape == (3, 3)
    assert matrix.tolist() == [[1, 0, 0], [0, 2, 0], [0, 1, 1]]


def test_confusion_matrix_explicit_num_classes() -> None:
    matrix = confusion_matrix([0, 1], [0, 1], num_classes=4)
    assert matrix.shape == (4, 4)


def test_confusion_matrix_num_classes_too_small() -> None:
    with pytest.raises(ValueError, match="too small"):
        confusion_matrix([0, 3], [0, 3], num_classes=2)


def test_confusion_matrix_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        confusion_matrix([0, 1, 2], [0, 1])


def test_confusion_matrix_empty_returns_1x1() -> None:
    matrix = confusion_matrix([], [])
    assert matrix.shape == (1, 1)
    assert matrix.sum() == 0


def test_precision_recall_f1_macro() -> None:
    precision, recall, f1 = precision_recall_f1(
        [0, 1, 2, 2, 1], [0, 1, 2, 1, 1], average="macro"
    )
    assert precision == pytest.approx(0.8888888, abs=1e-4)
    assert recall == pytest.approx(0.8333333, abs=1e-4)
    assert f1 == pytest.approx(0.8222222, abs=1e-4)


def test_precision_recall_f1_micro_equals_accuracy() -> None:
    yt, yp = [0, 1, 2, 2, 1], [0, 1, 2, 1, 1]
    precision, recall, f1 = precision_recall_f1(yt, yp, average="micro")
    assert precision == recall == f1 == pytest.approx(accuracy(yt, yp))


def test_precision_recall_f1_weighted() -> None:
    precision, recall, f1 = precision_recall_f1(
        [0, 1, 2, 2, 1], [0, 1, 2, 1, 1], average="weighted"
    )
    assert 0.0 <= precision <= 1.0
    assert recall == pytest.approx(0.8, abs=1e-6)


def test_precision_recall_f1_empty_is_zero() -> None:
    assert precision_recall_f1([], []) == (0.0, 0.0, 0.0)


def test_invalid_average_rejected() -> None:
    with pytest.raises(ValueError, match="average must be"):
        precision_recall_f1([0], [0], average="bogus")


def test_scalar_score_helpers_agree_with_tuple() -> None:
    yt, yp = [0, 1, 1, 0], [0, 1, 0, 0]
    precision, recall, f1 = precision_recall_f1(yt, yp)
    assert precision_score(yt, yp) == precision
    assert recall_score(yt, yp) == recall
    assert f1_score(yt, yp) == f1


def test_classification_metrics_bundle() -> None:
    metrics = classification_metrics([0, 1, 2, 2, 1], [0, 1, 2, 1, 1])
    assert set(metrics) == {"accuracy", "precision", "recall", "f1"}
    assert metrics["accuracy"] == pytest.approx(0.8)


def test_mean_average_precision_placeholder() -> None:
    assert mean_average_precision() == 0.0
    assert mean_average_precision([]) == 0.0
    assert mean_average_precision([0.4, 0.6]) == pytest.approx(0.5)


def test_metrics_accept_numpy_arrays() -> None:
    yt = np.array([0, 1, 2])
    yp = np.array([0, 1, 1])
    assert accuracy(yt, yp) == pytest.approx(2 / 3)


class TestMetricTracker:
    def test_weighted_average(self) -> None:
        tracker = MetricTracker()
        tracker.update("loss", 1.0, count=2)
        tracker.update("loss", 4.0, count=1)
        assert tracker.average("loss") == pytest.approx(2.0)

    def test_update_many_and_averages(self) -> None:
        tracker = MetricTracker()
        tracker.update_many({"loss": 1.0, "acc": 0.5})
        tracker.update_many({"loss": 3.0, "acc": 0.7})
        averages = tracker.averages()
        assert averages["loss"] == pytest.approx(2.0)
        assert averages["acc"] == pytest.approx(0.6)

    def test_missing_metric_average_is_zero(self) -> None:
        assert MetricTracker().average("nope") == 0.0

    def test_reset_clears(self) -> None:
        tracker = MetricTracker()
        tracker.update("loss", 1.0)
        tracker.reset()
        assert tracker.averages() == {}
        assert "loss" not in tracker

    def test_names_and_contains(self) -> None:
        tracker = MetricTracker()
        tracker.update("loss", 1.0)
        assert tracker.names == ("loss",)
        assert "loss" in tracker

    def test_non_positive_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="count must be positive"):
            MetricTracker().update("loss", 1.0, count=0)
