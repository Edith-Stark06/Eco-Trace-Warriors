"""Device Intelligence Enrichment Service (P5.3).

Orchestrates the multi-facet enrichment pipeline:
DeviceRecord -> Brand -> Condition -> Materials -> Carbon -> Enriched Record.

Preserves the original detection records, applies explicit provenance,
updates the persistent DeviceRecord, and returns the structured enrichment representation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import uuid

from loguru import logger

from ..configs.settings import Settings
from ..exceptions import DeviceNotFoundError
from .brand import BrandIntelligence, RuleBasedBrandIntelligence
from .carbon import CarbonIntelligence, EstimatedBurdenCarbonIntelligence
from .condition import BaselineConditionIntelligence, ConditionIntelligence
from .enrichment_models import (
    BrandAssessment,
    CarbonAssessment,
    ConditionAssessment,
    DeviceEnrichment,
    MaterialAssessment,
)
from .material import MaterialIntelligence, ProfileBasedMaterialIntelligence
from .models import DeviceEvent, DeviceEventType, DeviceRecord
from .repository import DeviceRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeviceIntelligenceService:
    """Orchestrator for device intelligence enrichment."""

    def __init__(
        self,
        *,
        repository: DeviceRepository,
        settings: Settings,
        brand_intelligence: BrandIntelligence | None = None,
        condition_intelligence: ConditionIntelligence | None = None,
        material_intelligence: MaterialIntelligence | None = None,
        carbon_intelligence: CarbonIntelligence | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._brand = brand_intelligence or RuleBasedBrandIntelligence()
        self._condition = condition_intelligence or BaselineConditionIntelligence()
        self._material = material_intelligence or ProfileBasedMaterialIntelligence()
        self._carbon = carbon_intelligence or EstimatedBurdenCarbonIntelligence()

    def enrich_device(
        self,
        device_id: str,
        *,
        ocr_text: str | None = None,
        ocr_confidence: float | None = None,
        manual_condition: str | None = None,
    ) -> tuple[DeviceRecord, DeviceEnrichment]:
        """Run intelligence enrichment pipeline on a device and persist changes.

        Args:
            device_id: Identifier of the target device record.
            ocr_text: Optional recognized OCR text string for brand discovery.
            ocr_confidence: Optional OCR recognition confidence score.
            manual_condition: Optional condition inspection label.

        Returns:
            A tuple of ``(updated_device_record, device_enrichment)``.

        Raises:
            DeviceNotFoundError: If ``device_id`` does not exist in repository.
        """
        record = self._repository.get(device_id)
        if record is None:
            raise DeviceNotFoundError(
                f"Device '{device_id}' not found for intelligence enrichment.",
                details={"device_id": device_id},
            )

        # 1. Brand Intelligence
        brand_assessment = self._brand.assess_brand(
            ocr_text=ocr_text,
            confidence=ocr_confidence,
        )

        # 2. Condition Intelligence
        condition_assessment = self._condition.assess_condition(
            manual_override=manual_condition,
        )

        # 3. Material Intelligence
        material_assessment = self._material.assess_materials(
            device_type=record.device_type,
            version=self._settings.material_profile_version,
        )

        # 4. Carbon Intelligence
        carbon_assessment = self._carbon.assess_carbon(
            material_assessment=material_assessment,
            version=self._settings.carbon_model_version,
            methodology=self._settings.carbon_calculation_methodology,
        )

        # 5. Assemble Aggregate Enrichment
        enrichment = DeviceEnrichment(
            device_id=device_id,
            brand=brand_assessment,
            condition=condition_assessment,
            materials=material_assessment,
            carbon=carbon_assessment,
            enriched_at=_utc_now(),
        )

        # 6. Mutate Record Facets & Metadata
        record.condition = condition_assessment.value
        record.materials = {m.material: m.mass_g for m in material_assessment.materials}
        record.carbon_score = carbon_assessment.carbon_score
        record.metadata["brand"] = brand_assessment.to_dict()
        record.metadata["enrichment"] = enrichment.to_dict()
        record.updated_at = _utc_now()

        # 7. Persist Updated Record
        enrich_event = DeviceEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            device_id=record.device_id,
            event_type=DeviceEventType.DEVICE_ENRICHED,
            timestamp=_utc_now(),
            capture_id=record.capture_id,
            metadata={
                "brand": brand_assessment.value,
                "condition": condition_assessment.value,
                "carbon_score": carbon_assessment.carbon_score,
            },
        )

        if hasattr(self._repository, "save_with_event"):
            self._repository.save_with_event(record, enrich_event)
        else:
            self._repository.save(record)
            self._repository.append_event(enrich_event)

        if hasattr(self._repository, "save_enrichment"):
            self._repository.save_enrichment(enrichment)

        logger.bind(
            device_id=device_id,
            brand=brand_assessment.value,
            condition=condition_assessment.value,
            carbon_score=carbon_assessment.carbon_score,
        ).info("Device intelligence enriched and persisted")

        return record, enrichment

    def get_device_intelligence(
        self,
        device_id: str,
    ) -> tuple[DeviceRecord, DeviceEnrichment]:
        """Retrieve existing or compute baseline intelligence for a device record.

        Args:
            device_id: Target device identifier.

        Returns:
            A tuple of ``(device_record, device_enrichment)``.

        Raises:
            DeviceNotFoundError: If ``device_id`` is not found.
        """
        record = self._repository.get(device_id)
        if record is None:
            raise DeviceNotFoundError(
                f"Device '{device_id}' not found.",
                details={"device_id": device_id},
            )

        if "enrichment" in record.metadata:
            enrichment = DeviceEnrichment.from_dict(record.metadata["enrichment"])
            return record, enrichment

        # Generate on-the-fly baseline enrichment if not yet enriched
        return self.enrich_device(device_id)
