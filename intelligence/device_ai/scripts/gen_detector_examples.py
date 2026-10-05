"""Generate illustrative detector evaluation artifacts for docs/examples/detector.

Renders a detection evaluation report (JSON + self-contained HTML) from a small
**fake** ``model.val()`` result — the same shape the unit tests use — with an
injected fixed clock so the output is byte-stable. No real model is trained,
downloaded or executed here: the numbers are illustrative placeholders standing
in for a real Ultralytics ``val()`` on a fine-tuned detector.

At runtime the equivalent files are written under the gitignored
``artifacts/reports/`` tree by :meth:`DetectionEvaluator.build_document` /
:meth:`DetectionEvaluator.to_html`.

Usage (from ``intelligence/`` with ``PYTHONPATH=.``)::

    python -m device_ai.scripts.gen_detector_examples
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from device_ai.training.detector.evaluation import DetectionEvaluator

_FIXED_CLOCK = datetime(2026, 7, 31, 12, 0, 0)
_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples" / "detector"

#: Canonical e-waste device classes the illustrative detector distinguishes.
_CLASS_NAMES = {0: "laptop", 1: "smartphone", 2: "tablet", 3: "monitor"}


class _FakeConfusion:
    """Stand-in for an Ultralytics ``ConfusionMatrix`` (background row/col)."""

    def __init__(self, matrix: list[list[float]]) -> None:
        self.matrix = matrix


class _FakeValResult:
    """Stand-in for the object returned by ``model.val()``."""

    def __init__(
        self,
        results_dict: dict[str, float],
        confusion: _FakeConfusion,
    ) -> None:
        self.results_dict = results_dict
        self.confusion_matrix = confusion


def _build_result() -> _FakeValResult:
    """Return a fixed, illustrative detection val result.

    Returns:
        A fake val result with a four-class confusion matrix (plus the
        Ultralytics background row/column) and representative mAP/P/R numbers.
    """
    # 5x5 for four classes → one extra background row/col (Ultralytics shape).
    confusion = _FakeConfusion(
        [
            [46, 0, 1, 0, 3],
            [0, 44, 2, 0, 4],
            [1, 1, 39, 0, 4],
            [0, 0, 1, 42, 2],
            [2, 3, 2, 1, 0],
        ]
    )
    return _FakeValResult(
        results_dict={
            "metrics/precision(B)": 0.912,
            "metrics/recall(B)": 0.884,
            "metrics/mAP50(B)": 0.901,
            "metrics/mAP50-95(B)": 0.742,
        },
        confusion=confusion,
    )


def main() -> None:
    """Generate the example detector-evaluation artifacts."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = DetectionEvaluator()
    document = evaluator.build_document(
        model_name="device-detector",
        model_version="1.0.0",
        results=_build_result(),
        generated_at=_FIXED_CLOCK,
        class_names=_CLASS_NAMES,
        dataset_version="v1",
        num_samples=200,
    )
    (_EXAMPLES_DIR / "evaluation.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (_EXAMPLES_DIR / "evaluation.html").write_text(
        evaluator.to_html(document), encoding="utf-8"
    )
    print(f"Wrote example detector artifacts to {_EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
