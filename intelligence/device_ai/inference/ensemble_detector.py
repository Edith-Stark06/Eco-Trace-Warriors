"""Multi-model WBF ensemble detector for P5.0 production inference.

:class:`EnsembleDetector` implements the existing
:class:`~device_ai.inference.predictor.Detector` contract by running two
YOLO models (P4.11 YOLO11n and P4.12 YOLO11s), optionally with Test-Time
Augmentation (TTA), and fusing their predictions via Weighted Box Fusion.

This corresponds to the **E4_EnsTTA_50_50** configuration from the P4.13
evaluation suite which achieved the highest overall OOD mAP50 (0.3381) and
the highest in-domain P4.5 mAP50 (0.7353).

Design notes:

* **Same contract as YOLODetector.**  Plugs into ``PredictionPipeline`` via
  dependency injection — no pipeline or API change required.
* **Optional backend, honest degradation.**  If ``ultralytics``/``torch`` are
  unavailable or weight files do not exist, the detector stays not-ready and
  the caller falls back to the mock pipeline.
* **No hardcoded paths.**  Weight locations come from configuration.
* **Fakes-friendly.**  A pre-loaded model pair can be injected via
  ``model_a`` / ``model_b`` for unit testing without weights or torch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from ..exceptions import ModelNotLoadedError
from ..preprocessing.image_loader import LoadedImage
from .class_map import CANONICAL_CLASSES
from .predictor import Detection, DetectionResult, Detector
from .wbf import weighted_box_fusion


#: Placeholder brand until a brand/manufacturer model ships.
_PLACEHOLDER_BRAND = "Unknown"

#: Device type reported when the ensemble produces no detections.
_UNKNOWN_DEVICE_TYPE = "Unknown"


def _import_yolo() -> Any | None:
    """Return the Ultralytics ``YOLO`` class, or ``None`` when unavailable."""
    try:  # pragma: no cover - ultralytics is not installed in the base env
        from ultralytics import YOLO
    except ImportError:
        return None
    return YOLO  # pragma: no cover


def _load_model(weights_path: Path) -> Any | None:
    """Load a YOLO model from ``weights_path``, returning ``None`` on failure.

    Args:
        weights_path: Absolute or relative path to the ``.pt`` checkpoint.

    Returns:
        The loaded model, or ``None`` when the file is absent, the backend
        is not installed, or loading fails.
    """
    if not weights_path.is_file():
        logger.warning(
            "Ensemble weight file not found at '{}'; model not loaded.",
            weights_path,
        )
        return None

    yolo_cls = _import_yolo()
    if yolo_cls is None:
        logger.warning(
            "ultralytics is not installed; ensemble weight '{}' not loaded.",
            weights_path,
        )
        return None

    try:  # pragma: no cover
        model = yolo_cls(str(weights_path))
    except Exception as exc:  # noqa: BLE001 - degrade honestly
        logger.warning("Failed to load ensemble weight '{}': {}", weights_path, exc)
        return None

    logger.info("Loaded ensemble model from '{}'.", weights_path)  # pragma: no cover
    return model  # pragma: no cover


class EnsembleDetector(Detector):
    """WBF ensemble of two YOLO detectors with optional TTA.

    Implements the :class:`Detector` contract so it can be injected into
    :class:`~device_ai.inference.pipeline.PredictionPipeline` identically to
    :class:`~device_ai.inference.yolo_detector.YOLODetector`.

    Args:
        model_a_path: P4.11 YOLO11n checkpoint. Ignored when ``model_a``
            is supplied.
        model_b_path: P4.12 YOLO11s checkpoint. Ignored when ``model_b``
            is supplied.
        weights: Per-model fusion weights ``(w_a, w_b)``.
        use_tta: Whether to enable Test-Time Augmentation.
        iou_threshold: IoU threshold for WBF clustering.
        image_size: Inference image size (pixels).
        confidence_threshold: Minimum confidence for a fused detection.
        model_a: Pre-loaded Model A (for testing).
        model_b: Pre-loaded Model B (for testing).
    """

    version = "ensemble-wbf-1.0.0"

    def __init__(
        self,
        *,
        model_a_path: Path | None = None,
        model_b_path: Path | None = None,
        weights: tuple[float, float] = (0.5, 0.5),
        use_tta: bool = True,
        iou_threshold: float = 0.55,
        image_size: int = 512,
        confidence_threshold: float = 0.25,
        model_a: Any | None = None,
        model_b: Any | None = None,
    ) -> None:
        self._model_a_path = model_a_path
        self._model_b_path = model_b_path
        self._weights = list(weights)
        self._use_tta = use_tta
        self._iou_threshold = iou_threshold
        self._image_size = image_size
        self._confidence_threshold = confidence_threshold

        # Load models (injected fakes take precedence).
        self._model_a: Any | None = (
            model_a
            if model_a is not None
            else (_load_model(model_a_path) if model_a_path else None)
        )
        self._model_b: Any | None = (
            model_b
            if model_b is not None
            else (_load_model(model_b_path) if model_b_path else None)
        )

    # -- Readiness --------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Both models must be loaded for the ensemble to be ready."""
        return self._model_a is not None and self._model_b is not None

    # -- Inference --------------------------------------------------------

    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        """Run ensemble inference and return fused detections.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A :class:`DetectionResult` with WBF-fused detections.

        Raises:
            ModelNotLoadedError: If either model is not loaded.
        """
        if not self.is_ready:
            raise ModelNotLoadedError(
                "Ensemble detector requires both models to be loaded.",
                details={
                    "model_a_path": str(self._model_a_path),
                    "model_b_path": str(self._model_b_path),
                    "model_a_loaded": self._model_a is not None,
                    "model_b_loaded": self._model_b is not None,
                },
            )

        frames = [img.image for img in images]
        all_detections: list[Detection] = []

        for frame in frames:
            fused = self._fuse_single_image(frame)
            all_detections.extend(fused)

        return self._aggregate(all_detections)

    def _run_single_model(self, model: Any, frame: Any) -> Any:
        """Run a single YOLO model on one frame.

        Args:
            model: A loaded YOLO model.
            frame: A decoded image (PIL or ndarray).

        Returns:
            The first result object from the model.
        """
        predict = getattr(model, "predict", None)
        if callable(predict):
            results = predict(
                frame,
                imgsz=self._image_size,
                conf=0.001,  # Low threshold; WBF handles confidence later.
                iou=0.7,
                augment=self._use_tta,
                verbose=False,
            )
        else:
            results = model(frame)

        return results[0] if results else None

    def _extract_predictions(
        self, result: Any, img_h: int, img_w: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extract normalised predictions from a YOLO result.

        Args:
            result: A single-image YOLO result object.
            img_h: Original image height.
            img_w: Original image width.

        Returns:
            Tuple of ``(boxes_norm, scores, labels)`` where boxes are in
            normalised ``[0, 1]`` coordinates.
        """
        if result is None:
            return _empty_preds()

        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return _empty_preds()

        xyxy = _to_numpy(getattr(boxes, "xyxy", []))
        scores = _to_numpy(getattr(boxes, "conf", []))
        labels = _to_numpy(getattr(boxes, "cls", [])).astype(int)

        if len(xyxy) == 0:
            return _empty_preds()

        # Normalise to [0, 1].
        xyxy_norm = xyxy.copy().astype(np.float32)
        xyxy_norm[:, 0] = np.clip(xyxy[:, 0] / img_w, 0.0, 1.0)
        xyxy_norm[:, 1] = np.clip(xyxy[:, 1] / img_h, 0.0, 1.0)
        xyxy_norm[:, 2] = np.clip(xyxy[:, 2] / img_w, 0.0, 1.0)
        xyxy_norm[:, 3] = np.clip(xyxy[:, 3] / img_h, 0.0, 1.0)

        return xyxy_norm, scores.astype(np.float32), labels

    def _fuse_single_image(self, frame: Any) -> list[Detection]:
        """Run both models on a single image and fuse via WBF.

        Args:
            frame: A decoded image (PIL or ndarray).

        Returns:
            A list of fused :class:`Detection` objects.
        """
        # Determine image dimensions.
        img_h, img_w = _image_dimensions(frame)

        # Run both models.
        result_a = self._run_single_model(self._model_a, frame)
        result_b = self._run_single_model(self._model_b, frame)

        # Extract normalised predictions.
        boxes_a, scores_a, labels_a = self._extract_predictions(
            result_a, img_h, img_w
        )
        boxes_b, scores_b, labels_b = self._extract_predictions(
            result_b, img_h, img_w
        )

        # Fuse via WBF.
        fused_boxes, fused_scores, fused_labels = weighted_box_fusion(
            boxes_list=[boxes_a, boxes_b],
            scores_list=[scores_a, scores_b],
            labels_list=[labels_a, labels_b],
            weights=self._weights,
            iou_thr=self._iou_threshold,
        )

        # Convert back to pixel coordinates and build Detection list.
        detections: list[Detection] = []
        for i in range(len(fused_scores)):
            conf = float(fused_scores[i])
            if conf < self._confidence_threshold:
                continue

            box_norm = fused_boxes[i]
            x1 = int(round(box_norm[0] * img_w))
            y1 = int(round(box_norm[1] * img_h))
            x2 = int(round(box_norm[2] * img_w))
            y2 = int(round(box_norm[3] * img_h))

            cls_id = int(fused_labels[i])
            label = CANONICAL_CLASSES.get(cls_id, str(cls_id))

            detections.append(
                Detection(
                    label=label,
                    confidence=round(conf, 4),
                    bounding_box=(x1, y1, x2, y2),
                )
            )

        return detections

    @staticmethod
    def _aggregate(detections: list[Detection]) -> DetectionResult:
        """Reduce per-object detections to a single :class:`DetectionResult`.

        The highest-confidence detection drives ``device_type``/``confidence``
        and the reported bounding box; ``brand`` is a placeholder.

        Args:
            detections: Every detection across all frames.

        Returns:
            The aggregated result (``Unknown`` when no detections).
        """
        if not detections:
            return DetectionResult(
                device_type=_UNKNOWN_DEVICE_TYPE,
                brand=_PLACEHOLDER_BRAND,
                confidence=0.0,
                detections=[],
            )

        best = max(detections, key=lambda d: d.confidence)
        return DetectionResult(
            device_type=best.label.replace("_", " ").title(),
            brand=_PLACEHOLDER_BRAND,
            confidence=best.confidence,
            detections=detections,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_preds() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return empty prediction arrays."""
    return (
        np.empty((0, 4), dtype=np.float32),
        np.empty((0,), dtype=np.float32),
        np.empty((0,), dtype=int),
    )


def _to_numpy(value: Any) -> np.ndarray:
    """Convert a tensor/array/sequence to a numpy array."""
    if hasattr(value, "cpu"):
        return value.cpu().numpy()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.array(value)


def _image_dimensions(frame: Any) -> tuple[int, int]:
    """Return ``(height, width)`` of the frame.

    Handles PIL Images (``size`` attribute = ``(w, h)``) and numpy arrays
    (``shape`` = ``(h, w, ...)``).

    Args:
        frame: A decoded image.

    Returns:
        A ``(height, width)`` tuple.
    """
    # numpy / cv2 array
    if hasattr(frame, "shape") and len(frame.shape) >= 2:
        return int(frame.shape[0]), int(frame.shape[1])
    # PIL Image
    size = getattr(frame, "size", None)
    if size is not None and len(size) == 2:
        return int(size[1]), int(size[0])
    # Fallback (should never happen with validated images).
    return 640, 640
