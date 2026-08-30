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
    DeviceEvent,
    DeviceEventType,
    DeviceRecord,
    RegistrationState,
    VALID_STATE_TRANSITIONS,
)
from .passport import (
    AuditFacet,
    BrandFacet,
    CarbonFacet,
    ConditionFacet,
    DetectionFacet,
    DeviceIdentityFacet,
    DevicePassport,
    LifecycleFacet,
    MaterialFacet,
    MaterialItemDetail,
    build_device_passport,
)
from .passport_verification import (
    PassportVerificationResult,
    VerificationCheckDetail,
    VerificationCheckStatus,
    VerificationStatus,
    canonicalize_passport,
    fingerprint_passport,
    verify_passport,
)
from .external_trust import (
    ExternalTrustAnchor,
    ExternalTrustLedger,
    ExternalTrustStatus,
    ExternalTrustVerificationResult,
    FabricExternalTrustLedger,
    FullTrustComparisonResult,
    InMemoryExternalTrustLedger,
    compute_overall_trust_status,
)
from .postgres_external_trust_repository import PostgresExternalTrustAnchorRepository
from .postgres_repository import PostgresDeviceRepository
from .postgres_trust_anchor_repository import PostgresTrustAnchorRepository
from .repository import (
    DeviceRepository,
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from .service import DeviceRegistrationService
from .trust_anchor import (
    DevicePassportTrustService,
    InMemoryTrustAnchorRepository,
    TrustAnchor,
    TrustAnchorPolicy,
    TrustAnchorRepository,
    TrustAnchorStatus,
    TrustAnchorVerification,
    TrustStatus,
    TrustStatusResult,
    build_trust_payload,
    canonicalize_trust_payload,
)

__all__ = [
    # Models & enums
    "ConfidenceState",
    "DeviceCandidate",
    "DeviceEvent",
    "DeviceEventType",
    "DeviceRecord",
    "RegistrationState",
    "VALID_STATE_TRANSITIONS",
    # Passport read model
    "DevicePassport",
    "build_device_passport",
    "DeviceIdentityFacet",
    "DetectionFacet",
    "BrandFacet",
    "ConditionFacet",
    "MaterialFacet",
    "MaterialItemDetail",
    "CarbonFacet",
    "LifecycleFacet",
    "AuditFacet",
    # Passport verification & trust layer (P5.7 & P5.8)
    "VerificationCheckStatus",
    "VerificationStatus",
    "VerificationCheckDetail",
    "PassportVerificationResult",
    "canonicalize_passport",
    "fingerprint_passport",
    "verify_passport",
    # Trust Anchor Abstraction & Persistence (P5.8, P5.9, P5.10)
    "TrustAnchor",
    "TrustAnchorStatus",
    "TrustAnchorPolicy",
    "TrustAnchorVerification",
    "TrustAnchorRepository",
    "InMemoryTrustAnchorRepository",
    "PostgresTrustAnchorRepository",
    "TrustStatus",
    "TrustStatusResult",
    "DevicePassportTrustService",
    "build_trust_payload",
    "canonicalize_trust_payload",
    # External / Blockchain Trust Ledger (P5.11)
    "ExternalTrustStatus",
    "ExternalTrustAnchor",
    "ExternalTrustVerificationResult",
    "FullTrustComparisonResult",
    "ExternalTrustLedger",
    "InMemoryExternalTrustLedger",
    "FabricExternalTrustLedger",
    "PostgresExternalTrustAnchorRepository",
    "compute_overall_trust_status",
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
