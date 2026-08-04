"""Real device detector backed by Ultralytics YOLO (milestone M1.4).

:class:`YOLODetector` is the first *real* model to replace a milestone-M1.1
mock. It implements the existing :class:`~device_ai.inference.predictor.Detector`
contract, so wiring it into the pipeline (and therefore ``POST /predict``) is a
dependency-injection concern only — the API response schema is unchanged.

Only ``device_type``, ``confidence`` and ``bounding_box`` become real; ``brand``
stays a placeholder until a later sprint (the YOLO detector does not classify
manufacturers).

Design, consistent with the rest of the engine:

* **Optional backend, honest degradation.** ``ultralytics``/``torch`` are heavy,
  optional dependencies (``requirements-models.txt``). The import is guarded; in
  the base environment (or when no artifact resolves) the detector is simply
  *not ready* and never pretends to run.
* **Everything injectable.** A loaded model can be passed in directly
  (``model=...``) so all parsing/aggregation logic is unit-testable with a small
  fake — no weights, no torch, no GPU.
* **No hardcoded paths.** The weights location is resolved from configuration by
  the caller (see :func:`device_ai.api.dependencies.get_pipeline`) and injected.

The Ultralytics-present code paths (importing ``ultralytics`` and constructing a
real ``YOLO``) are marked ``# pragma: no cover``: no model is installed in the
test environment, so they never run there. All parsing, mapping, aggregation and
the not-loaded guard are covered via injected fakes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from ..exceptions import ModelNotLoadedError
from ..preprocessing.image_loader import LoadedImage
from .predictor import Detection, DetectionResult, Detector

#: Placeholder brand until a brand/manufacturer model ships (later sprint).
_PLACEHOLDER_BRAND = "Unknown"

#: Device type reported when the model returns no detections for the batch.
_UNKNOWN_DEVICE_TYPE = "Unknown"

#: Artifact file names tried, in order, when ``weights_path`` is a directory.
_WEIGHTS_CANDIDATES: tuple[str, ...] = ("model.pt", "model.onnx")


def _import_yolo() -> Any | None:
    """Return the Ultralytics ``YOLO`` class, or ``None`` when unavailable.

    Returns:
        The ``ultralytics.YOLO`` class when importable, otherwise ``None``.
    """
    try:  # pragma: no cover - ultralytics is not installed in the base env
        from ultralytics import YOLO
    except ImportError:
        return None
    return YOLO  # pragma: no cover


def _as_list(value: Any) -> list[Any]:
    """Normalise a tensor/array/sequence of predictions into a plain list.

    Ultralytics returns torch tensors (which expose ``tolist``); test fakes pass
    plain nested lists. Both are handled without importing torch.

    Args:
        value: A tensor, array or sequence.

    Returns:
        A plain Python list of the values.
    """
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        result: list[Any] = to_list()
        return result
    return list(value)


class YOLODetector(Detector):
    """Ultralytics-YOLO-backed implementation of the :class:`Detector` contract.

    The detector runs YOLO inference over the batch, collects per-object
    detections and reports the single highest-confidence detection as the
    device type/confidence/bounding box. ``brand`` remains a placeholder.

    Args:
        weights_path: Location of the model artifact. May point directly at a
            ``.pt``/``.onnx`` file, or at a directory containing ``model.pt`` or
            ``model.onnx``. Ignored when ``model`` is supplied.
        image_size: Inference image size (pixels) forwarded to YOLO.
        confidence_threshold: Minimum confidence for a detection to be kept.
        label_map: Optional mapping from raw model class name to a canonical
            device-type label. Unmapped labels fall back to the raw name; the
            result is always title-cased.
        model: A pre-loaded model object (real ``YOLO`` or a test fake exposing
            ``predict``/``__call__``). When given, ``weights_path`` is not read.
    """

    version = "yolo-detector-1.0.0"

    def __init__(
        self,
        *,
        weights_path: Path | None = None,
        image_size: int = 640,
        confidence_threshold: float = 0.25,
        label_map: Mapping[str, str] | None = None,
        model: Any | None = None,
    ) -> None:
        self._weights_path = weights_path
        self._image_size = image_size
        self._confidence_threshold = confidence_threshold
        self._label_map: dict[str, str] = dict(label_map or {})
        if model is not None:
            self._model: Any | None = model
        elif weights_path is not None:
            self._model = self._load(weights_path)
        else:
            self._model = None

    # -- Readiness --------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Whether a model is loaded and inference can be served."""
        return self._model is not None

    # -- Loading ----------------------------------------------------------

    @staticmethod
    def _resolve_weights(weights_path: Path) -> Path | None:
        """Resolve ``weights_path`` to a concrete artifact file, if present.

        Args:
            weights_path: A file path, or a directory to search for a known
                artifact file name.

        Returns:
            The resolved artifact file path, or ``None`` when nothing exists.
        """
        if weights_path.is_file():
            return weights_path
        if weights_path.is_dir():
            for candidate_name in _WEIGHTS_CANDIDATES:
                candidate = weights_path / candidate_name
                if candidate.is_file():
                    return candidate
        return None

    def _load(self, weights_path: Path) -> Any | None:
        """Load a YOLO model from ``weights_path``, degrading honestly.

        Returns ``None`` (leaving the detector not-ready) when the artifact is
        absent, Ultralytics is not installed, or loading fails — never raising,
        so the caller can fall back to the mock detector.

        Args:
            weights_path: File or directory locating the model artifact.

        Returns:
            The loaded model object, or ``None`` on any failure.
        """
        resolved = self._resolve_weights(weights_path)
        if resolved is None:
            logger.warning(
                "No detector artifact found at '{}'; detector not loaded.",
                weights_path,
            )
            return None
        yolo_cls = _import_yolo()
        if yolo_cls is None:
            logger.warning(
                "ultralytics is not installed; detector artifact '{}' not loaded.",
                resolved,
            )
            return None
        try:  # pragma: no cover - requires optional ultralytics/torch
            model = yolo_cls(str(resolved))
        except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
            logger.warning("Failed to load detector artifact '{}': {}", resolved, exc)
            return None
        logger.info("Loaded YOLO detector from '{}'.", resolved)  # pragma: no cover
        return model  # pragma: no cover

    # -- Inference --------------------------------------------------------

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        """Detect the device type/confidence/bounding box for a batch.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A :class:`DetectionResult` whose ``device_type``/``confidence``/
            highest-confidence bounding box are real and whose ``brand`` is a
            placeholder.

        Raises:
            ModelNotLoadedError: If no model is loaded (``is_ready`` is False).
        """
        if not self.is_ready:
            raise ModelNotLoadedError(
                "YOLO detector has no model loaded.",
                details={"weights_path": str(self._weights_path)},
            )
        frames = [img.image for img in images]
        results = self._run_inference(frames)
        detections = self._parse_results(results)
        return self._aggregate(detections)

    def _run_inference(self, frames: list[Any]) -> Any:
        """Run the loaded model over ``frames`` and return its raw results.

        Prefers a ``predict`` method (Ultralytics' public API), falling back to
        calling the model directly.

        Args:
            frames: Decoded images (Pillow images or arrays) to run inference on.

        Returns:
            The backend's raw results (an iterable of per-image result objects).
        """
        predict = getattr(self._model, "predict", None)
        if callable(predict):
            return predict(
                frames,
                imgsz=self._image_size,
                conf=self._confidence_threshold,
                verbose=False,
            )
        model = self._model
        assert model is not None  # noqa: S101 - guarded by is_ready in detect()
        return model(frames)

    def _parse_results(self, results: Any) -> list[Detection]:
        """Parse backend results into a flat list of :class:`Detection`.

        Robust to the Ultralytics ``Results``/``Boxes`` shape and to plain-list
        fakes: coordinates/confidences/classes are read defensively and class
        indices are mapped to names via each result's ``names`` mapping.

        Args:
            results: An iterable of per-image result objects.

        Returns:
            Every kept detection across the batch (may be empty).
        """
        detections: list[Detection] = []
        for result in results or []:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            names = getattr(result, "names", None) or {}
            xyxy = _as_list(getattr(boxes, "xyxy", []))
            confidences = _as_list(getattr(boxes, "conf", []))
            classes = _as_list(getattr(boxes, "cls", []))
            for box, confidence, class_index in zip(
                xyxy, confidences, classes, strict=False
            ):
                conf = round(float(confidence), 4)
                if conf < self._confidence_threshold:
                    continue
                label = str(names.get(int(class_index), int(class_index)))
                detections.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        bounding_box=self._to_box(box),
                    )
                )
        return detections

    @staticmethod
    def _to_box(box: Any) -> tuple[int, int, int, int]:
        """Convert a raw ``[x1, y1, x2, y2]`` box to an int 4-tuple."""
        x1, y1, x2, y2 = (int(round(float(value))) for value in list(box)[:4])
        return (x1, y1, x2, y2)

    def _map_label(self, label: str) -> str:
        """Map a raw model class name to a canonical, title-cased device type.

        Args:
            label: The raw class name emitted by the model.

        Returns:
            The mapped label (identity fallback) with underscores turned to
            spaces and title-cased.
        """
        mapped = self._label_map.get(label, label)
        return mapped.replace("_", " ").title()

    def _aggregate(self, detections: list[Detection]) -> DetectionResult:
        """Reduce per-object detections to a single :class:`DetectionResult`.

        The highest-confidence detection drives ``device_type``/``confidence``/
        the reported bounding box; ``brand`` is a placeholder.

        Args:
            detections: Every detection across the batch.

        Returns:
            The aggregated detection result (``Unknown`` device type when the
            batch produced no detections).
        """
        if not detections:
            return DetectionResult(
                device_type=_UNKNOWN_DEVICE_TYPE,
                brand=_PLACEHOLDER_BRAND,
                confidence=0.0,
                detections=[],
            )
        best = max(detections, key=lambda detection: detection.confidence)
        return DetectionResult(
            device_type=self._map_label(best.label),
            brand=_PLACEHOLDER_BRAND,
            confidence=best.confidence,
            detections=detections,
        )
