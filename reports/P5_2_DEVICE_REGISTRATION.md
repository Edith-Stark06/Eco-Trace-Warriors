# EcoTrace India — P5.2 Device Registration & Intelligence Workflow Report

**Status:** Completed & Validated
**Date:** 2026-08-30
**Phase:** P5.2 Device Registration & Intelligence Workflow
**Service:** `intelligence/device_ai` (FastAPI Microservice)
**Git HEAD:** `48b4217fca2a9f619fb7ff6abb3c818a17daeeb0`

---

## 1. Executive Summary

Phase **P5.2** elevates the computer-vision inference capabilities established in P5.0 and hardened in P5.1 into a domain-driven device registration and intelligence workflow.

The core pipeline transforms raw user capture images into structured, policy-validated domain records:

$$\text{Image Capture} \longrightarrow \text{AI Detection} \longrightarrow \text{Device Candidate(s)} \longrightarrow \text{Normalized Domain Records} \longrightarrow \text{Lifecycle State Machine}$$

### Key Capabilities & Architectural Principles
1. **Multi-Detection Preservation**: A single capture image can contain multiple electronic devices. Each detected object is instantiated as an independent `DeviceCandidate` and `DeviceRecord` sharing a common `capture_id`, preventing silent loss of co-located devices.
2. **Configurable Confidence Policy**: Confidence states are classified using application configuration rather than magic numbers:
   - $\ge 0.75 \implies \text{HIGH\_CONFIDENCE}$
   - $0.40 \le \text{conf} < 0.75 \implies \text{REVIEW\_REQUIRED}$
   - $< 0.40 \implies \text{LOW\_CONFIDENCE}$
3. **Explicit Lifecycle State Machine**: Enforces valid progression without premature blockchain or recycling claims:
   $$\text{DETECTED} \longrightarrow \text{CONFIRMED} \longrightarrow \text{REGISTERED}$$
4. **Clean Persistence Abstraction**: Storage-agnostic `DeviceRepository` protocol with both `InMemoryDeviceRepository` (default/testing) and `JsonFileDeviceRepository` (durable file tree).
5. **Separation of Concerns**: Device registration consumes the high-level `PredictionPipeline` dependency; no ML models or weights are duplicated or directly coupled to domain entities.
6. **Condition / Materials / Carbon Score**: Faithfully marked as `null` / pending per Step 7 until dedicated downstream subsystems are integrated.

---

## 2. API Endpoints & Request/Response Contracts

### `POST /devices/register`
Multipart upload registering one or more device candidates from capture images.

#### Request
- Form Data: `images: list[UploadFile]` (1 to 6 files), `capture_id: str` (optional)
- Headers: `X-Request-ID: str` (optional)

#### Response (HTTP 200)
```json
{
  "success": true,
  "capture_id": "cap-sess-101",
  "total_detected": 2,
  "devices": [
    {
      "device_id": "DEV-2026-SESS101-01",
      "capture_id": "cap-sess-101",
      "class_id": 0,
      "device_type": "laptop",
      "confidence": 0.8912,
      "confidence_state": "HIGH_CONFIDENCE",
      "bounding_box": [20, 20, 300, 200],
      "model_version": "1.0.0",
      "inference_mode": "single_model",
      "registration_state": "DETECTED",
      "condition": null,
      "materials": null,
      "carbon_score": null,
      "metadata": { "eco_id": "ET-2026-A1B2C3D4", "image_count": 1 },
      "created_at": "2026-08-30T01:27:00+00:00",
      "updated_at": "2026-08-30T01:27:00+00:00"
    },
    {
      "device_id": "DEV-2026-SESS101-02",
      "capture_id": "cap-sess-101",
      "class_id": 5,
      "device_type": "mouse",
      "confidence": 0.6540,
      "confidence_state": "REVIEW_REQUIRED",
      "bounding_box": [310, 150, 380, 210],
      "model_version": "1.0.0",
      "inference_mode": "single_model",
      "registration_state": "DETECTED",
      "condition": null,
      "materials": null,
      "carbon_score": null,
      "metadata": { "eco_id": "ET-2026-A1B2C3D4", "image_count": 1 },
      "created_at": "2026-08-30T01:27:00+00:00",
      "updated_at": "2026-08-30T01:27:00+00:00"
    }
  ],
  "inference_mode": "single_model",
  "timing": {
    "preprocessing_ms": 3.45,
    "inference_ms": 12.80,
    "postprocessing_ms": 1.95,
    "total_ms": 18.20
  },
  "request_id": "req-trace-001"
}
```

### `GET /devices/{device_id}`
Retrieves a single persisted device domain record.

### `POST /devices/{device_id}/confirm`
Transitions a device candidate from `DETECTED` to `CONFIRMED`.

### `POST /devices/{device_id}/finalize`
Transitions a device record from `CONFIRMED` to `REGISTERED`.

### `GET /devices`
Lists devices with pagination (`limit`, `offset`) and optional `capture_id` filtering.

---

## 3. Files Created & Modified

| File | Action | Purpose |
|---|---|---|
| `intelligence/device_ai/devices/models.py` | CREATED | `ConfidenceState`, `RegistrationState`, `DeviceCandidate`, `DeviceRecord` models. |
| `intelligence/device_ai/devices/repository.py` | CREATED | `DeviceRepository` protocol, `InMemoryDeviceRepository`, `JsonFileDeviceRepository`. |
| `intelligence/device_ai/devices/service.py` | CREATED | `DeviceRegistrationService` orchestration logic. |
| `intelligence/device_ai/devices/__init__.py` | CREATED | Devices package exports. |
| `intelligence/device_ai/api/device_schemas.py` | CREATED | Pydantic request/response schemas for device endpoints. |
| `intelligence/device_ai/api/device_routes.py` | CREATED | FastAPI `/devices/*` route handlers. |
| `intelligence/device_ai/exceptions.py` | MODIFIED | Added typed exceptions (`DeviceNotFoundError`, `DuplicateDeviceError`, `InvalidStateTransitionError`, `NoDetectionsForRegistrationError`, `InvalidDeviceClassError`, `DevicePersistenceError`). |
| `intelligence/device_ai/configs/settings.py` | MODIFIED | Added `device_backend`, `device_store_dir`, `confidence_high_threshold`, `confidence_review_threshold`. |
| `intelligence/device_ai/.env.example` | MODIFIED | Documented P5.2 environment variables. |
| `intelligence/device_ai/api/dependencies.py` | MODIFIED | Added `get_device_repository` and `get_device_service` providers. |
| `intelligence/device_ai/application.py` | MODIFIED | Registered `device_router` in `create_app`. |
| `intelligence/device_ai/tests/test_device_workflow.py` | CREATED | Comprehensive test suite covering domain models, repository, state machine, and API endpoints. |

---

## 4. Test Execution & Verification

```text
================================== TEST SUMMARY ==================================
tests/test_device_workflow.py ..................................... [ 9/9  PASSED]
tests/test_p51_production_api.py .................................. [ 9/9  PASSED]
tests/test_predict.py, test_predict_detection.py, test_pipeline.py . [15/15 PASSED]
tests/test_meta.py, test_model_routes.py .......................... [ 8/8  PASSED]
tests/test_yolo_detector.py, test_ensemble_detector.py ............ [13/13 PASSED]
tests/test_wbf.py ................................................. [ 6/6  PASSED]
----------------------------------------------------------------------------------
Combined Device Intelligence Test Suite:                           69/69 PASSED (100%)
==================================================================================
```

---

## 5. Checkpoint & Dataset Immutability Audit

Cryptographic SHA-256 verification confirmed that all frozen assets remain byte-for-byte unmodified:

| Target Asset Path | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|:---:|
| `dataset_acquisition/training/p4_4_2_bulk_balance_v1/runs/p442_yolo11n/weights/best.pt` | `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92` | `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92` | **MATCH** |
| `dataset_acquisition/training/p4_11_multisource_targeted_aug_v1/runs/p411_yolo11n_targeted_aug/weights/best.pt` | `ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c` | `ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c` | **MATCH** |
| `dataset_acquisition/training/p4_12_model_scale_v1/runs/p412_yolo11s/weights/best.pt` | `96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc` | `96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc` | **MATCH** |
| `dataset_acquisition/training/p4_14_targeted_ood_robustness_v1/runs/p414_yolo11n_targeted_aug/weights/best.pt` | `8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81` | `8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81` | **MATCH** |
| `dataset_acquisition/evaluation/p4_5_real_world_v1/p45_data.yaml` | `b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b` | `b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b` | **MATCH** |
| `dataset_acquisition/evaluation/p4_7_wikimedia_ood_v1/p47_final_data.yaml` | `5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284` | `5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284` | **MATCH** |
