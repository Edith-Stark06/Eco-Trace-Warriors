"""Tests for the evaluation report builder (milestone M1.3)."""

from __future__ import annotations

from datetime import datetime

import numpy as np

from device_ai.training.core.evaluator import (
    Evaluator,
    build_benchmark_placeholder,
    build_evaluation_document,
)


def _now() -> datetime:
    return datetime(2026, 8, 1, 9, 0, 0)


class TestBuildDocument:
    def test_metrics_and_benchmark_placeholder(self) -> None:
        document = build_evaluation_document(
            model_name="m",
            model_version="1.0.0",
            metrics={"accuracy": 0.9},
            confusion=None,
            class_names=None,
            generated_at=_now(),
            dataset_version="v1",
            num_samples=10,
        )
        assert document["model_name"] == "m"
        assert document["num_samples"] == 10
        assert document["metrics"]["accuracy"] == 0.9
        benchmark = document["benchmark"]
        assert isinstance(benchmark, dict)
        assert benchmark["status"] == "placeholder"
        assert benchmark["latency_ms"] is None
        assert "confusion_matrix" not in document

    def test_confusion_matrix_included(self) -> None:
        matrix = np.array([[2, 0], [1, 3]], dtype=np.int64)
        document = build_evaluation_document(
            model_name="m",
            model_version="1.0.0",
            metrics={},
            confusion=matrix,
            class_names=["a", "b"],
            generated_at=_now(),
        )
        confusion = document["confusion_matrix"]
        assert isinstance(confusion, dict)
        assert confusion["labels"] == ["a", "b"]
        assert confusion["matrix"] == [[2, 0], [1, 3]]

    def test_confusion_matrix_default_labels(self) -> None:
        matrix = np.array([[1, 0], [0, 1]], dtype=np.int64)
        document = build_evaluation_document(
            model_name="m",
            model_version="1.0.0",
            metrics={},
            confusion=matrix,
            class_names=None,
            generated_at=_now(),
        )
        assert document["confusion_matrix"]["labels"] == ["0", "1"]

    def test_benchmark_placeholder_shape(self) -> None:
        placeholder = build_benchmark_placeholder()
        assert set(placeholder) >= {
            "status",
            "note",
            "latency_ms",
            "throughput_fps",
            "device",
            "batch_size",
        }


class TestEvaluator:
    def test_evaluate_computes_metrics(self) -> None:
        evaluator = Evaluator()
        document = evaluator.evaluate(
            model_name="m",
            model_version="1.0.0",
            y_true=[0, 1, 2, 2, 1],
            y_pred=[0, 1, 2, 1, 1],
            class_names=["a", "b", "c"],
            generated_at=_now(),
            dataset_version="v1",
        )
        assert document["metrics"]["accuracy"] == 0.8
        assert document["num_samples"] == 5
        assert "confusion_matrix" in document

    def test_to_html_is_self_contained(self) -> None:
        evaluator = Evaluator()
        document = evaluator.evaluate(
            model_name="m",
            model_version="1.0.0",
            y_true=[0, 1],
            y_pred=[0, 1],
            class_names=["a", "b"],
            generated_at=_now(),
        )
        html = evaluator.to_html(document)
        assert html.startswith("<!DOCTYPE html>")
        assert "<script" not in html.lower()
        assert "Model Evaluation Report" in html
        assert "Confusion matrix" in html
        assert "Inference benchmark" in html
        # No external assets referenced.
        assert "http://" not in html
        assert "https://" not in html

    def test_to_html_without_confusion(self) -> None:
        document = build_evaluation_document(
            model_name="m",
            model_version="1.0.0",
            metrics={"accuracy": 1.0},
            confusion=None,
            class_names=None,
            generated_at=_now(),
        )
        html = Evaluator().to_html(document)
        assert "Confusion matrix" not in html
        assert "Metrics" in html

    def test_html_escapes_model_name(self) -> None:
        document = build_evaluation_document(
            model_name="<script>evil</script>",
            model_version="1.0.0",
            metrics={},
            confusion=None,
            class_names=None,
            generated_at=_now(),
        )
        html = Evaluator().to_html(document)
        assert "<script>evil" not in html
        assert "&lt;script&gt;" in html
