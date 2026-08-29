"""Prediction pipeline: orchestration of the model components.

The :class:`PredictionPipeline` wires the individual model components
(detector → embedding → condition → OCR → material estimator) into the
end-to-end flow described in the milestone spec, then derives the EcoID and
carbon score. Components are injected, so swapping a mock for a real model
is a construction-time concern only.

The pipeline holds **no HTTP** and **no business logic** beyond composing
model outputs into the response value object — decisions belong to the
backend (``docs/engineering/08_AI.md``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..exceptions import DeviceAIError, InferenceError, ModelNotLoadedError
from ..preprocessing.image_loader import LoadedImage
from .ecoid import EcoIDGenerator
from .predictor import (
    ConditionAssessor,
    ConditionResult,
    DetectionResult,
    Detector,
    EmbeddingEncoder,
    EmbeddingResult,
    MaterialEstimator,
    MaterialResult,
    MockConditionAssessor,
    MockDetector,
    MockEmbeddingEncoder,
    MockMaterialEstimator,
    MockOCREngine,
    OCREngine,
    OCRResult,
)

# Base carbon score awarded to any recovered device, before adjustments.
_BASE_CARBON_SCORE = 50.0

# Per-condition multiplier applied to the recoverable-material contribution:
# a device in better condition yields more recoverable value.
_CONDITION_WEIGHTS: dict[str, float] = {
    "Excellent": 1.0,
    "Good": 0.85,
    "Fair": 0.65,
    "Poor": 0.4,
}

# Relative environmental value of recovering each material (per unit
# fraction). Illustrative weights used to derive a single carbon score.
_MATERIAL_CARBON_VALUE: dict[str, float] = {
    "aluminum": 60.0,
    "copper": 55.0,
    "pcb": 45.0,
    "battery": 40.0,
    "plastic": 15.0,
}


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """The full result of a prediction, ready for API serialization.

    Attributes:
        eco_id: Human-readable EcoID (``ET-YYYY-XXXXXXXX``).
        detection: Device type/brand result.
        condition: Condition assessment result.
        ocr: OCR extraction result.
        materials: Estimated material composition.
        embedding: Embedding reference.
        carbon_score: Derived environmental recovery score.
        model_version: Aggregate model/service version tag.
    """

    eco_id: str
    detection: DetectionResult
    condition: ConditionResult
    ocr: OCRResult
    materials: MaterialResult
    embedding: EmbeddingResult
    carbon_score: float
    model_version: str


class PredictionPipeline:
    """Compose model components into the end-to-end prediction flow.

    Components are injected to keep the pipeline testable and to allow real
    models to replace mocks without touching this class.

    Args:
        detector: Device type/brand detector.
        condition: Condition assessor.
        ocr: OCR engine.
        material: Material estimator.
        embedding: Embedding encoder.
        ecoid_generator: EcoID generator.
        model_version: Version tag reported with every prediction.
    """

    def __init__(
        self,
        *,
        detector: Detector,
        condition: ConditionAssessor,
        ocr: OCREngine,
        material: MaterialEstimator,
        embedding: EmbeddingEncoder,
        ecoid_generator: EcoIDGenerator,
        model_version: str,
    ) -> None:
        self._detector = detector
        self._condition = condition
        self._ocr = ocr
        self._material = material
        self._embedding = embedding
        self._ecoid = ecoid_generator
        self._model_version = model_version

    def predict(self, images: list[LoadedImage]) -> PredictionResult:
        """Run the full prediction pipeline over validated images.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A :class:`PredictionResult` aggregating every component output.
        """
        result, _ = self.predict_with_timing(images)
        return result

    def predict_with_timing(
        self, images: list[LoadedImage]
    ) -> tuple[PredictionResult, dict[str, float]]:
        """Run the prediction pipeline and measure per-stage execution latency.

        Separates detector forward pass from downstream parsing and aggregation.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A tuple of ``(PredictionResult, timing_dict)`` where timing_dict
            contains ``inference_ms`` and ``postprocessing_ms``.

        Raises:
            ModelNotLoadedError: If the detector is not ready to serve.
            InferenceError: If an unexpected error occurs during inference.
        """
        t_inf_start = time.perf_counter()
        try:
            detection = self._detector.detect(images)
        except DeviceAIError:
            raise
        except Exception as exc:
            raise InferenceError(
                f"Model detector inference failed: {exc}",
                details={"error": str(exc), "detector": self._detector.name},
            ) from exc
        t_inf_end = time.perf_counter()
        inference_ms = round((t_inf_end - t_inf_start) * 1000, 2)

        t_post_start = time.perf_counter()
        embedding = self._embedding.encode(images)
        condition = self._condition.assess(images)
        ocr = self._ocr.extract(images)
        materials = self._material.estimate(images, detection.device_type)

        carbon_score = self._carbon_score(condition, materials)
        eco_id = self._ecoid.generate()
        t_post_end = time.perf_counter()
        postprocessing_ms = round((t_post_end - t_post_start) * 1000, 2)

        result = PredictionResult(
            eco_id=eco_id,
            detection=detection,
            condition=condition,
            ocr=ocr,
            materials=materials,
            embedding=embedding,
            carbon_score=carbon_score,
            model_version=self._model_version,
        )
        timing = {
            "inference_ms": inference_ms,
            "postprocessing_ms": postprocessing_ms,
        }
        return result, timing

    def health(self) -> dict[str, bool]:
        """Report readiness of each underlying component.

        Returns:
            Mapping of component name to readiness flag.
        """
        components = (
            self._detector,
            self._condition,
            self._ocr,
            self._material,
            self._embedding,
        )
        return {component.name: component.is_ready for component in components}

    @property
    def detector(self) -> Detector:
        """Return the underlying detector component."""
        return self._detector

    @staticmethod
    def _carbon_score(
        condition: ConditionResult,
        materials: MaterialResult,
    ) -> float:
        """Derive a single carbon-recovery score from component outputs.

        The score combines a base value with a condition-weighted sum of the
        environmental value of each recoverable material. The result is
        clamped to ``[0, 100]``.

        Args:
            condition: The assessed device condition.
            materials: The estimated material composition.

        Returns:
            A carbon score in the range [0.0, 100.0], rounded to one decimal.
        """
        condition_weight = _CONDITION_WEIGHTS.get(condition.label, 0.5)
        material_value = sum(
            fraction * _MATERIAL_CARBON_VALUE.get(material, 20.0)
            for material, fraction in materials.composition.items()
        )
        raw = _BASE_CARBON_SCORE + condition_weight * material_value
        return round(max(0.0, min(100.0, raw)), 1)


def build_mock_pipeline(
    *,
    model_version: str,
    year: int,
    sequence_start: int = 1,
) -> PredictionPipeline:
    """Construct a pipeline wired entirely with mock components.

    This is the default factory for milestone M1.1. Replacing it with a
    real-model factory later is a single dependency-provider change.

    Args:
        model_version: Version tag reported with predictions.
        year: Year embedded in generated EcoIDs.
        sequence_start: First sequence number for the EcoID generator.

    Returns:
        A ready-to-use :class:`PredictionPipeline`.
    """
    return PredictionPipeline(
        detector=MockDetector(),
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=year, sequence_start=sequence_start),
        model_version=model_version,
    )


def build_detection_pipeline(
    *,
    detector: Detector,
    model_version: str,
    year: int,
    sequence_start: int = 1,
) -> PredictionPipeline:
    """Construct a pipeline with a real detector and mock everything else.

    Milestone M1.4 replaces only the detector; the condition, OCR, material and
    embedding components remain deterministic mocks until their own sprints.
    The API contract is identical to :func:`build_mock_pipeline` — only the
    ``device_type``/``brand``/``confidence`` source changes.

    Args:
        detector: The real (injected) detector, e.g. a
            :class:`~device_ai.inference.yolo_detector.YOLODetector`.
        model_version: Version tag reported with predictions.
        year: Year embedded in generated EcoIDs.
        sequence_start: First sequence number for the EcoID generator.

    Returns:
        A ready-to-use :class:`PredictionPipeline` driven by ``detector``.
    """
    return PredictionPipeline(
        detector=detector,
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=year, sequence_start=sequence_start),
        model_version=model_version,
    )
