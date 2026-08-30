# P5.6 — EcoTrace Device Passport & Traceability Walkthrough Report

## Executive Summary

Phase **P5.6 EcoTrace Device Passport & Traceability Read Layer** implements a unified, aggregated domain read model (`DevicePassport`) and REST API (`GET /devices/{device_id}/passport`) aggregating device identity, computer vision detection, brand intelligence, condition assessment, material composition, avoided carbon footprint, lifecycle state, and chronological audit history into a single authoritative digital product passport without mutating underlying entities or fabricating synthetic data.

---

## 1. Architectural Design & Read Model

### Aggregation Pipeline
```text
DeviceRecord (P5.2 / P5.4)
    +
DeviceEnrichment (P5.3)
    +
DeviceEvent Log (P5.5)
    +
Detection & Model Metadata (P5.0 / P5.1)
    ↓
build_device_passport(...) [Pure Function]
    ↓
DevicePassport (Domain Read Model)
    ↓
GET /devices/{device_id}/passport
```

### Core Passport Facets
1. **Device Identity (`DeviceIdentityFacet`)**: `device_id`, `eco_id`, `device_type`, `class_id`, `capture_id`, `registration_timestamp`, `created_at`, `updated_at`.
2. **Detection Metadata (`DetectionFacet`)**: `confidence`, `confidence_state`, `bounding_box`, `inference_mode`, `model_version`.
3. **Brand Intelligence (`BrandFacet`)**: `brand`, `status`, `source`, `confidence`, `raw_text` (matched OCR text).
4. **Condition Intelligence (`ConditionFacet`)**: `condition`, `status`, `source`, `notes`.
5. **Material Composition (`MaterialFacet`)**: `materials` breakdown (material, category, mass_g, recoverable, hazardous, basis), `total_mass_g`, `source`, `version`, `notes`.
6. **Carbon Footprint (`CarbonFacet`)**: `carbon_score` (avoided CO2e in kg), `contributing_factors` by category, `methodology`, `source`, `version`, `notes`.
7. **Lifecycle State (`LifecycleFacet`)**: `current_state` (DETECTED, CONFIRMED, REGISTERED), `is_confirmed`, `is_registered`, `is_enriched`.
8. **Audit Trail (`AuditFacet`)**: `total_events`, `events` (chronological list of events with event IDs, timestamps, capture IDs, and context metadata).

---

## 2. Invariants & Read-Only Guarantees

- **Zero-Mutation Invariant**: Retrieving or building a passport performs **zero writes** to disk or database, does **not mutate** `DeviceRecord`, and emits **zero new audit events**.
- **Explicit Pending/Unavailable State**: If a device exists but has not undergone enrichment (P5.3), all enrichment facets are populated with explicit `UNAVAILABLE` or `PENDING` signals rather than guessing or fabricating synthetic values.
- **Repository Parity**: Functions seamlessly across `InMemoryDeviceRepository`, `JsonFileDeviceRepository`, and `PostgresDeviceRepository`.

---

## 3. API Documentation

### Endpoint
`GET /devices/{device_id}/passport`

### Example Response (`GET /devices/DEV-2026-B8196E01-01/passport`):
```json
{
  "success": true,
  "request_id": "req-pass-view-01",
  "passport": {
    "device_id": "DEV-2026-B8196E01-01",
    "eco_id": "ET-2026-B8196E01",
    "identity": {
      "device_id": "DEV-2026-B8196E01-01",
      "eco_id": "ET-2026-B8196E01",
      "device_type": "tablet",
      "class_id": 2,
      "capture_id": "cap-api-pass-01",
      "registration_timestamp": "2026-08-30T02:43:28.718000+00:00",
      "created_at": "2026-08-30T02:43:28.718000+00:00",
      "updated_at": "2026-08-30T02:43:28.726000+00:00"
    },
    "detection": {
      "confidence": 0.91,
      "confidence_state": "HIGH_CONFIDENCE",
      "bounding_box": [15, 25, 180, 240],
      "inference_mode": "single_model",
      "model_version": "1.0.0"
    },
    "brand": {
      "brand": "Apple",
      "status": "CONFIRMED",
      "source": "ocr",
      "confidence": 0.96,
      "raw_text": "Apple"
    },
    "condition": {
      "condition": "UNKNOWN",
      "status": "UNAVAILABLE",
      "source": "pending_assessment",
      "notes": "Baseline condition policy: visual condition assessment model pending."
    },
    "material": {
      "materials": [
        {
          "material": "Aluminium chassis",
          "category": "metals",
          "mass_g": 200.0,
          "recoverable": true,
          "hazardous": false,
          "basis": "nominal_profile"
        },
        {
          "material": "Display glass / touch panel",
          "category": "glass",
          "mass_g": 120.0,
          "recoverable": true,
          "hazardous": false,
          "basis": "nominal_profile"
        },
        {
          "material": "Lithium-ion battery",
          "category": "batteries",
          "mass_g": 90.0,
          "recoverable": true,
          "hazardous": true,
          "basis": "nominal_profile"
        },
        {
          "material": "Motherboard / PCB assembly",
          "category": "circuit_boards",
          "mass_g": 60.0,
          "recoverable": true,
          "hazardous": false,
          "basis": "nominal_profile"
        },
        {
          "material": "Internal plastic brackets",
          "category": "plastics",
          "mass_g": 30.0,
          "recoverable": true,
          "hazardous": false,
          "basis": "nominal_profile"
        }
      ],
      "total_mass_g": 500.0,
      "source": "device_profile",
      "version": "v1.0.0",
      "notes": "Nominal composition profile for category 'tablet'."
    },
    "carbon": {
      "carbon_score": 3.32,
      "contributing_factors": {
        "metals": 1.76,
        "circuit_boards": 1.15,
        "batteries": 0.28,
        "glass": 0.08,
        "plastics": 0.05
      },
      "methodology": "avoided_burden_co2e",
      "source": "estimated_project_model",
      "version": "v1.0.0",
      "notes": "Avoided burden score computed from nominal material fractions for 'tablet'."
    },
    "lifecycle": {
      "current_state": "CONFIRMED",
      "is_confirmed": true,
      "is_registered": false,
      "is_enriched": true
    },
    "audit": {
      "total_events": 3,
      "events": [
        {
          "event_id": "evt-7dfa91b2c401",
          "device_id": "DEV-2026-B8196E01-01",
          "event_type": "DEVICE_DETECTED",
          "timestamp": "2026-08-30T02:43:28.718000+00:00",
          "capture_id": "cap-api-pass-01",
          "metadata": {
            "confidence": 0.91,
            "device_type": "tablet"
          }
        },
        {
          "event_id": "evt-812ca94efbc0",
          "device_id": "DEV-2026-B8196E01-01",
          "event_type": "DEVICE_CONFIRMED",
          "timestamp": "2026-08-30T02:43:28.723000+00:00",
          "capture_id": "cap-api-pass-01",
          "metadata": {
            "state": "CONFIRMED"
          }
        },
        {
          "event_id": "evt-9a0cb4901f42",
          "device_id": "DEV-2026-B8196E01-01",
          "event_type": "DEVICE_ENRICHED",
          "timestamp": "2026-08-30T02:43:28.726000+00:00",
          "capture_id": "cap-api-pass-01",
          "metadata": {
            "brand": "Apple",
            "condition": "UNKNOWN",
            "carbon_score": 3.32
          }
        }
      ]
    },
    "generated_at": "2026-08-30T02:43:28.730000+00:00"
  }
}
```

---

## 4. Test Verification Summary

- **P5.6 Tests (`test_p56_device_passport.py`)**: **9 passed**
- **P4.3-P5.6 Regression Test Suite**: **94 passed**
- **Full Active Test Suite**: **899 passed**
- **Failures**: 0.

---

## 5. Cryptographic Safety & Immutability Audit

| Asset | Expected SHA-256 | Verified SHA-256 | Status |
|---|---|---|:---:|
| `P4.4.2 YOLO11n` | `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92` | `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92` | **MATCH** |
| `P4.11 Targeted Aug` | `ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c` | `ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c` | **MATCH** |
| `P4.12 YOLO11s` | `96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc` | `96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc` | **MATCH** |
| `P4.14 Targeted Aug` | `8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81` | `8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81` | **MATCH** |
| `P4.5 Data YAML` | `b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b` | `b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b` | **MATCH** |
| `P4.7 Data YAML` | `5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284` | `5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284` | **MATCH** |

- **Git HEAD**: `fb9b084e727ef14a4bff9b0e7814c884b7b7157f`
- **Protected Directories**: 100% untouched.
