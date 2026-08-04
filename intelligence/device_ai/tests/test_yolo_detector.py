"""Unit tests for the Ultralytics-backed :class:`YOLODetector` (milestone M1.4).

Every test drives the detector through **injected fakes** — no ``ultralytics``,
``torch`` or GPU is required — so the parsing, mapping, aggregation and the
not-loaded guard are all exercised in the base environment. The tiny fakes below
mimic the Ultralytics ``Results``/``Boxes`` shape the detector reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from device_ai.exceptions import ModelNotLoadedError
from device_ai.inference.predictor import DetectionResult
from device_ai.inference.yolo_detector import YOLODetector
from device_ai.preprocessing.image_loader import LoadedImage


class _FakeBoxes:
    """Stand-in for an Ultralytics ``Boxes`` object exposing plain lists."""

    def __init__(
        self,
        xyxy: list[list[float]],
        conf: list[float],
        cls: list[int],
    ) -> None:
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls


class _FakeResult:
    """Stand-in for one Ultralytics ``Results`` object."""

    def __init__(self, boxes: _FakeBoxes | None, names: dict[int, str]) -> None:
        self.boxes = boxes
        self.names = names


class _FakeModel:
    """A fake YOLO model recording the arguments it was called with."""

    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = results
        self.predict_kwargs: dict[str, object] = {}
        self.called_with_frames: list[object] | None = None

    def predict(self, frames: list[object], **kwargs: object) -> list[_FakeResult]:
        """Record inputs and return the canned results."""
        self.called_with_frames = frames
        self.predict_kwargs = kwargs
        return self._results


class _CallableOnlyModel:
    """A fake exposing only ``__call__`` (no ``predict``) to test the fallback."""

    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = results
        self.called_with_frames: list[object] | None = None

    def __call__(self, frames: list[object]) -> list[_FakeResult]:
        self.called_with_frames = frames
        return self._results


def _loaded_image(color: tuple[int, int, int] = (10, 20, 30)) -> LoadedImage:
    """Build a minimal :class:`LoadedImage` with a real Pillow image."""
    return LoadedImage(
        filename="x.png",
        content_type="image/png",
        raw=b"x",
        image=Image.new("RGB", (32, 32), color),
        sha256="deadbeef",
    )


def test_not_ready_without_model_or_weights() -> None:
    """A detector built with neither a model nor weights is not ready."""
    detector = YOLODetector()
    assert detector.is_ready is False


def test_detect_raises_when_not_loaded() -> None:
    """``detect`` raises :class:`ModelNotLoadedError` when no model is loaded."""
    detector = YOLODetector()
    with pytest.raises(ModelNotLoadedError):
        detector.detect([_loaded_image()])


def test_injected_model_is_ready() -> None:
    """Injecting a model makes the detector ready without touching disk."""
    model = _FakeModel([])
    detector = YOLODetector(model=model)
    assert detector.is_ready is True


def test_detect_parses_and_aggregates_highest_confidence() -> None:
    """The highest-confidence detection drives device_type/confidence."""
    result = _FakeResult(
        boxes=_FakeBoxes(
            xyxy=[[1.4, 2.6, 10.2, 20.8], [0.0, 0.0, 5.0, 5.0]],
            conf=[0.90, 0.40],
            cls=[0, 1],
        ),
        names={0: "laptop", 1: "smartphone"},
    )
    detector = YOLODetector(model=_FakeModel([result]), confidence_threshold=0.25)

    outcome = detector.detect([_loaded_image()])

    assert isinstance(outcome, DetectionResult)
    assert outcome.device_type == "Laptop"
    assert outcome.confidence == 0.90
    assert outcome.brand == "Unknown"  # placeholder until a later sprint
    assert len(outcome.detections) == 2
    # Coordinates are rounded to an int 4-tuple.
    assert outcome.detections[0].bounding_box == (1, 3, 10, 21)


def test_detect_filters_below_threshold() -> None:
    """Detections below the confidence threshold are dropped."""
    result = _FakeResult(
        boxes=_FakeBoxes(
            xyxy=[[0, 0, 4, 4], [1, 1, 2, 2]],
            conf=[0.80, 0.10],
            cls=[0, 0],
        ),
        names={0: "monitor"},
    )
    detector = YOLODetector(model=_FakeModel([result]), confidence_threshold=0.25)

    outcome = detector.detect([_loaded_image()])

    assert len(outcome.detections) == 1
    assert outcome.detections[0].confidence == 0.80


def test_detect_no_detections_yields_unknown() -> None:
    """An empty batch of detections aggregates to the Unknown placeholder."""
    result = _FakeResult(boxes=_FakeBoxes([], [], []), names={0: "laptop"})
    detector = YOLODetector(model=_FakeModel([result]))

    outcome = detector.detect([_loaded_image()])

    assert outcome.device_type == "Unknown"
    assert outcome.brand == "Unknown"
    assert outcome.confidence == 0.0
    assert outcome.detections == []


def test_detect_handles_result_without_boxes() -> None:
    """A result whose ``boxes`` is ``None`` is skipped, not fatal."""
    detector = YOLODetector(model=_FakeModel([_FakeResult(None, {})]))
    outcome = detector.detect([_loaded_image()])
    assert outcome.device_type == "Unknown"


def test_label_map_and_title_casing() -> None:
    """A configured label map is applied, then underscores/casing normalised."""
    result = _FakeResult(
        boxes=_FakeBoxes([[0, 0, 4, 4]], [0.7], [0]),
        names={0: "cell_phone"},
    )
    detector = YOLODetector(
        model=_FakeModel([result]),
        label_map={"cell_phone": "smart_phone"},
    )

    outcome = detector.detect([_loaded_image()])

    assert outcome.device_type == "Smart Phone"


def test_predict_receives_configured_inference_args() -> None:
    """``predict`` is called with the configured image size and threshold."""
    model = _FakeModel([_FakeResult(_FakeBoxes([], [], []), {})])
    detector = YOLODetector(model=model, image_size=512, confidence_threshold=0.33)

    detector.detect([_loaded_image(), _loaded_image((1, 2, 3))])

    assert model.predict_kwargs["imgsz"] == 512
    assert model.predict_kwargs["conf"] == 0.33
    assert model.predict_kwargs["verbose"] is False
    assert model.called_with_frames is not None
    assert len(model.called_with_frames) == 2


def test_callable_only_model_fallback() -> None:
    """A model without ``predict`` is invoked via ``__call__``."""
    result = _FakeResult(_FakeBoxes([[0, 0, 4, 4]], [0.9], [0]), {0: "tablet"})
    model = _CallableOnlyModel([result])
    detector = YOLODetector(model=model)

    outcome = detector.detect([_loaded_image()])

    assert outcome.device_type == "Tablet"
    assert model.called_with_frames is not None


def test_load_absent_artifact_degrades_to_not_ready(tmp_path: Path) -> None:
    """A weights path with no artifact leaves the detector not ready."""
    detector = YOLODetector(weights_path=tmp_path / "missing")
    assert detector.is_ready is False


def test_resolve_weights_file_and_directory(tmp_path: Path) -> None:
    """``_resolve_weights`` returns a file directly and finds one in a dir."""
    direct = tmp_path / "model.pt"
    direct.write_text("weights", encoding="utf-8")
    assert YOLODetector._resolve_weights(direct) == direct

    model_dir = tmp_path / "artifact"
    model_dir.mkdir()
    nested = model_dir / "model.onnx"
    nested.write_text("weights", encoding="utf-8")
    assert YOLODetector._resolve_weights(model_dir) == nested

    empty = tmp_path / "empty"
    empty.mkdir()
    assert YOLODetector._resolve_weights(empty) is None
