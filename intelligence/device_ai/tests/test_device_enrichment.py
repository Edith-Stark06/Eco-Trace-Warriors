"""Comprehensive test suite for Device Intelligence Enrichment (P5.3).

Covers:
- Brand OCR extraction, normalization, and UNKNOWN fallback.
- Baseline condition assessment policy and manual override.
- Material profile generation for all 8 canonical classes and unknown fallback.
- Carbon scoring determinism, versioning, and factor attribution.
- Device intelligence orchestration and record persistence.
- REST API endpoints (POST /devices/{id}/enrich, GET /devices/{id}/intelligence).
- 404 error handling for missing device records.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from device_ai.api import dependencies
from device_ai.application import create_app
from device_ai.configs.settings import Settings, get_settings
from device_ai.devices.brand import (
    CANONICAL_BRAND_MAP,
    RuleBasedBrandIntelligence,
)
from device_ai.devices.carbon import EstimatedBurdenCarbonIntelligence
from device_ai.devices.condition import BaselineConditionIntelligence
from device_ai.devices.enrichment_models import (
    BrandAssessment,
    CarbonAssessment,
    ConditionAssessment,
    DeviceEnrichment,
    MaterialAssessment,
    MaterialItem,
)
from device_ai.devices.enrichment_service import DeviceIntelligenceService
from device_ai.devices.material import (
    CANONICAL_MATERIAL_PROFILES,
    ProfileBasedMaterialIntelligence,
)
from device_ai.devices.models import (
    ConfidenceState,
    DeviceRecord,
    RegistrationState,
)
from device_ai.devices.repository import (
    InMemoryDeviceRepository,
    JsonFileDeviceRepository,
)
from device_ai.exceptions import DeviceNotFoundError
from device_ai.inference.class_map import CANONICAL_CLASSES


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="development",
        max_images=4,
        min_images=1,
        max_file_size=1 * 1024 * 1024,
        confidence_high_threshold=0.75,
        confidence_review_threshold=0.40,
        device_backend="memory",
        device_store_dir=tmp_path / "devices",
        material_profile_version="v1.0.0",
        carbon_model_version="v1.0.0",
        carbon_calculation_methodology="avoided_burden_co2e",
        log_level="WARNING",
    )


def _make_dummy_device(
    device_id: str = "DEV-2026-TEST-001",
    device_type: str = "laptop",
    class_id: int = 0,
) -> DeviceRecord:
    return DeviceRecord(
        device_id=device_id,
        capture_id="cap-test-123",
        class_id=class_id,
        device_type=device_type,
        confidence=0.88,
        confidence_state=ConfidenceState.HIGH_CONFIDENCE,
        bounding_box=(10, 20, 200, 150),
        model_version="1.0.0",
        inference_mode="single_model",
        registration_state=RegistrationState.DETECTED,
    )


# ---------------------------------------------------------------------------
# Brand Intelligence Unit Tests
# ---------------------------------------------------------------------------


def test_brand_ocr_success() -> None:
    """OCR text containing recognized manufacturer is matched with status CONFIRMED."""
    brand_intel = RuleBasedBrandIntelligence()
    result = brand_intel.assess_brand("Model Latitude 5420 by Dell Inc.", confidence=0.92)

    assert result.value == "Dell"
    assert result.status == "CONFIRMED"
    assert result.source == "ocr"
    assert result.confidence == 0.92
    assert result.raw_text.lower() == "dell"


def test_brand_ocr_unavailable() -> None:
    """Empty or absent OCR text yields UNKNOWN brand with source 'none'."""
    brand_intel = RuleBasedBrandIntelligence()
    res1 = brand_intel.assess_brand(None)
    assert res1.value is None
    assert res1.status == "UNKNOWN"
    assert res1.source == "none"
    assert res1.confidence is None

    res2 = brand_intel.assess_brand("   ")
    assert res2.value is None
    assert res2.status == "UNKNOWN"


def test_brand_normalization_multiple_brands() -> None:
    """Tests normalization across various canonical brands."""
    brand_intel = RuleBasedBrandIntelligence()

    test_cases = [
        ("Apple MacBook Pro A2338", "Apple"),
        ("SAMSUNG Electronics Co.", "Samsung"),
        ("Hewlett-Packard LaserJet", "HP"),
        ("Lenovo ThinkPad X1", "Lenovo"),
        ("Logitech MX Master 3S", "Logitech"),
        ("Sony Alpha A7 IV", "Sony"),
        ("Canon EOS R5", "Canon"),
        ("Bose QuietComfort 45", "Bose"),
    ]

    for raw_text, expected_canonical in test_cases:
        res = brand_intel.assess_brand(raw_text)
        assert res.value == expected_canonical
        assert res.status == "CONFIRMED"


def test_brand_unmatched_text() -> None:
    """Unmatched text returns explicit UNKNOWN with source 'ocr'."""
    brand_intel = RuleBasedBrandIntelligence()
    res = brand_intel.assess_brand("Product Serial SN-987654321 Made in India")
    assert res.value is None
    assert res.status == "UNKNOWN"
    assert res.source == "ocr"


def test_brand_never_infers_from_device_class() -> None:
    """Brand intelligence never guesses a brand from device class alone."""
    brand_intel = RuleBasedBrandIntelligence()
    # No OCR text passed -> cannot infer "Apple" or "Dell" even if device is laptop/phone
    res = brand_intel.assess_brand(None)
    assert res.value is None
    assert res.status == "UNKNOWN"


# ---------------------------------------------------------------------------
# Condition Intelligence Unit Tests
# ---------------------------------------------------------------------------


def test_condition_baseline_policy() -> None:
    """Baseline condition policy returns explicit UNKNOWN with pending_assessment provenance."""
    cond_intel = BaselineConditionIntelligence()
    res = cond_intel.assess_condition()

    assert res.value == "UNKNOWN"
    assert res.status == "UNAVAILABLE"
    assert res.source == "pending_assessment"
    assert res.confidence is None
    assert "pending" in res.notes.lower()


def test_condition_manual_override() -> None:
    """Manual condition inspection is honored when provided."""
    cond_intel = BaselineConditionIntelligence()
    res = cond_intel.assess_condition(manual_override="GOOD")

    assert res.value == "GOOD"
    assert res.status == "AVAILABLE"
    assert res.source == "manual_inspection"
    assert res.confidence == 1.0


# ---------------------------------------------------------------------------
# Material Intelligence Unit Tests
# ---------------------------------------------------------------------------


def test_material_profile_all_canonical_classes() -> None:
    """Every canonical class (0..7) has a defined material profile with basis 'device_profile'."""
    mat_intel = ProfileBasedMaterialIntelligence()

    for class_id, class_name in CANONICAL_CLASSES.items():
        assessment = mat_intel.assess_materials(class_name, version="v1.0.0")

        assert assessment.source == "device_profile"
        assert assessment.version == "v1.0.0"
        assert assessment.total_mass_g > 0
        assert len(assessment.materials) >= 3

        for item in assessment.materials:
            assert item.basis == "device_profile"
            assert item.mass_g > 0
            assert item.category in ("metals", "plastics", "glass", "circuit_boards", "battery", "other")


def test_material_profile_unknown_class_fallback() -> None:
    """Unmapped device class gets deterministic fallback profile."""
    mat_intel = ProfileBasedMaterialIntelligence()
    assessment = mat_intel.assess_materials("unrecognized_gadget", version="v1.0.0")

    assert assessment.source == "device_profile"
    assert assessment.total_mass_g == 500.0
    assert "fallback" in assessment.notes.lower()


# ---------------------------------------------------------------------------
# Carbon Intelligence Unit Tests
# ---------------------------------------------------------------------------


def test_carbon_scoring_determinism() -> None:
    """Carbon scoring produces exact, deterministic avoided CO2e calculation."""
    mat_intel = ProfileBasedMaterialIntelligence()
    carbon_intel = EstimatedBurdenCarbonIntelligence()

    laptop_materials = mat_intel.assess_materials("laptop")
    carbon_assessment = carbon_intel.assess_carbon(laptop_materials)

    # Laptop has:
    # metals: 600g (0.6 kg * 5.0 = 3.0 kg CO2e)
    # plastics: 500g (0.5 kg * 1.8 = 0.9 kg CO2e)
    # circuit_boards: 300g (0.3 kg * 18.0 = 5.4 kg CO2e)
    # battery: 300g (0.3 kg * 8.5 = 2.55 kg CO2e)
    # glass: 100g (0.1 kg * 0.7 = 0.07 kg CO2e)
    # Total = 3.0 + 0.9 + 5.4 + 2.55 + 0.07 = 11.92 kg CO2e
    expected_score = 11.92
    assert pytest.approx(carbon_assessment.carbon_score, 1e-3) == expected_score
    assert carbon_assessment.source == "estimated_project_model"
    assert carbon_assessment.methodology == "avoided_burden_co2e"
    assert carbon_assessment.version == "v1.0.0"
    assert "metals" in carbon_assessment.contributing_factors
    assert "circuit_boards" in carbon_assessment.contributing_factors


# ---------------------------------------------------------------------------
# Enrichment Service Orchestration Tests
# ---------------------------------------------------------------------------


def test_device_intelligence_service_orchestration(test_settings: Settings) -> None:
    """DeviceIntelligenceService updates DeviceRecord and populates enrichment metadata."""
    repo = InMemoryDeviceRepository()
    device = _make_dummy_device(device_id="DEV-2026-ENRICH-01", device_type="laptop")
    repo.save(device)

    service = DeviceIntelligenceService(
        repository=repo,
        settings=test_settings,
    )

    updated_record, enrichment = service.enrich_device(
        "DEV-2026-ENRICH-01",
        ocr_text="Dell XPS 13 Laptop",
        ocr_confidence=0.95,
    )

    assert updated_record.device_id == "DEV-2026-ENRICH-01"
    assert updated_record.condition == "UNKNOWN"
    assert updated_record.materials is not None
    assert len(updated_record.materials) >= 4
    assert updated_record.carbon_score is not None
    assert updated_record.carbon_score > 0

    assert enrichment.brand.value == "Dell"
    assert enrichment.brand.status == "CONFIRMED"
    assert enrichment.condition.value == "UNKNOWN"
    assert enrichment.materials.total_mass_g > 0
    assert enrichment.carbon.carbon_score == updated_record.carbon_score

    # Check persistence
    persisted = repo.get("DEV-2026-ENRICH-01")
    assert persisted is not None
    assert persisted.carbon_score == updated_record.carbon_score
    assert "enrichment" in persisted.metadata


def test_enrich_device_json_repository_persistence(tmp_path: Path, test_settings: Settings) -> None:
    """Enriched device records are successfully persisted in JsonFileDeviceRepository."""
    repo = JsonFileDeviceRepository(tmp_path / "devices_json_test")
    device = _make_dummy_device(device_id="DEV-2026-JSON-01", device_type="smartphone", class_id=1)
    repo.save(device)

    service = DeviceIntelligenceService(
        repository=repo,
        settings=test_settings,
    )

    service.enrich_device(
        "DEV-2026-JSON-01",
        ocr_text="Apple iPhone 14",
    )

    loaded = repo.get("DEV-2026-JSON-01")
    assert loaded is not None
    assert loaded.device_type == "smartphone"
    assert loaded.carbon_score is not None
    assert "enrichment" in loaded.metadata
    assert loaded.metadata["brand"]["value"] == "Apple"


def test_enrichment_not_found_raises_exception(test_settings: Settings) -> None:
    """Enriching a non-existent device raises DeviceNotFoundError."""
    repo = InMemoryDeviceRepository()
    service = DeviceIntelligenceService(repository=repo, settings=test_settings)

    with pytest.raises(DeviceNotFoundError, match="not found"):
        service.enrich_device("DEV-UNKNOWN-999")


# ---------------------------------------------------------------------------
# API Integration Tests (POST /enrich & GET /intelligence)
# ---------------------------------------------------------------------------


def test_api_enrich_and_get_intelligence(test_settings: Settings) -> None:
    """API endpoints POST /devices/{id}/enrich and GET /devices/{id}/intelligence work correctly."""
    repo = InMemoryDeviceRepository()
    dev = _make_dummy_device(device_id="DEV-2026-API-01", device_type="monitor", class_id=3)
    repo.save(dev)

    dependencies.reset_dependency_caches()
    get_settings.cache_clear()
    app = create_app(test_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[dependencies.get_device_repository] = lambda: repo

    with TestClient(app) as client:
        # 1. POST /devices/{id}/enrich
        enrich_resp = client.post(
            "/devices/DEV-2026-API-01/enrich",
            json={"ocr_text": "LG UltraFine 4K Monitor", "ocr_confidence": 0.90},
            headers={"X-Request-ID": "req-enrich-01"},
        )
        assert enrich_resp.status_code == 200, enrich_resp.text
        enrich_data = enrich_resp.json()

        assert enrich_data["success"] is True
        assert enrich_data["device"]["device_id"] == "DEV-2026-API-01"
        assert enrich_data["device"]["device_type"] == "monitor"
        assert enrich_data["intelligence"]["brand"]["value"] == "LG"
        assert enrich_data["intelligence"]["brand"]["status"] == "CONFIRMED"
        assert enrich_data["intelligence"]["condition"]["value"] == "UNKNOWN"
        assert enrich_data["intelligence"]["materials"]["source"] == "device_profile"
        assert enrich_data["intelligence"]["carbon"]["source"] == "estimated_project_model"
        assert enrich_data["intelligence"]["carbon"]["carbon_score"] > 0
        assert enrich_data["request_id"] == "req-enrich-01"

        # 2. GET /devices/{id}/intelligence
        get_intel_resp = client.get(
            "/devices/DEV-2026-API-01/intelligence",
            headers={"X-Request-ID": "req-intel-02"},
        )
        assert get_intel_resp.status_code == 200
        get_intel_data = get_intel_resp.json()
        assert get_intel_data["intelligence"]["brand"]["value"] == "LG"
        assert get_intel_data["intelligence"]["device_id"] == "DEV-2026-API-01"

        # 3. GET /devices/{non_existent}/intelligence -> 404
        missing_resp = client.get("/devices/DEV-DOES-NOT-EXIST/intelligence")
        assert missing_resp.status_code == 404
        assert missing_resp.json()["error"]["code"] == "DEVICE_NOT_FOUND"

    app.dependency_overrides.clear()
    dependencies.reset_dependency_caches()
