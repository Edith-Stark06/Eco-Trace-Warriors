"""Device registration and intelligence domain workflow package (P5.2 & P5.3)."""

from __future__ import annotations

from .brand import (
    CANONICAL_BRAND_MAP,
    BrandIntelligence,
    RuleBasedBrandIntelligence,
)
from .carbon import (
    CATEGORY_CO2E_FACTORS_KG_PER_KG,
    CarbonIntelligence,
    EstimatedBurdenCarbonIntelligence,
)
from .condition import (
    BaselineConditionIntelligence,
    ConditionIntelligence,
    VALID_CONDITION_STATES,
)
from .enrichment_models import (
    BrandAssessment,
    CarbonAssessment,
    ConditionAssessment,
    DeviceEnrichment,
    MaterialAssessment,
    MaterialItem,
)
from .enrichment_service import DeviceIntelligenceService
from .material import (
    CANONICAL_MATERIAL_PROFILES,
    MaterialIntelligence,
    ProfileBasedMaterialIntelligence,
)
from .models import (
    ConfidenceState,
    DeviceCandidate,
    DeviceRecord,
    RegistrationState,
    VALID_STATE_TRANSITIONS,
)
from .postgres_repository import PostgresDeviceRepository
from .repository import (
    DeviceRepository,
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from .service import DeviceRegistrationService

__all__ = [
    # Models & enums
    "ConfidenceState",
    "DeviceCandidate",
    "DeviceRecord",
    "RegistrationState",
    "VALID_STATE_TRANSITIONS",
    # Enrichment models
    "BrandAssessment",
    "ConditionAssessment",
    "MaterialItem",
    "MaterialAssessment",
    "CarbonAssessment",
    "DeviceEnrichment",
    # Intelligence interfaces & services
    "BrandIntelligence",
    "RuleBasedBrandIntelligence",
    "CANONICAL_BRAND_MAP",
    "ConditionIntelligence",
    "BaselineConditionIntelligence",
    "VALID_CONDITION_STATES",
    "MaterialIntelligence",
    "ProfileBasedMaterialIntelligence",
    "CANONICAL_MATERIAL_PROFILES",
    "CarbonIntelligence",
    "EstimatedBurdenCarbonIntelligence",
    "CATEGORY_CO2E_FACTORS_KG_PER_KG",
    "DeviceIntelligenceService",
    # Repositories & core service
    "DeviceRegistrationService",
    "DeviceRepository",
    "InMemoryDeviceRepository",
    "JsonFileDeviceRepository",
    "PostgresDeviceRepository",
]
