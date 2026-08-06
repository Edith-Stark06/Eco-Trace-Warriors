# EcoTrace India — Device Intelligence Engine (DIE)

> AI microservice for e-waste **device intelligence**: turn device photos
> into structured data (device type, brand, condition, recoverable
> materials, carbon score) behind a clean REST API.

**Module:** `intelligence/device_ai`
**Status:** Milestone **M3.3** — **Device Lifecycle Ledger Engine**: an
internal-only, **deterministic device-history builder** that models the complete
lifecycle of a device as an ordered sequence of immutable **`LifecycleEvent`**
objects (registered → in use → collected → … → disposed), validates that ordering
against an **external, versioned state machine** (a `LifecycleRuleSet` loaded from
YAML/JSON behind a strict validating loader), and composes the result into an
immutable **`LifecycleRecord`**. It sits *above* the ledger core — where the
ledger chains passport *verdicts*, this engine chains a device's *history* — and
ties into the ledger **through the M3.2 backend abstraction**, depending only on
an injected **`LedgerService`** to confirm, list and load anchored passport chains
without touching a concrete store. An illegal event ordering is *reported* as
`is_valid == False`; only a malformed **rules file** *raises* (a typed
`LifecycleRuleError`). It carries **no inference and no evidence of its own** and
implements **no** Hyperledger Fabric, chaincode, smart contracts, REST endpoints,
networking, GPS tracking, event streaming, QR scanning, wallets or digital
signatures. Built on **M3.2** — the **Ledger Backend Abstraction Layer**: a
technology-agnostic **`LedgerBackend`** protocol and three deterministic,
in-memory implementations (**`MemoryLedgerBackend`**, **`MockFabricLedgerBackend`**,
**`MockEthereumLedgerBackend`**) that let the **`LedgerService`** persist chains
through an *injected* backend, depending only on the protocol — so the ledger
technology can change without touching the domain or service. Every write returns
a **`LedgerReceipt`** carrying the chain id and backend-specific metadata. Built
on **M3.1** — the **Blockchain Ledger Core**, an internal-only, **deterministic
immutable-ledger builder** that consumes the three upstream artefacts the passport
pipeline already produced (the immutable `DevicePassport` from M2.3, its
`PassportIntegrityReport` from M2.4 and its `PassportTrustReport` from M2.5) and
emits a tamper-evident **`Blockchain`** — an ordered chain of **`Block`** objects,
each carrying one **`LedgerRecord`** payload and one **`BlockHeader`** that links
it to the previous block via a deterministic SHA-256 hash. It answers one
question: *how do we record this passport in an append-only, independently
verifiable audit trail?* Unlike M2.3 (which *assembles* the passport), M2.4 (which
*checks* it) and M2.5 (which *scores* it), the ledger core carries **no inference
and no evidence collection of its own** — it snapshots the three reports' key
outcomes into a record, hashes it, and chains it by embedding the SHA-256 digest
of the previous block's header (or a genesis sentinel for the first block). It
ships **no new endpoint**, and **no** Hyperledger Fabric, Ethereum, consensus,
proof-of-work, smart contracts, chaincode, wallets, certificates, digital
signatures, networking or persistence (the M3.2 mocks emit technology-*shaped*
metadata only), and leaves the `/predict` API contract **unchanged and
backward-compatible**. (Built on M2.5 — a trust & provenance engine; M2.4 — a
passport validation & integrity engine; M2.3 — a device passport core; M2.2 — a
circular decision engine; M2.1 — a decision-knowledge engine; M1.11 — an
environmental impact engine; M1.10 — a material inference engine; M1.9 — a
component inference engine; M1.8 — a recoverability rule engine; M1.7 — a
multi-modal fusion engine; M1.6 — an OCR intelligence engine; M1.5 — an OpenCLIP
fingerprint engine; and M1.4 — a real Ultralytics YOLO detector.)
**Version:** `1.0.0`

---

## Table of Contents

1. [Overview](#overview)
2. [Why a separate service](#why-a-separate-service)
3. [Architecture](#architecture)
4. [Folder structure](#folder-structure)
5. [Service pipeline](#service-pipeline)
6. [API reference](#api-reference)
7. [Dataset intelligence pipeline (M1.2)](#dataset-intelligence-pipeline-m12)
8. [AI training & MLOps platform (M1.3)](#ai-training--mlops-platform-m13)
9. [Device Detection Engine (M1.4)](#device-detection-engine-m14)
10. [Device Fingerprinting Engine (M1.5)](#device-fingerprinting-engine-m15)
11. [OCR Intelligence Engine (M1.6)](#ocr-intelligence-engine-m16)
12. [Multi-Modal Fusion Engine (M1.7)](#multi-modal-fusion-engine-m17)
13. [Recoverability Intelligence Engine (M1.8)](#recoverability-intelligence-engine-m18)
14. [Component Intelligence Engine (M1.9)](#component-intelligence-engine-m19)
15. [Material Intelligence Engine (M1.10)](#material-intelligence-engine-m110)
16. [Environmental Intelligence Engine (M1.11)](#environmental-intelligence-engine-m111)
17. [Decision Knowledge Engine (M2.1)](#decision-knowledge-engine-m21)
18. [Circular Decision Engine (M2.2)](#circular-decision-engine-m22)
19. [Device Passport Core (M2.3)](#device-passport-core-m23)
20. [Device Passport Validation & Integrity Engine (M2.4)](#device-passport-validation--integrity-engine-m24)
21. [Trust & Provenance Engine (M2.5)](#trust--provenance-engine-m25)
22. [Blockchain Ledger Core (M3.1)](#blockchain-ledger-core-m31)
23. [Ledger Backend Abstraction Layer (M3.2)](#ledger-backend-abstraction-layer-m32)
24. [Device Lifecycle Ledger Engine (M3.3)](#device-lifecycle-ledger-engine-m33)
25. [Configuration](#configuration)
26. [Running locally](#running-locally)
27. [Running with Docker](#running-with-docker)
28. [Testing](#testing)
29. [Code quality](#code-quality)
30. [Future integration points](#future-integration-points)
31. [Roadmap](#roadmap)

---

## Overview

The Device Intelligence Engine is an **independent** Python/FastAPI service.
The existing EcoTrace backend (Express/PostgreSQL/Prisma) calls it over HTTP
and remains completely unchanged. The service holds **no business logic** —
it answers _"what is this device"_, never _"what should the system do"_.
Decisions stay in the backend (`docs/engineering/08_AI.md`).

For milestone M1.1 the service ships **pluggable interfaces** and
**mock** model implementations. The mocks are **deterministic**: the same
images always produce the same prediction (derived from a content hash), so
demos are predictable and tests are reproducible — with zero trained
weights.

## Why a separate service

- **Isolation** — AI dependencies (PyTorch, YOLO, CLIP, OCR) never touch the
  Node backend runtime.
- **Independent scaling & deployment** — the AI service scales on its own.
- **Pluggability** — real models replace mocks behind the same interfaces
  with no API or pipeline changes.

## Architecture

```
                     ┌───────────────────────────────┐
   Express Backend   │      Device Intelligence       │
  ────HTTP /predict──▶            Engine (DIE)         │
                     │                                 │
                     │  api/ ──► preprocessing/ ──►    │
                     │             inference/ (pipeline)│
                     │                 │               │
                     │        pluggable model adapters │
                     │   detector · clip · condition · │
                     │         ocr · material          │
                     └───────────────────────────────┘
```

Layering (dependencies point downward, never upward):

```
api/           (transport: routes, schemas, middleware, errors)
   ↓
inference/     (pipeline orchestration + model interfaces)
   ↓
preprocessing/ (validation, loading, transforms)
   ↓
utils/ · configs/ · exceptions   (cross-cutting foundations)
```

## Folder structure

```
device_ai/
├── api/                 # HTTP layer
│   ├── routes.py            #   endpoints: / /health /version /predict
│   ├── dataset_routes.py    #   /dataset/* endpoints (M1.2)
│   ├── fingerprint_routes.py#   /fingerprint/* endpoints (M1.5)
│   ├── ocr_routes.py        #   /ocr/* endpoints (M1.6)
│   ├── schemas.py           #   Pydantic request/response models
│   ├── fingerprint_schemas.py#  fingerprint request/response models (M1.5)
│   ├── ocr_schemas.py       #   OCR request/response models (M1.6)
│   ├── dependencies.py      #   DI providers (settings, pipeline, validator, fingerprint, ocr)
│   ├── middleware.py        #   request-id + latency structured logging
│   └── errors.py            #   exception → error-envelope handlers
├── configs/
│   ├── settings.py      # env-driven Settings (pydantic-settings)
│   └── logging.py       # Loguru structured logging
├── preprocessing/
│   ├── image_loader.py  # bytes → decoded LoadedImage
│   ├── validator.py     # count/size/mime/corruption/resolution checks
│   └── transforms.py    # deterministic model-input transforms
├── inference/
│   ├── predictor.py     # model interfaces + deterministic mocks
│   ├── yolo_detector.py # M1.4 real YOLO detector (Detector interface)
│   ├── clip_encoder.py  # M1.5 OpenCLIP encoder (EmbeddingEncoder interface)
│   ├── pipeline.py      # orchestration + carbon score (mock + detection factories)
│   ├── ecoid.py         # EcoID generation (ET-YYYY-XXXXXXXX)
│   └── registry.py      # config-driven artifact resolution
├── fingerprint/         # M1.5 device fingerprinting engine
│   ├── models.py        #   DeviceFingerprint domain model + hash-backed fingerprint
│   ├── similarity.py    #   cosine/euclidean/manhattan metrics + dispatcher
│   ├── verification.py  #   VerificationEngine: similarity + match/no-match decision
│   ├── repository.py    #   storage-agnostic Protocol + InMemory/JsonFile stores
│   └── service.py       #   orchestration facade (encode→normalize→hash→persist)
├── ocr/                 # M1.6 OCR intelligence engine
│   ├── models.py        #   TextSpan/BarcodeResult/ExtractedField/OCRExtraction/OCRIdentity
│   ├── patterns.py      #   pure regex + validators (IMEI/Luhn, MAC, serial, manufacturer)
│   ├── parser.py        #   OCRParser: spans+barcodes → confidence-scored fields (pure)
│   ├── backends.py      #   OCRBackend ABC + guarded EasyOCRBackend + MockOCRBackend
│   ├── barcode.py       #   BarcodeReader ABC + guarded OpenCVBarcodeReader + MockBarcodeReader
│   └── service.py       #   OCRService: backend + barcode reader + parser orchestration
├── fusion/              # M1.7 multi-modal fusion engine (internal-only, no endpoints)
│   ├── models.py        #   FusionAttribute/Evidence/Claim/ResolvedAttribute/Conflict/DeviceContext
│   └── engine.py        #   FusionEngine: merge detection+fingerprint+ocr → immutable context
├── recoverability/      # M1.8 recoverability intelligence engine (internal-only, no endpoints)
│   ├── models.py        #   HazardLevel/RecommendedAction/RuleOutcome/RecoverabilityReport
│   ├── profiles.py      #   DeviceProfile knowledge table + profile_for() + aliases
│   ├── config.py        #   RecoverabilityConfig: all thresholds + rule weights (single source of truth)
│   ├── rules.py         #   Rule ABC + 7 modular rules + RuleEngine (ordered, injectable)
│   ├── scoring.py       #   ScoringEngine: summed/clamped deltas, hazard max, confidence product
│   └── service.py       #   RecoverabilityService.assess(context) → immutable report
├── components/          # M1.9 component intelligence engine (internal-only, no endpoints)
│   ├── models.py        #   ComponentCategory/InferredComponent/ComponentReport
│   ├── profiles.py      #   external-catalogue loader → ComponentSpec/Profile/Library + profile_for()
│   ├── config.py        #   ComponentConfig: catalogue locator + corroboration/aggregation weights
│   ├── inference.py     #   ComponentInferenceEngine: prior + bounded corroboration, clamp, floor, blend
│   ├── service.py       #   ComponentService.analyze(context, recoverability) → immutable report
│   └── data/            #   components.yaml — external, versioned component catalogue (19 classes)
├── materials/          # M1.10 material intelligence engine (internal-only, no endpoints)
│   ├── models.py        #   MaterialCategory/RecoveredMaterial/MaterialReport
│   ├── profiles.py      #   external-catalogue loader → MaterialSpec/Profile/Library + profile_for()
│   ├── config.py        #   MaterialConfig: catalogue locator + confidence weights (single source of truth)
│   ├── inference.py     #   MaterialInferenceEngine: nominal mass + source-gated confidence, clamp, floor, blend
│   ├── service.py       #   MaterialService.analyze(context, recoverability, components) → immutable report
│   └── data/            #   materials.yaml — external, versioned material catalogue (19 classes)
├── dataset/             # M1.2 dataset intelligence pipeline
│   ├── layout.py        #   DATASET_DIR sub-folder resolution + discovery
│   ├── records.py       #   immutable value objects (records/reports)
│   ├── hashing.py       #   SHA-256 + aHash/dHash/pHash + hamming distance
│   ├── metadata.py      #   quality metrics (blur/brightness/…) + metadata
│   ├── duplicates.py    #   exact + near-duplicate detection
│   ├── validator.py     #   YOLO annotation parsing/validation
│   ├── importer.py      #   copy-in + de-duplicate source images
│   ├── augmenter.py     #   deterministic offline augmentation
│   ├── splitter.py      #   deterministic train/val/test splitting
│   ├── exporter.py      #   YOLO / COCO / Pascal VOC export
│   ├── statistics.py    #   aggregate dataset statistics
│   ├── versioning.py    #   content-addressed dataset snapshots
│   ├── reporting.py     #   JSON + self-contained HTML reports
│   └── service.py       #   orchestration facade (the API's collaborator)
├── models/              # detector/ clip/ condition/ ocr/ (artifacts, gitignored)
├── training/            # M1.3 AI training & MLOps platform (see training/README.md)
│   ├── config.py        #   typed RunConfig + Hydra-compatible YAML loader
│   ├── configs/         #   default.yaml + training.yaml + optimizer.yaml + detector.yaml
│   ├── core/            #   BaseTrainer, callbacks, metrics, evaluator, exporter, registry
│   ├── detector/        #   M1.4 YOLOTrainer + DetectionEvaluator (plug-in on the platform)
│   ├── experiments/     #   ExperimentTracker protocol + JSON/MLflow/Null trackers
│   ├── registry/        #   JSON model registry + artifact manager
│   └── utils/           #   seeding, timing, git metadata, environment capture
├── datasets/            # managed dataset tree (contents gitignored)
│   ├── raw/             #   ingested, unmodified source images
│   ├── processed/       #   images after deterministic preprocessing
│   ├── cleaned/         #   images remaining after dedup/quality removal
│   ├── augmented/       #   generated augmentation variants
│   ├── annotations/     #   source annotations in their original format
│   ├── labels/          #   normalised YOLO .txt labels
│   ├── metadata/        #   metadata.json + versions.json
│   ├── quality/         #   report.json + report.html
│   ├── splits/          #   split.json manifests
│   └── exports/         #   yolo/ coco/ voc/ format exports
├── artifacts/           # M1.3 training outputs: checkpoints/ exports/ reports/ (gitignored)
├── mlruns/              # M1.3 experiment-tracking runs (gitignored)
├── evaluation/          # metric reports (future)
├── utils/               # image_utils, file_utils, hashing
├── scripts/             # developer utilities (e.g. example-artifact generation)
├── tests/               # pytest suite
├── notebooks/           # exploration (future)
├── app.py               # ASGI entrypoint (device_ai.app:app)
├── application.py       # FastAPI app factory
├── exceptions.py        # domain error hierarchy
├── train.py                # CLI shim → python -m device_ai.train
├── evaluate.py             # CLI shim → python -m device_ai.evaluate
├── export.py               # CLI shim → python -m device_ai.export
├── requirements.txt         # core runtime deps
├── requirements-dev.txt     # test/lint/type deps
├── requirements-models.txt  # heavy model deps (future)
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Service pipeline

```
POST /predict
   → validate images (count, size, mime, corruption, resolution)
   → preprocess (decode, EXIF-strip, transform)
   → detector      (device type + bbox)         [real: YOLO — M1.4]
   → CLIP encoder  (embedding reference)         [mock]
   → condition     (label + score)               [mock]
   → OCR           (serial / model)              [mock]
   → material      (recoverable composition)     [mock]
   → carbon score  (derived from condition + materials)
   → EcoID         (ET-YYYY-XXXXXXXX, UUID-backed)
   → JSON response
```

## API reference

Base URL (local): `http://localhost:8100`
Interactive docs: `http://localhost:8100/docs`

### `GET /`
Service metadata / liveness.

### `GET /health`
Readiness including per-component status and model-directory availability.

### `GET /version`
Service and model-contract version information.

### `POST /predict`
`multipart/form-data`. Field **`images`**: 1–6 files.

- **Accepted types:** `jpg`, `jpeg`, `png`, `webp`
- **Max size:** 10 MB per image · **Max images:** 6 · **Min images:** 1
- **Validated:** resolution, file size, MIME type, corrupted images

**Example**

```bash
curl -X POST http://localhost:8100/predict \
  -F "images=@device_front.jpg" \
  -F "images=@device_back.jpg"
```

**Response `200`**

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "Laptop",
  "brand": "Dell",
  "confidence": 0.98,
  "condition": { "label": "Good", "score": 0.91 },
  "ocr": { "serial_number": "", "model": "" },
  "materials": {
    "plastic": 0.42, "aluminum": 0.26, "copper": 0.15,
    "pcb": 0.10, "battery": 0.07
  },
  "carbon_score": 82.5,
  "embedding_id": "mock_embedding_1a2b3c4d",
  "model_version": "1.0.0"
}
```

**Error envelope** (all handled failures share this shape)

```json
{
  "success": false,
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds the maximum allowed size of 10.0 MB.",
    "details": { "filename": "big.jpg", "size": 12345678 }
  },
  "request_id": "b1c2d3e4f5a6b7c8"
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `NO_IMAGES_PROVIDED` | 400 | Fewer than the minimum images sent |
| `TOO_MANY_IMAGES` | 400 | More than `MAX_IMAGES` sent |
| `FILE_TOO_LARGE` | 413 | An image exceeds `MAX_FILE_SIZE` |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Disallowed MIME type / extension |
| `CORRUPTED_IMAGE` | 422 | An image could not be decoded |
| `INVALID_IMAGE_DIMENSIONS` | 422 | Resolution outside bounds |

## Dataset intelligence pipeline (M1.2)

The dataset pipeline turns a folder of device photos into a **clean, versioned,
export-ready** training dataset — **without training anything**. It lives in the
self-contained `dataset/` package and is exposed through six `/dataset/*`
endpoints mounted on the same service. The existing prediction endpoints are
untouched.

Everything operates on a **managed dataset tree** rooted at `DATASET_DIR`
(default `datasets/`). Paths are never hardcoded: `dataset/layout.py` resolves
every sub-folder from settings, and the service creates the tree on first use.

### Capabilities

| Concern | Module | What it does |
|---|---|---|
| **Import & de-dup** | `importer.py` | Copy source images into `raw/`, skipping byte-identical duplicates and unreadable files; preserves sub-folder structure; idempotent. |
| **Hashing** | `hashing.py` | `SHA-256` (exact) + `aHash`, `dHash`, `pHash` (perceptual, 64-bit) compared via Hamming distance. |
| **Quality metrics** | `metadata.py` | Blur (variance of Laplacian), brightness (mean luminance), resolution and corruption flags — Pillow + NumPy only, no OpenCV. |
| **Duplicate detection** | `duplicates.py` | Exact (SHA-256) and near-duplicate (perceptual within a configurable threshold) groups; first-in-sorted-order retained. |
| **Annotation validation** | `validator.py` | Parses YOLO labels; flags malformed lines, out-of-range coords/classes, and missing/orphan image↔label pairs. |
| **Augmentation** | `augmenter.py` | Deterministic offline variants (`hflip`, `rotate90`, `brightness`, `grayscale`); default set is label-preserving. |
| **Splitting** | `splitter.py` | Deterministic, seeded train/val/test partitioning with validated ratios. |
| **Export** | `exporter.py` | YOLO (`images/`+`labels/`+`data.yaml`), COCO (`annotations.json`), Pascal VOC (`Annotations/*.xml`). |
| **Statistics** | `statistics.py` | Counts by format/mode, resolution bounds/means, aggregate quality flags, duplicate totals. |
| **Versioning** | `versioning.py` | Content-addressed, monotonic (`v1`, `v2`, …) dataset snapshots with an aggregate content hash. |
| **Reporting** | `reporting.py` | Combined JSON document + self-contained HTML page (inline CSS, no JS). |

### Endpoints

Base URL (local): `http://localhost:8100`

| Method & path | Body | Purpose |
|---|---|---|
| `POST /dataset/import` | `{ "source": "<dir>", "deduplicate": true }` | Ingest & de-duplicate images from a server-side directory into `raw/`. |
| `POST /dataset/validate` | `{ "num_classes": 3 }` (optional) | Validate YOLO annotations against images. |
| `POST /dataset/augment` | `{ "operations": ["hflip"] }` (optional) | Generate augmented variants into `augmented/`. |
| `POST /dataset/export` | `{ "format": "coco", "class_names": [...] }` | Export to `yolo` \| `coco` \| `voc` under `exports/<format>/`. |
| `GET /dataset/stats` | — | Aggregate statistics (folds in duplicate detection). |
| `GET /dataset/report` | — | Build the combined report; writes `quality/report.json` + `quality/report.html`. |

Dataset error envelope codes (same shape as the prediction errors):

| Code | HTTP | Meaning |
|---|---|---|
| `DATASET_NOT_FOUND` | 404 | Referenced source directory does not exist |
| `EMPTY_DATASET` | 422 | Operation needs images but the dataset has none |
| `UNSUPPORTED_EXPORT_FORMAT` | 400 | Unknown export format requested |
| `INVALID_SPLIT` | 400 | Split ratios negative or not summing to 1.0 |

### Example — import, inspect, export

```bash
# 1. Import a folder of photos into the managed raw/ directory
curl -X POST http://localhost:8100/dataset/import \
  -H 'Content-Type: application/json' \
  -d '{"source": "/data/incoming_photos", "deduplicate": true}'

# 2. Aggregate statistics (formats, resolution, quality flags, duplicates)
curl http://localhost:8100/dataset/stats

# 3. Validate YOLO annotations (optionally bounding the class range)
curl -X POST http://localhost:8100/dataset/validate \
  -H 'Content-Type: application/json' -d '{"num_classes": 5}'

# 4. Export to COCO
curl -X POST http://localhost:8100/dataset/export \
  -H 'Content-Type: application/json' \
  -d '{"format": "coco", "class_names": ["battery", "phone", "laptop"]}'

# 5. Build the combined JSON + HTML report
curl http://localhost:8100/dataset/report
```

Example artifacts (metadata + JSON/HTML report) are checked in under
[`docs/examples/`](docs/examples/) for reference.

## AI training & MLOps platform (M1.3)

The training platform is the reusable **ecosystem** that every future model
(YOLO detector, CLIP encoder, OCR, condition classifier, material estimator,
carbon intelligence) plugs into. It lives in the self-contained `training/`
package and ships **no model implementations** — this milestone builds the
platform only: **no real model is trained, no dataset is downloaded, and
neither YOLO, CLIP nor OCR is implemented** (TensorRT export is likewise out of
scope). A `MockTrainer` in the test-suite exercises the whole lifecycle so the
ecosystem is proven with zero trained weights. Full details live in
[`training/README.md`](training/README.md).

### Design — light default, optional adapters

The platform runs entirely in the base environment (FastAPI + Pydantic + NumPy
+ PyYAML). Heavy libraries — **PyTorch, ONNX, Hydra, MLflow** — are optional
(`requirements-models.txt`) and accessed behind import guards. When absent, the
platform degrades *honestly*: config still composes via PyYAML, experiment
tracking falls back to a JSON tracker, and exporters return a `skipped` record
rather than faking an export. Every collaborator and every source of
non-determinism (clock, git commit, RNG seed) is dependency-injected, so runs
are reproducible and unit-testable.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Run configuration** | `config.py` | Typed, validated `RunConfig` (+ `TrainingConfig`/`OptimizerConfig`) loaded from a Hydra-compatible YAML `defaults` list — works today with only PyYAML. |
| **Training lifecycle** | `core/trainer.py` | Abstract `BaseTrainer`: seeding → epoch loop → metric aggregation → callback dispatch → tracking → checkpoint → auto-registration → immutable `TrainingHistory`. Subclasses implement five hooks. |
| **Callbacks** | `core/callbacks.py` | `EarlyStopping`, `ModelCheckpoint`, `LoggingCallback` over a shared `TrainerState`. |
| **Metrics** | `core/metrics.py` | Pure-NumPy accuracy, precision/recall/F1 (macro/micro/weighted), confusion matrix, mAP placeholder, running `MetricTracker`. |
| **Evaluation** | `core/evaluator.py` | Combined JSON document + self-contained HTML report (confusion matrix, metrics summary, benchmark **placeholder**). |
| **Export** | `core/exporter.py` | PyTorch / TorchScript / ONNX adapters; each returns `skipped` when its backend is absent. |
| **Experiment tracking** | `experiments/` | `ExperimentTracker` protocol; JSON tracker (default), optional MLflow adapter, and a null tracker. |
| **Model registry** | `registry/model_registry.py` | JSON-backed catalogue of `ModelRecord` provenance (name, version, dataset version, timestamp, git commit, framework, metrics, export formats, artifact location). |
| **Artifact layout** | `registry/artifact_manager.py` | Resolves & creates the `checkpoints/` `exports/` `reports/` tree under `ARTIFACT_DIR`. |

### Command-line interface

Three thin CLIs drive the platform (run from `intelligence/` with `PYTHONPATH=.`):

```bash
# Compose + validate config, resolve paths, print the run plan (dry run —
# no concrete trainer ships in M1.3, so a dry run is the honest default):
python -m device_ai.train --config device_ai/training/configs/default.yaml

# Attempt a real fit() once a trainer is registered under --trainer:
python -m device_ai.train --trainer yolo --epochs 50 --run

# Render a registered model's recorded metrics into a JSON + HTML report:
python -m device_ai.evaluate --model device-detector --version 1.0.0

# Attempt export (honestly reports "skipped" when torch/onnx are absent):
python -m device_ai.export --model device-detector --version 1.0.0
```

Illustrative, byte-stable outputs of a mock run (registry entry, training
history, evaluation JSON/HTML) are checked in under
[`docs/examples/training/`](docs/examples/training/).

## Device Detection Engine (M1.4)

Milestone M1.4 ships the **first real model**: an Ultralytics YOLO detector that
replaces `MockDetector` behind the existing `Detector` interface, built on the
M1.3 training platform. The `/predict` **API contract is unchanged** — only
`device_type`, `confidence` and the detection `bounding_box` become real; every
other field stays a deterministic mock until its own sprint (`brand` is a
placeholder `"Unknown"`; OCR, CLIP, condition, material and carbon remain mock).
Full details live in [`docs/engineering/detector.md`](docs/engineering/detector.md).

### Design — real detector, unchanged contract, honest fallback

- **`inference/yolo_detector.py` → `YOLODetector(Detector)`** runs YOLO
  inference, keeps detections above `DETECTOR_CONFIDENCE_THRESHOLD`, and reports
  the highest-confidence detection as `device_type`/`confidence`. Raw class names
  are mapped through an optional `label_map` then title-cased. The Ultralytics
  backend is import-guarded and everything is dependency-injected, so the whole
  parse/map/aggregate path is unit-tested with fakes — no torch/GPU.
- **Guarded production swap.** `get_pipeline()` wires the real detector **only if**
  Ultralytics is importable *and* a detector artifact resolves *and* loads;
  otherwise it degrades to the all-mock pipeline. Both paths return the identical
  schema, so CI and the base environment stay green.
- **`training/detector/` → `YOLOTrainer(BaseTrainer)`** overrides `fit()` to
  delegate the epoch loop to Ultralytics (native resume, early stopping,
  checkpointing, MLflow) while **reusing** the platform's `ArtifactManager`,
  `ModelRegistry`, `ExperimentTracker`, `ExportRecord` and evaluation report —
  no duplicated framework functionality. `DetectionEvaluator` adapts a
  `model.val()` result (mAP / precision / recall / derived F1 / confusion matrix)
  onto the shared JSON + HTML report surface.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Real detection** | `inference/yolo_detector.py` | `YOLODetector(Detector)`: YOLO inference → highest-confidence device type/confidence/bbox; import-guarded backend; injectable model. |
| **Pipeline wiring** | `inference/pipeline.py` | `build_detection_pipeline(detector=…)`: real detector + mock everything else, identical response schema. |
| **Guarded swap** | `api/dependencies.py` | `get_pipeline()` selects real-vs-mock by artifact + backend availability; logs the chosen path. |
| **Training** | `training/detector/yolo_trainer.py` | `YOLOTrainer`: delegates to Ultralytics (resume/early-stop/checkpoint/MLflow), reuses platform provenance + ONNX export. |
| **Evaluation** | `training/detector/evaluation.py` | `DetectionEvaluator`: `model.val()` → mAP/P/R/F1 + confusion → shared JSON/HTML report. |
| **Run config** | `training/configs/detector.yaml` | Hydra-composed detector run (`trainer: yolo`, image size, early-stopping patience). |

### Command-line interface

Real training needs `requirements-models.txt` (ultralytics/torch/onnx). Run from
`intelligence/` with `PYTHONPATH=.`:

```bash
# Train the real detector (resume/early-stopping/checkpointing are native):
python -m device_ai.train --trainer yolo \
  --config device_ai/training/configs/detector.yaml \
  --data-config device_ai/datasets/exports/yolo/data.yaml \
  --epochs 100 --batch-size 16 --run

# Render the recorded detection metrics into a JSON + HTML report:
python -m device_ai.evaluate --model-name device-detector --model-version 1.0.0
```

To **serve** a trained detector, point `DETECTOR_WEIGHTS` at the produced
artifact under `MODEL_DIR`; the guarded selector loads it on next start.
An illustrative, byte-stable detector evaluation report is checked in under
[`docs/examples/detector/`](docs/examples/detector/) (regenerate with
`python -m device_ai.scripts.gen_detector_examples`). The dataset-preparation and
training walkthroughs live in [`docs/engineering/detector.md`](docs/engineering/detector.md).

## Device Fingerprinting Engine (M1.5)

Milestone M1.5 ships the **second real model interface**: a pluggable **OpenCLIP**
encoder that turns device photos into L2-normalized semantic embeddings, derives
**hash-backed EcoTrace Fingerprints**, compares them with **configurable similarity
metrics**, and returns a match/no-match decision from a **Verification Engine** —
all behind three new `/fingerprint/*` endpoints. Like the detector, the encoder
degrades **honestly**: when `open-clip-torch`/`torch` are absent it falls back to
the deterministic mock encoder rather than faking a result. The `/predict`
**API contract is unchanged**. Full details live in
[`docs/engineering/fingerprint.md`](docs/engineering/fingerprint.md).

### Design — pluggable encoder, hash-backed identity, storage-agnostic persistence

- **`inference/clip_encoder.py` → `CLIPEncoder(EmbeddingEncoder)`** runs OpenCLIP
  `encode_image`, moves to CPU and L2-normalizes. The `open-clip-torch`/`torch`
  backend is import-guarded, the weights resolve through the **M1.3 Model Registry**
  (never a hardcoded path), construction never raises, and everything is
  dependency-injected — so the whole aggregate/normalize path is unit-tested with a
  fake `encode_fn` (no torch/GPU). When the backend or artifact is unavailable the
  encoder reports **not-ready** and DI wires the mock instead.
- **Hash-backed fingerprint.** `fingerprint/models.py` canonically encodes the
  rounded normalized vector and hashes it (SHA-256) into a stable 64-char
  **`fingerprint`** identifier; the public **`eco_id`** comes from the reused
  `EcoIDGenerator` (`ET-YYYY-XXXXXXXX`). Same images → same fingerprint.
- **Configurable metrics + verification.** `fingerprint/similarity.py` implements
  cosine, euclidean and manhattan as pure functions returning a normalized
  **similarity in `[0, 1]`** plus the raw distance (pure Python, `math.fsum`, no
  NumPy). `fingerprint/verification.py`'s `VerificationEngine` turns a comparison
  into a `similarity` + `MATCH`/`NO_MATCH` decision against a settings-driven
  threshold; dimension/encoder mismatches raise a typed error.
- **Storage-agnostic persistence.** `fingerprint/repository.py` defines a
  `FingerprintRepository` **Protocol** (`save`/`get`/`exists`/`list_ids`) with two
  implementations — `InMemoryFingerprintRepository` (default) and
  `JsonFileFingerprintRepository` (one JSON per EcoID). The `FingerprintService`
  depends only on the Protocol, so storage is swappable via `FINGERPRINT_BACKEND`.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Real encoding** | `inference/clip_encoder.py` | `CLIPEncoder(EmbeddingEncoder)`: OpenCLIP `encode_image` → CPU → L2-normalized vector; import-guarded backend; registry-resolved weights; honest not-ready fallback. |
| **Domain model** | `fingerprint/models.py` | `DeviceFingerprint`: EcoID, hash-backed `fingerprint`, embedding, encoder provenance, source hashes; canonical-encode → SHA-256 identity. |
| **Similarity** | `fingerprint/similarity.py` | `SimilarityMetric` enum + cosine/euclidean/manhattan → normalized similarity `[0,1]` + raw distance; pure Python (`math.fsum`), no NumPy. |
| **Verification** | `fingerprint/verification.py` | `VerificationEngine`: two fingerprints → similarity + `MATCH`/`NO_MATCH`; settings-driven threshold/metric; typed mismatch error. |
| **Persistence** | `fingerprint/repository.py` | `FingerprintRepository` Protocol + `InMemory`/`JsonFile` stores (path-traversal-safe). |
| **Orchestration** | `fingerprint/service.py` | `FingerprintService`: encode → normalize → hash → persist; `generate`/`compare`/`get`; all collaborators injected. |

### API reference — `/fingerprint/*`

Base URL (local): `http://localhost:8100`

#### `POST /fingerprint/generate`
`multipart/form-data`. Field **`images`**: 1–`MAX_IMAGES` files; optional
`device_type` / `brand` form fields (provenance only). Generates and **persists**
a fingerprint. Same validation as `/predict` (count, size, MIME, corruption,
resolution).

```bash
curl -X POST http://localhost:8100/fingerprint/generate \
  -F "images=@device_front.jpg" \
  -F "device_type=Laptop" -F "brand=Dell"
```

**Response `200`** (embedding truncated for brevity)

```json
{
  "eco_id": "ET-2026-00000001",
  "fingerprint": "0f4d…c2a9",
  "embedding": [0.0123, -0.0456, "…512 floats…"],
  "dimension": 512,
  "encoder_name": "clip",
  "encoder_version": "mock-clip-1.0.0",
  "metric": "cosine",
  "created_at": "2026-08-01T12:00:00+00:00",
  "source_hashes": ["9a3c…"],
  "device_type": "Laptop",
  "brand": "Dell"
}
```

#### `POST /fingerprint/compare`
`application/json`. Verifies two **stored** fingerprints by EcoID, with an
optional per-request `metric` override.

```bash
curl -X POST http://localhost:8100/fingerprint/compare \
  -H 'Content-Type: application/json' \
  -d '{"left_eco_id": "ET-2026-00000001", "right_eco_id": "ET-2026-00000002"}'
```

**Response `200`**

```json
{
  "left_eco_id": "ET-2026-00000001",
  "right_eco_id": "ET-2026-00000002",
  "metric": "cosine",
  "similarity": 0.507836,
  "distance": 0.984329,
  "threshold": 0.85,
  "decision": "no_match",
  "is_match": false
}
```

#### `GET /fingerprint/{eco_id}`
Returns the stored fingerprint (same shape as `generate`), or `404`
`FINGERPRINT_NOT_FOUND` if the EcoID is unknown.

Fingerprint error envelope codes (same shape as the prediction errors):

| Code | HTTP | Meaning |
|---|---|---|
| `FINGERPRINT_NOT_FOUND` | 404 | No fingerprint stored for the given EcoID |
| `FINGERPRINT_MISMATCH` | 422 | Fingerprints differ in dimension/encoder and cannot be compared |
| `ENCODER_NOT_READY` | 503 | The requested encoder backend is unavailable |

Illustrative, byte-stable fingerprint artifacts (example generate/compare
responses and a **similarity evaluation report**) are checked in under
[`docs/examples/fingerprint/`](docs/examples/fingerprint/) (regenerate with
`python -m device_ai.scripts.gen_fingerprint_examples`).

## OCR Intelligence Engine (M1.6)

Milestone M1.6 ships an **OCR Intelligence Engine**: a pluggable **EasyOCR** text
backend and an **OpenCV** QR/barcode reader feed a pure **normalization/parser
layer** that turns noisy OCR spans into structured, confidence-scored **identity
fields** — manufacturer, model, serial number, IMEI, MAC address, QR and
barcode. It is exposed through three new `/ocr/*` endpoints and adds an
**optional, backward-compatible** identity seam into the M1.5 fingerprint
engine. Like the detector and encoder, both backends degrade **honestly**: when
`easyocr` / `opencv-python-headless` are absent they fall back to deterministic
mocks rather than faking a read. The existing `predictor.OCREngine` behind the
frozen `/predict` contract is **untouched**. Full details live in
[`docs/engineering/ocr.md`](docs/engineering/ocr.md).

### Design — pluggable backends, pure parser, honest fallback

- **`ocr/backends.py` → `EasyOCRBackend(OCRBackend)`** runs a pretrained EasyOCR
  reader; the `easyocr` backend is import-guarded, its weights resolve relative
  to `MODEL_DIR` (never a hardcoded path), construction never raises, and the
  row→span mapping is dependency-injected so it is unit-tested with a fake — no
  torch/GPU. When the backend or artifact is unavailable it reports **not-ready**
  and DI wires `MockOCRBackend` instead. EasyOCR is pretrained → a serving-only
  plug-in with no trainer, exactly like the CLIP encoder.
- **`ocr/barcode.py` → `OpenCVBarcodeReader(BarcodeReader)`** decodes QR via
  `cv2.QRCodeDetector` and 1-D barcodes via `cv2.barcode.BarcodeDetector`, behind
  an import guard; the decode step is injectable. Absent cv2 → not-ready →
  `MockBarcodeReader`.
- **`ocr/patterns.py` + `ocr/parser.py`** — the normalization layer is **pure and
  deterministic** (no image, no backend, no clock): label-aware extraction,
  OCR-confusion normalization applied **only** to structured IDs, IMEI validated
  by **Luhn**, per-field confidence = `clamp(recognition_conf × pattern_strength ×
  label_boost)`, and the highest-confidence candidate wins per field type.
  Barcode/QR payloads become fields **and** are mined for an embedded IMEI/serial.
  Fully unit-testable from hand-built spans — which is exactly what `POST
  /ocr/parse` exposes.
- **`ocr/service.py` → `OCRService`** orchestrates backend + barcode reader +
  parser, stamping engine identity, `created_at` (injected clock) and sorted
  source-image hashes. `identity_for()` yields the small `OCRIdentity` projection
  the fingerprint engine can optionally consume.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Text recognition** | `ocr/backends.py` | `OCRBackend` ABC + guarded `EasyOCRBackend` (injectable `recognize_fn`) + deterministic `MockOCRBackend`. |
| **QR/barcode decoding** | `ocr/barcode.py` | `BarcodeReader` ABC + guarded `OpenCVBarcodeReader` (injectable `decode_fn`) + deterministic `MockBarcodeReader`. |
| **Patterns & normalization** | `ocr/patterns.py` | Pure IMEI(+Luhn)/MAC/serial/model/manufacturer matchers with pattern-strength weights + OCR-confusion normalization (IDs only). |
| **Parser** | `ocr/parser.py` | `OCRParser.parse(spans, barcodes)` → confidence-scored `OCRExtraction`; label-aware; barcode mining; deterministic best-selection. |
| **Domain model** | `ocr/models.py` | Frozen `TextSpan`/`BarcodeResult`/`ExtractedField`/`OCRExtraction`/`OCRIdentity` (+ `to_dict`/`from_dict`/`identity`). |
| **Orchestration** | `ocr/service.py` | `OCRService`: `extract`/`parse`/`identity_for`; all collaborators injected. |

### API reference — `/ocr/*`

Base URL (local): `http://localhost:8100`

#### `POST /ocr/extract`
`multipart/form-data`. Field **`images`**: 1–`MAX_IMAGES` files. Runs the text
backend + barcode reader + parser and returns the full structured extraction.
Same validation as `/predict` (count, size, MIME, corruption, resolution).

```bash
curl -X POST http://localhost:8100/ocr/extract -F "images=@device_label.jpg"
```

**Response `200`** (fields truncated for brevity)

```json
{
  "fields": [
    { "field_type": "manufacturer", "value": "Dell", "confidence": 0.9215,
      "raw_text": "Dell", "source": "text" },
    { "field_type": "imei", "value": "019510777635357", "confidence": 0.90552,
      "raw_text": "IMEI: 019510777635357", "source": "text" }
  ],
  "spans": [ { "text": "Dell", "confidence": 0.97, "bounding_box": null } ],
  "barcodes": [
    { "kind": "qr", "payload": "SN0FE1B9C5", "symbology": "QRCODE", "confidence": 0.99 }
  ],
  "identity": {
    "manufacturer": "Dell", "model": "XPS-0FE1",
    "serial_number": "SN0FE1B9C5", "imei": "019510777635357",
    "mac_address": "0F:E1:B9:C5:F1:CD"
  },
  "engine_name": "ocr",
  "engine_version": "mock-ocr-m16-1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00",
  "source_hashes": ["0fe1b9c5f1cd…"]
}
```

#### `POST /ocr/parse`
`application/json`. Runs the **parser only** over client-supplied spans/barcodes,
so the normalization layer is demonstrable without an image.

```bash
curl -X POST http://localhost:8100/ocr/parse \
  -H 'Content-Type: application/json' \
  -d '{"spans": [{"text": "S/N: ABC12345", "confidence": 0.93}],
       "barcodes": [{"kind": "qr", "payload": "490154203237518"}]}'
```

Returns an `OCRResponse` (no source hashes) — here the serial `ABC12345` and a
**Luhn-valid IMEI** mined from the QR payload.

#### `GET /ocr/fields`
Enumerates every supported `FieldType` (discovery).

```json
{ "field_types": ["manufacturer", "model", "serial_number", "imei",
                  "mac_address", "qr_code", "barcode"] }
```

OCR error envelope codes (same shape as the prediction errors):

| Code | HTTP | Meaning |
|---|---|---|
| `OCR_ERROR` | 500 | Base OCR engine failure |
| `OCR_BACKEND_NOT_READY` | 503 | The OCR recognition backend has no reader loaded |
| `OCR_PARSE_ERROR` | 422 | Malformed spans/barcodes submitted to the parser |

The fingerprint engine can **optionally** consume OCR identity:
`FingerprintService.generate(..., identity=ocr_service.identity_for(images))`
attaches the non-empty fields; omitting it leaves M1.5 behaviour byte-identical
(the `identity` key is dropped when empty).

Illustrative, byte-stable OCR artifacts (a full extract response, parse examples
and a **field-level evaluation report**) are checked in under
[`docs/examples/ocr/`](docs/examples/ocr/) (regenerate with
`python -m device_ai.scripts.gen_ocr_examples`).

## Multi-Modal Fusion Engine (M1.7)

Milestone M1.7 ships an **internal-only Multi-Modal Fusion Engine**: it merges the
outputs of the detector (M1.4), the fingerprint engine (M1.5) and the OCR engine
(M1.6) into a single, normalized, **immutable** `DeviceContext`. Each engine
answers a narrow question in isolation and the answers overlap (all three can
assert a brand) and can disagree (a detected `Laptop` vs. an OCR-read phone
identity); fusion reconciles them onto a shared **attribute space**, aggregates
confidence across heterogeneous evidence, resolves one winning value per attribute,
records any disagreement as a first-class **`Conflict`**, and preserves the full
per-module provenance for downstream AI. It mounts **no router**, adds **no
endpoint**, and leaves the `/predict` contract **unchanged**. Full details live in
[`docs/engineering/fusion.md`](docs/engineering/fusion.md).

### Design — uniform evidence, deterministic resolution, immutable context

- **`fusion/models.py`** defines the domain: `FusionAttribute` (the shared
  `device_type`/`brand`/`model`/`serial_number`/`imei`/`mac_address` space),
  `Claim` (a single `(attribute, value, confidence, source)` assertion with a
  case/whitespace-normalized `key`), `Evidence` (a module's set of claims),
  `ResolvedAttribute`, `Conflict` and the frozen **`DeviceContext`**. Pure builders
  (`from_detection`, `from_fingerprint`, `from_ocr`, `from_ocr_identity`) project
  each engine's frozen result onto that space, dropping placeholder values so
  spurious claims never manufacture a conflict. The perception result types are
  imported **only under `TYPE_CHECKING`** (lazy at call time) — the fusion package
  has zero runtime coupling to `inference/`/`fingerprint/`/`ocr/` and duplicates
  nothing.
- **`fusion/engine.py` → `FusionEngine`** is stateless with an injected clock and
  two entry points: `fuse(evidence, …)` (pure core over pre-built `Evidence`) and
  `fuse_modules(detection=…, fingerprint=…, ocr=…)` (builds evidence from raw
  results). Any subset of modules may be supplied; missing evidence yields a
  well-defined **empty context** rather than an error.
- **Confidence aggregation.** Agreement uses **noisy-OR** (`1 − Π(1 − cᵢ)`, so two
  `0.8` claims combine to `0.96` — corroboration raises confidence); disagreement
  applies **support-share damping** (the winner is scaled by its share of the total
  combined confidence, so a dissenting module pulls it below its raw value). The
  context-level `confidence` is the mean of the resolved attributes; everything is
  clamped and rounded to 6 decimals in `[0, 1]`.
- **Conflict detection.** An attribute is conflicted when ≥2 distinct normalized
  values compete; the winner is chosen by a **total ordering**
  (`combined_confidence, claim_count, module_order`) so identical evidence always
  fuses identically, and every competing claim is retained on the emitted
  `Conflict` for auditability.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Attribute space** | `fusion/models.py` | `FusionAttribute` enum + `Claim`/`Evidence` abstraction; per-engine builders that map native results onto the shared space and drop placeholders. |
| **Unified model** | `fusion/models.py` | Frozen `DeviceContext` (+ `ResolvedAttribute`/`Conflict`): resolved attributes, aggregate confidence, full evidence trail, conflicts, provenance; accessors + `to_dict`. |
| **Fusion** | `fusion/engine.py` | `FusionEngine.fuse` / `fuse_modules`: merge detection+fingerprint+OCR; noisy-OR agreement + support-share damping; deterministic winner selection; injected clock. |

### Internal-only — no endpoints

The fusion engine is a **library**, not a service surface. There is nothing to
mount and nothing to call over HTTP; a future orchestrator combines the engines
in-process:

```python
from device_ai.fusion import FusionEngine

engine  = FusionEngine()
context = engine.fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)

context.device_type     # "Laptop"
context.brand           # "Dell"
context.confidence      # aggregate confidence in [0, 1]
context.has_conflicts   # True if any attribute was contested
context.to_dict()       # attributes + evidence + conflicts, fully serializable
```

M1.7 introduces **no new environment variables** — the engine is a pure domain
component. The only new error type is `FUSION_ERROR` (a typed `DeviceAIError`),
surfaced to orchestrating code rather than through the HTTP envelope.

## Recoverability Intelligence Engine (M1.8)

Milestone M1.8 ships the **first downstream consumer** of the fusion engine: an
internal-only, **deterministic rule engine** that turns a fused, immutable
`DeviceContext` into an explainable **`RecoverabilityReport`** — normalized
repairability / reusability / recyclability scores, a hazard level, an
aggregated confidence and a recommended end-of-life action, each backed by
ordered human-readable reasoning and warnings. It is **deterministic and
rule-based** (no learned damage classification, no material/carbon/blockchain/
passport), so it runs in the base environment with zero weights. It mounts **no
router**, adds **no endpoint**, and leaves the `/predict` contract **unchanged**.
Full details live in [`docs/engineering/recoverability.md`](docs/engineering/recoverability.md).

### Design — modular rules, pure scoring, injected service

- **`recoverability/profiles.py`** holds a **knowledge table** of 19 curated
  `DeviceProfile`s (baseline repairability / reusability / recyclability,
  intrinsic `hazard`, `has_battery`) plus ~40 synonym aliases; `profile_for()`
  does case/whitespace-insensitive lookups and falls back to a conservative
  `known=False` profile that forces manual review.
- **`recoverability/rules.py`** — seven small, independent `Rule`s, each emitting
  uniform additive **`RuleOutcome`s**: `BaselineProfileRule` seeds the scores +
  hazard from the profile; `IdentityCompletenessRule` rewards model/serial/IMEI
  presence and warns when identity is absent; `BatteryHazardRule` raises the
  hazard floor to `MEDIUM` and penalizes recycling; `HighHazardDisposalRule`
  forces hazardous disposal for intrinsically-high classes (CRT, batteries);
  `ConflictPenaltyRule` and `LowConfidenceRule` damp confidence and can force
  `MANUAL_REVIEW`; `UnknownDeviceRule` forces review for unrecognized types. The
  `RuleEngine` runs the ordered, **injectable** rule set.
- **`recoverability/scoring.py` → `ScoringEngine`** is a **pure fold**: summed and
  clamped per-dimension deltas, most-severe hazard floor (`max_hazard`), and
  **confidence aggregation** = `context.confidence × Π rule confidence_factors`
  (independent damping signals compound), all rounded to 6 decimals matching
  fusion. The **recommended action** comes from an explicit ordered decision
  table — `HIGH` hazard → `HAZARDOUS_DISPOSAL`; forced manual review →
  `MANUAL_REVIEW`; reusability ≥ 0.65 → `REFURBISH`; repairability ≥ 0.55 →
  `REPAIR`; recyclability ≥ 0.45 → `RECYCLE`; else `MANUAL_REVIEW`.
- **`recoverability/config.py` → `RecoverabilityConfig`** is the single source of
  truth for every threshold and rule weight; the four operationally-tunable
  thresholds map from env via `from_settings()`.
- **`recoverability/service.py` → `RecoverabilityService.assess(context)`** wires
  profile + rules + scoring into an immutable report, stamping `eco_id`,
  `engine_version` and an injected `created_at`. All collaborators injected →
  deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `recoverability/models.py` | Frozen `HazardLevel`/`RecommendedAction`/`RuleOutcome`/`RecoverabilityReport`; `max_hazard` (UNKNOWN never masks a real floor). |
| **Knowledge table** | `recoverability/profiles.py` | 19 curated `DeviceProfile`s + `profile_for()` normalization/aliases + conservative unknown fallback. |
| **Rule engine** | `recoverability/rules.py` | 7 modular `Rule`s (baseline, identity, battery, high-hazard, conflict, low-confidence, unknown) + ordered injectable `RuleEngine`. |
| **Scoring** | `recoverability/scoring.py` | Summed/clamped deltas, hazard max, product-of-factors confidence, explicit ordered decision table. |
| **Config** | `recoverability/config.py` | All thresholds + weights in one frozen dataclass; env mapping via `from_settings()`. |
| **Orchestration** | `recoverability/service.py` | `assess(context)` → immutable report; all collaborators injected. |

### Internal-only — no endpoints

Like fusion, the recoverability engine is a **library**, not a service surface.
A future orchestrator chains it onto fusion in-process:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService

context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)

report = RecoverabilityService().assess(context)       # M1.8
report.recommended_action    # e.g. RecommendedAction.REFURBISH
report.hazard_level          # e.g. HazardLevel.MEDIUM
report.reasoning             # ordered, human-readable explanations
report.warnings              # operator-facing cautions
report.to_dict()             # fully serializable
```

M1.8 adds four **opt-in** environment variables (defaults reproduce the reference
behaviour, so an existing deployment is unchanged) and one new error type,
`RECOVERABILITY_ERROR` (a typed `DeviceAIError`), surfaced to orchestrating code
rather than through the HTTP envelope.

## Component Intelligence Engine (M1.9)

Milestone M1.9 ships the **second downstream consumer** of the fusion engine, and
the first to also consume the recoverability engine: an internal-only,
**deterministic inference engine** that turns a fused, immutable `DeviceContext`
and its `RecoverabilityReport` into an explainable **`ComponentReport`** — the
likely internal electronic components of the device, each with a **presence
confidence**, plus a single **overall confidence** and ordered human-readable
reasoning and warnings. It infers from device type + OCR identity + recoverability
hazard + versioned component profiles, and is **deterministic and explainable**
(no learned models, no material/carbon/blockchain/passport), so it runs in the
base environment with zero weights. Unlike M1.8's in-code profile table, its
knowledge lives in an **external, versioned YAML/JSON catalogue** so the component
library is **data, not logic** — reviewable and extensible without a code change.
It mounts **no router**, adds **no endpoint**, and leaves the `/predict` contract
**unchanged**. Full details live in
[`docs/engineering/component.md`](docs/engineering/component.md).

### Design — external catalogue, priors + bounded corroboration, injected service

- **`components/data/components.yaml`** is the external, versioned catalogue: a
  `version`, 47 synonym `aliases`, a conservative `unknown` fallback and 19 device
  profiles (mirroring the recoverability classes). Each component entry has a
  `name`, `category`, `base_likelihood` (a prior), `hazardous`/`recoverable` flags
  and an optional `implied_by` list of identity signals.
- **`components/profiles.py`** owns the strict loader: it turns the file into
  immutable `ComponentSpec`/`ComponentProfile`/`ComponentProfileLibrary` value
  objects, **validating aggressively** (version present, every category valid,
  every likelihood numeric in `[0, 1]`, every `implied_by`/alias resolvable) and
  failing with a typed `ComponentProfileError`. `profile_for()` does the same
  case/whitespace-insensitive, alias-aware lookup as recoverability, with a
  conservative unknown fallback stamped with the caller label.
- **`components/inference.py` → `ComponentInferenceEngine`** is a **pure fold**:
  each component starts at its catalogue `base_likelihood`, gains a small bounded
  `+identity_corroboration_bonus` when a declared `implied_by` signal is present
  and a `+hazard_corroboration_bonus` when a hazardous part agrees with a concrete
  (non-`NONE`/`UNKNOWN`) device hazard, is clamped/rounded to 6 decimals, and is
  dropped below the min-presence floor. The **overall confidence** blends the
  fused and recoverability confidences, then damps multiplicatively (compounding)
  for an unrecognized type and for fusion conflicts.
- **`components/config.py` → `ComponentConfig`** is the single source of truth for
  the catalogue locator and every corroboration/aggregation weight; the two
  operationally-tunable knobs map from env via `from_settings()`.
- **`components/service.py` → `ComponentService.analyze(context, recoverability)`**
  loads the external catalogue **once** at construction, resolves the device-type
  profile, runs the inference engine and stamps `eco_id`, `engine_version`, the
  catalogue `profile_version` and an injected `created_at`. All collaborators
  (config, library, inference engine, clock) are injected → deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `components/models.py` | Frozen `ComponentCategory`/`InferredComponent`/`ComponentReport`; hazardous/recoverable partitions + `to_dict`. |
| **External catalogue** | `components/data/components.yaml` | Versioned YAML: 19 device profiles + 47 aliases + conservative unknown fallback; component priors, hazard/recovery flags, `implied_by` signals. |
| **Profile library & loader** | `components/profiles.py` | Strict `load_library()` → immutable `ComponentSpec`/`Profile`/`Library`; aggressive validation; normalized/alias-aware `profile_for()`. |
| **Inference** | `components/inference.py` | `ComponentInferenceEngine`: catalogue prior + bounded identity/hazard corroboration, clamp/round, min-presence floor; blended/damped overall confidence; ordered reasoning/warnings. |
| **Config** | `components/config.py` | Catalogue locator + all weights in one frozen dataclass; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `components/service.py` | `analyze(context, recoverability)` → immutable report; catalogue loaded once; all collaborators injected. |

### Internal-only — no endpoints

Like fusion and recoverability, the component engine is a **library**, not a
service surface. A future orchestrator chains it onto the two upstream engines
in-process:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService

context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)
recoverability = RecoverabilityService().assess(context)   # M1.8

report = ComponentService().analyze(context, recoverability)   # M1.9
report.components             # tuple[InferredComponent, …] in catalogue order
report.hazardous_components   # only the hazardous parts (e.g. the battery)
report.overall_confidence     # e.g. 0.9
report.reasoning              # ordered, human-readable explanations
report.warnings               # operator-facing cautions
report.to_dict()              # fully serializable
```

M1.9 adds two **opt-in** environment variables (`COMPONENT_PROFILES_PATH`,
`COMPONENT_MIN_PRESENCE_CONFIDENCE`; defaults reproduce the reference behaviour, so
an existing deployment is unchanged) and one new error type, `COMPONENT_ERROR` (a
typed `DeviceAIError`, with the loader raising the `COMPONENT_PROFILE_ERROR`
subclass on a malformed catalogue), surfaced to orchestrating code rather than
through the HTTP envelope.

## Material Intelligence Engine (M1.10)

Milestone M1.10 ships the **third downstream consumer** of the fusion engine, and
the first to consume the M1.9 component engine: an internal-only, **deterministic
inference engine** that turns a fused, immutable `DeviceContext`, its
`RecoverabilityReport` and its `ComponentReport` into an explainable
**`MaterialReport`** — the recoverable and hazardous materials the device is made
of, each with an **estimated mass** and **confidence** plus the **source
components** it derives from, alongside device-level **total / recoverable /
hazardous** weight totals and a single **overall confidence**, backed by ordered
human-readable reasoning and warnings. It infers from the component inventory +
versioned material profiles + recoverability and device confidence, and is
**deterministic and explainable** (no learned models, no carbon/blockchain/
passport/market value), so it runs in the base environment with zero weights. Like
M1.9, its knowledge lives in an **external, versioned YAML/JSON catalogue** so the
material library is **data, not logic** — reviewable and extensible without a code
change. It mounts **no router**, adds **no endpoint**, and leaves the `/predict`
contract **unchanged**. Full details live in
[`docs/engineering/material.md`](docs/engineering/material.md).

### Design — external catalogue, source-gated mass, injected service

- **`materials/data/materials.yaml`** is the external, versioned catalogue: a
  `version`, synonym `aliases`, a conservative `unknown` fallback and 19 device
  profiles (mirroring the component classes). Each material entry has a `name`,
  `category`, an **absolute nominal `mass_g`**, `hazardous`/`recoverable` flags, an
  optional `source_components` list (the `ComponentCategory` wire values that must
  be present for the material to be included) and free-text `notes`.
- **`materials/profiles.py`** owns the strict loader: it turns the file into
  immutable `MaterialSpec`/`MaterialProfile`/`MaterialProfileLibrary` value objects,
  **validating aggressively** (version present, every category a `MaterialCategory`,
  every `mass_g` a non-negative number, every `source_components` entry a valid
  `ComponentCategory`, every alias resolvable, an `unknown` fallback present) and
  failing with a typed `MaterialProfileError`. `profile_for()` does the same
  case/whitespace-insensitive, alias-aware lookup as the component engine, with a
  conservative unknown fallback stamped with the caller label.
- **`materials/inference.py` → `MaterialInferenceEngine`** is a **pure fold**: a
  material is included only when at least one of its `source_components` is present
  in the consumed `ComponentReport` (a material with empty `source_components` is
  *structural / unconditional* — always present, source presence = `1.0`). The
  **mass** is the catalogue **nominal**, never scaled by confidence; a material's
  **confidence** is derived independently — `source_presence` (the max
  presence-confidence across its present source components) × the **overall
  confidence** — so no single material is ever more certain than the inventory as a
  whole. Materials below the min-confidence floor are dropped. The **overall
  confidence** blends the fused and recoverability confidences, then damps
  multiplicatively (compounding) for an unrecognized type and for fusion conflicts.
- **`materials/config.py` → `MaterialConfig`** is the single source of truth for
  the catalogue locator and every confidence weight; the two operationally-tunable
  knobs (`material_profiles_path`, `material_min_confidence`) map from env via
  `from_settings()`.
- **`materials/service.py` → `MaterialService.analyze(context, recoverability,
  components)`** loads the external catalogue **once** at construction, resolves the
  device-type profile, runs the inference engine and stamps `eco_id`,
  `engine_version`, the catalogue `profile_version` and an injected `created_at`.
  All collaborators (config, library, inference engine, clock) are injected →
  deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `materials/models.py` | Frozen `MaterialCategory`/`RecoveredMaterial`/`MaterialReport`; recoverable/hazardous mass partitions + `to_dict`. |
| **External catalogue** | `materials/data/materials.yaml` | Versioned YAML: 19 device profiles + aliases + conservative unknown fallback; nominal masses, hazard/recovery flags, `source_components` links. |
| **Profile library & loader** | `materials/profiles.py` | Strict `load_library()` → immutable `MaterialSpec`/`Profile`/`Library`; aggressive validation; normalized/alias-aware `profile_for()`. |
| **Inference** | `materials/inference.py` | `MaterialInferenceEngine`: source-component gating, nominal mass, presence-derived confidence, clamp/round, min-confidence floor; blended/damped overall confidence; ordered reasoning/warnings. |
| **Config** | `materials/config.py` | Catalogue locator + all weights in one frozen dataclass; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `materials/service.py` | `analyze(context, recoverability, components)` → immutable report; catalogue loaded once; all collaborators injected. |

### Internal-only — no endpoints

Like fusion, recoverability and the component engine, the material engine is a
**library**, not a service surface. A future orchestrator chains it onto the three
upstream engines in-process:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService

context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)
recoverability = RecoverabilityService().assess(context)              # M1.8
components = ComponentService().analyze(context, recoverability)      # M1.9

report = MaterialService().analyze(context, recoverability, components)   # M1.10
report.materials              # tuple[RecoveredMaterial, …] in catalogue order
report.hazardous_materials    # only the hazardous materials (e.g. leaded glass)
report.recoverable_mass_g     # recoverable weight in grams
report.hazardous_mass_g       # hazardous weight in grams
report.overall_confidence     # e.g. 0.9
report.reasoning              # ordered, human-readable explanations
report.warnings               # operator-facing cautions
report.to_dict()              # fully serializable
```

M1.10 adds two **opt-in** environment variables (`MATERIAL_PROFILES_PATH`,
`MATERIAL_MIN_CONFIDENCE`; defaults reproduce the reference behaviour, so an
existing deployment is unchanged) and one new error type, `MATERIAL_ERROR` (a typed
`DeviceAIError`, with the loader raising the `MATERIAL_PROFILE_ERROR` subclass on a
malformed catalogue), surfaced to orchestrating code rather than through the HTTP
envelope.

## Environmental Intelligence Engine (M1.11)

Milestone M1.11 ships the **fourth downstream consumer** of the fusion engine: an
internal-only, **deterministic inference engine** that turns a fused
`DeviceContext`, its `RecoverabilityReport`, its `ComponentReport` and its
`MaterialReport` into an explainable **`EnvironmentalImpactReport`** — the
**avoided environmental burden** of recovering the device rather than landfilling
it: **carbon saved**, **energy saved**, **water saved**, **landfill diversion**,
**critical-material recovery**, a **circularity index** and a **hazard-reduction
score**, with **confidence on a wholly separate axis** and ordered reasoning +
warnings. Like the material engine, its knowledge — the per-material-category
conversion factors — lives in an **external, versioned YAML/JSON catalogue** so the
factor library is **data, not logic**. The five physical metrics are real amounts
(never clamped); the two indices are normalized `[0, 1]`. It mounts **no router**,
adds **no endpoint**, and leaves the `/predict` contract **unchanged**. Full
details live in [`docs/engineering/environmental.md`](docs/engineering/environmental.md).

- **`environmental/data/factors.yaml`** is the external, versioned catalogue: a
  `version`, a conservative `default` fallback and a per-`MaterialCategory` factor
  (carbon/energy/water per kg + a `critical` flag). **`environmental/factors.py`**
  owns the strict loader (typed `EnvironmentalFactorError`) and the never-failing
  `factor_for()` fallback.
- **`environmental/inference.py` → `EnvironmentalInferenceEngine`** is a pure fold:
  recoverable materials above the confidence floor are grouped by category, each
  category's recovered mass is converted to an avoided burden via the per-kg
  factors, and the landfill/critical quantities, circularity index and
  hazard-reduction score are derived; confidence blends the material and
  recoverability confidences **without re-damping** (the upstream confidences
  already encode device-type/conflict damping).
- **`environmental/config.py` → `EnvironmentalConfig`** holds the catalogue locator
  and the tunable weights; `ENVIRONMENTAL_FACTORS_PATH` and
  `ENVIRONMENTAL_MIN_CONFIDENCE` map from env via `from_settings()`.
- **`environmental/service.py` → `EnvironmentalService.analyze(context,
  recoverability, components, materials)`** loads the catalogue once and stamps
  provenance (engine/factor versions + injected clock). New error types:
  `ENVIRONMENTAL_ERROR` (500) and its loader subclass `ENVIRONMENTAL_FACTOR_ERROR`
  (422).

## Decision Knowledge Engine (M2.1)

Milestone M2.1 ships the **fifth downstream consumer** of the fusion engine and
the first engine of **M2**: an internal-only, **deterministic inference engine**
that consolidates all five upstream reports — `DeviceContext`,
`RecoverabilityReport`, `ComponentReport`, `MaterialReport` and
`EnvironmentalImpactReport` — into a single, normalized **`DecisionKnowledgeReport`**.
It answers *"taken together, how strongly does each decision dimension weigh for
this device, on one comparable scale?"* — **normalized evidence only**: six
`[0, 1]` **decision dimensions** (repairability, reusability, recycling, hazard,
environmental priority, material value), each a transparent **weighted mean** of
upstream signals, plus a **separate** overall-confidence axis, an auditable
per-dimension evidence breakdown and ordered reasoning + warnings. It does **not**
recommend an action, assign a monetary value or optimize — those are later
milestones. Like the material and environmental engines, its knowledge — the
per-dimension signal weights and the normalization constants — lives in an
**external, versioned YAML/JSON catalogue** so the weighting is **data, not
logic**. It mounts **no router**, adds **no endpoint**, and leaves the `/predict`
contract **unchanged**. Full details live in
[`docs/engineering/decision.md`](docs/engineering/decision.md).

### Design — fixed signal vocabulary, re-weightable priors, injected service

- **`decision/data/knowledge.yaml`** is the external, versioned catalogue: a
  `version`, a `normalization` block (four strictly-positive saturation constants
  that map the environmental engine's unbounded physical amounts onto `[0, 1]`), a
  `dimensions` block (all six dimensions, each a `signal → weight` map) and a
  `confidence` block (the five upstream confidence sources → weight).
- **`decision/knowledge.py`** owns the **fixed vocabulary** — eleven
  `CANONICAL_SIGNALS` and five `CONFIDENCE_SOURCES` — and the strict loader: it
  turns the file into immutable `Normalization`/`KnowledgeBase` value objects,
  **validating aggressively** (version present, normalization strictly positive,
  every dimension present, only canonical signals named, non-negative weights with
  at least one positive per dimension/confidence map) and failing with a typed
  `DecisionKnowledgeError`. The catalogue may **re-weight** the signals but may not
  invent new ones, so a typo is a load-time error.
- **`decision/inference.py` → `DecisionInferenceEngine`** is a pure three-stage
  fold: (1) **project** the five reports onto the eleven normalized signals
  (pass-through scores, a `HazardLevel` severity map, environmental saturation,
  mass fractions, identity completeness); (2) **blend** each dimension as the
  weighted mean of its signals, recording every `(signal, value, weight)` for
  auditability; (3) **aggregate confidence** on a separate axis, dropping sources
  at or below the floor and **without re-damping** (upstream confidences already
  encode device-type/conflict damping).
- **`decision/config.py` → `DecisionConfig`** is a thin locator + filter
  (`knowledge_path`, `min_confidence`); both map from env via `from_settings()`.
- **`decision/service.py` → `DecisionService.analyze(context, recoverability,
  components, materials, environmental)`** loads the catalogue once and stamps
  `eco_id`, `engine_version`, the catalogue `knowledge_version` and an injected
  `created_at`. All collaborators are injected → deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `decision/models.py` | Frozen `DecisionDimension`/`EvidenceSignal`/`DimensionEvidence`/`DecisionKnowledgeReport`; six normalized scores + separate confidence + evidence breakdown + `to_dict`. |
| **External catalogue** | `decision/data/knowledge.yaml` | Versioned YAML: normalization constants + per-dimension signal weights + confidence weights. |
| **Knowledge base & loader** | `decision/knowledge.py` | Fixed signal/confidence vocabulary; strict `load_knowledge()` → immutable `KnowledgeBase`; aggressive validation. |
| **Inference** | `decision/inference.py` | `DecisionInferenceEngine`: project → weighted-mean blend → separate confidence blend; clamp/round; ordered reasoning/warnings. |
| **Config** | `decision/config.py` | Catalogue locator + confidence floor; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `decision/service.py` | `analyze(context, recoverability, components, materials, environmental)` → immutable report; catalogue loaded once; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the decision engine is a **library**, not a service
surface. A future orchestrator chains it onto the five upstream engines
in-process:

```python
from device_ai.fusion import FusionService
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService
from device_ai.environmental import EnvironmentalService
from device_ai.decision import DecisionService

context = FusionService().fuse(evidence)                              # M1.7
recoverability = RecoverabilityService().assess(context)             # M1.8
components = ComponentService().analyze(context, recoverability)     # M1.9
materials = MaterialService().analyze(context, recoverability, components)  # M1.10
environmental = EnvironmentalService().analyze(
    context, recoverability, components, materials
)                                                                    # M1.11

report = DecisionService().analyze(
    context, recoverability, components, materials, environmental
)                                                                    # M2.1
report.repairability_score    # normalized [0, 1] evidence
report.hazard_score           # normalized [0, 1] (higher = more hazardous)
report.material_value_score   # normalized unit index (NOT currency)
report.overall_confidence     # separate axis; never scales a score
report.dimensions             # per-dimension evidence breakdown (signals + reason)
report.reasoning              # ordered, human-readable explanations
report.warnings               # operator-facing cautions
report.to_dict()              # fully serializable
```

M2.1 adds two **opt-in** environment variables (`DECISION_KNOWLEDGE_PATH`,
`DECISION_MIN_CONFIDENCE`; defaults reproduce the reference behaviour) and one new
error type, `DECISION_ERROR` (a typed `DeviceAIError`, with the loader raising the
`DECISION_KNOWLEDGE_ERROR` subclass on a malformed catalogue), surfaced to
orchestrating code rather than through the HTTP envelope.

## Circular Decision Engine (M2.2)

Milestone M2.2 ships the **sixth downstream consumer** of the fusion engine and
the second engine of **M2**: an internal-only, **deterministic rule-evaluation
engine** that consumes four upstream reports — `DeviceContext`,
`DecisionKnowledgeReport`, `RecoverabilityReport` and `EnvironmentalImpactReport` —
and produces the pipeline's **first actionable recommendation**, a single
**`DecisionReport`**. It answers *"given the consolidated evidence, what should
actually be done with this device — and how urgently?"*: a recommended
**end-of-life action** (`refurbish` / `repair` / `recycle` / `hazardous_disposal` /
`manual_review`, reusing the recoverability engine's `RecommendedAction`
vocabulary), a triage **priority** (`high` / `medium` / `low`), an aggregated
**confidence**, the exact **rules that fired** (in precedence order, winner
flagged) and ordered **reasoning** and **warnings**. Unlike M2.1's normalized
evidence, this report carries a real recommendation — and it stays **auditable**
because every recommendation is a **precedence-ordered, deterministic rule match**,
never a black-box verdict. It assigns **no monetary value** and performs **no
optimization**. Like the M2.1/M1.11/M1.10 engines, its decision policy — *which
evidence triggers which action, and in what precedence* — lives in an **external,
versioned YAML/JSON rule catalogue** so the policy is **data, not logic**. It
mounts **no router**, adds **no endpoint**, and leaves the `/predict` contract
**unchanged**. Full details live in
[`docs/engineering/circular.md`](docs/engineering/circular.md).

### Design — external rule catalogue, precedence-ordered match, injected service

- **`circular/data/rules.yaml`** is the external, versioned catalogue: a `version`,
  a precedence-ordered list of `rules` (each with `id`, unique `precedence`,
  `action`, `priority`, `reason`, a non-empty `when` conjunction of
  `{ signal, operator, threshold }` conditions, and an optional `confidence_factor`
  in `(0, 1]` and `warning`) and a required `default` fallback. The shipped
  catalogue's ten rules encode a **hazard-first → review-gate → recovery-ladder**
  policy.
- **`circular/rules.py`** owns the **fixed vocabulary** — sixteen
  `CANONICAL_SIGNALS` and four `CONDITION_OPERATORS` (`gte`/`lte`/`gt`/`lt`) — and
  the strict loader: it turns the file into immutable
  `RuleCondition`/`DecisionRule`/`DefaultRule`/`RuleCatalogue` value objects,
  **validating aggressively** (version present, at least one rule, unique ids and
  precedences, non-negative integer precedence, only canonical signals/operators
  named, in-range thresholds, `(0, 1]` confidence factors, a known action/priority,
  a non-empty `when`, a present default) and failing with a typed
  `CircularRuleError`. The catalogue may **re-order or re-tune** rules but may not
  invent a signal or operator, so a typo is a load-time error.
- **`circular/engine.py` → `CircularDecisionEngine`** is a pure three-stage
  evaluation: (1) **project** the four reports onto the sixteen normalized `[0, 1]`
  signals (pass-through scores, a `HazardLevel` severity map, the upstream
  force/conflict flags as `0.0`/`1.0`, identity completeness); (2) **match** every
  rule against the signals — a rule fires when **all** its conditions hold, and the
  fired rule with the lowest precedence wins (the rest retained as overridden
  alternatives), with the required `default` applied when nothing fires; (3)
  **aggregate confidence** as the consolidated decision confidence damped by the
  product of every fired rule's confidence factor — a **separate axis** that never
  changes the action.
- **`circular/config.py` → `CircularConfig`** is a thin locator + knobs
  (`rules_path`, `min_confidence`, `identity_field_count`); the first two map from
  env via `from_settings()`.
- **`circular/service.py` → `CircularService.decide(context, knowledge,
  recoverability, environmental)`** loads the catalogue once and stamps `eco_id`,
  `engine_version`, the catalogue `rules_version` and an injected `created_at`. All
  collaborators are injected → deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `circular/models.py` | Frozen `Priority`/`TriggeredRule`/`DecisionReport` (re-uses `RecommendedAction`); action + priority + confidence + ordered triggered rules (winner flagged) + ordered reasoning/warnings + `to_dict`. |
| **External catalogue** | `circular/data/rules.yaml` | Versioned YAML: precedence-ordered policy rules + required default fallback. |
| **Rules & loader** | `circular/rules.py` | Fixed signal/operator vocabulary; strict `load_rules()` → immutable `RuleCatalogue`; aggressive validation. |
| **Engine** | `circular/engine.py` | `CircularDecisionEngine`: project → precedence-ordered rule match → damped confidence; clamp/round; ordered reasoning/warnings. |
| **Config** | `circular/config.py` | Catalogue locator + confidence floor + identity-field count; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `circular/service.py` | `decide(context, knowledge, recoverability, environmental)` → immutable report; catalogue loaded once; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the circular engine is a **library**, not a service
surface. A future orchestrator chains it onto the upstream engines in-process —
note the **four** inputs (`context`, `knowledge`, `recoverability`,
`environmental`):

```python
from device_ai.decision import DecisionService
from device_ai.circular import CircularService

knowledge = DecisionService().analyze(
    context, recoverability, components, materials, environmental
)                                                                    # M2.1

decision = CircularService().decide(
    context, knowledge, recoverability, environmental
)                                                                    # M2.2
decision.recommended_action   # RecommendedAction (refurbish/repair/recycle/…)
decision.priority             # Priority (high/medium/low)
decision.confidence           # separate axis; never changes the action
decision.triggered_rules      # rules that fired, precedence order, winner flagged
decision.winning_rule         # the deciding rule, or None when the fallback applied
decision.reasoning            # ordered, human-readable explanations
decision.warnings             # operator-facing cautions
decision.to_dict()            # fully serializable
```

M2.2 adds two **opt-in** environment variables (`CIRCULAR_RULES_PATH`,
`CIRCULAR_MIN_CONFIDENCE`; defaults reproduce the reference behaviour) and one new
error type, `CIRCULAR_DECISION_ERROR` (a typed `DeviceAIError`, 500, with the
loader raising the `CIRCULAR_RULE_ERROR` subclass, 422, on a malformed catalogue),
surfaced to orchestrating code rather than through the HTTP envelope.

## Device Passport Core (M2.3)

Milestone M2.3 ships the **Device Passport Core**: an internal-only,
deterministic **assembler** that consumes five upstream artefacts — a fused,
immutable `DeviceContext` (M1.7), a `DecisionReport` (M2.2), a `MaterialReport`
(M1.10), an `EnvironmentalImpactReport` (M1.11) and a `DeviceFingerprint` (M1.5) —
and **composes** them into a single, immutable **`DevicePassport`**: the
device's consolidated, portable record. Every other engine *infers* something new;
the passport core deliberately **does not**. It answers *"gather everything the
pipeline already knows about this device into one auditable document"* — it
**never re-scores a dimension, re-recommends an action or assigns a value**. The
passport carries a content-addressed **passport id**, a stamped **passport
version** and **EcoID**, device **identity** and **classification**, condensed
**decision / material / environmental / fingerprint** summaries, a transparent
**confidence summary**, provenance **metadata**, and ordered human-readable
**reasoning** and **warnings**. The passport's **structure** — which sections it
must contain and each section's field/range contract — lives in an **external,
versioned** YAML **schema** (not a rule catalogue) behind a **strict validator**,
so the shape is **data, not logic**. It mounts **no router**, adds **no
endpoint**, and leaves the `/predict` contract **unchanged**. It implements **no
blockchain, QR codes, CBOR, digital signatures, ownership history, lifecycle
events or database persistence** — those are later milestones. Full details live in
[`docs/engineering/passport.md`](docs/engineering/passport.md).

### Design — external schema, deterministic builder, composition-not-inference

- **`passport/data/schema.yaml`** is the external, versioned schema: a `version`
  and thirteen ordered `sections`, each with a `kind` (`string` / `object` /
  `array`), the `fields` an object section must carry and the `confidence_fields`
  that must be numeric in `[0, 1]`. It describes the passport's **structure**, not a
  decision policy; bumping a section or a field/range contract is a data change,
  reviewable without touching code.
- **`passport/schema.py`** owns the strict loader and validator: `load_schema()`
  turns the file into immutable `SectionSchema`/`PassportSchema` value objects,
  **validating aggressively** (version present, at least one section, every `kind`
  known, object sections declaring a non-empty `fields` list, every
  `confidence_field` present in its section's fields) and failing with a typed
  `PassportSchemaError`. `validate_passport(payload, schema)` then checks a built
  passport against that schema — every required section present and of the right
  kind, every declared field present, every confidence field a real number in
  `[0, 1]` (booleans rejected) — raising `PassportValidationError` on any breach.
- **`passport/builder.py` → `PassportBuilder`** is the **deterministic** four-stage
  composition: (1) **summarize** — project each upstream report onto its condensed
  passport section (identity, classification, decision, material, environmental,
  fingerprint), copying values verbatim; (2) **compose confidence** — the
  `ConfidenceSummary.overall` is the plain **arithmetic mean** of the four upstream
  confidences (classification, decision, material, environmental), rounded to six
  decimals — **a transparent composition, never a new inference**; (3) **identify**
  — derive a **content-addressed passport id** (`ET-PP-` + a 12-char uppercase
  SHA-256 prefix over the device's identifying fields) so the same device always
  maps to the same id, independent of the build timestamp; (4) **narrate** — lead
  the reasoning with the composed recommendation line, extend it with the decision's
  reasoning, and union the upstream warnings (de-duplicated, order-preserving), both
  bounded by the config's presentation caps.
- **`passport/config.py` → `PassportConfig`** is a thin locator + knobs
  (`schema_path`, `passport_version`, `max_reasoning`, `max_warnings`); the first
  two map from env via `from_settings()`.
- **`passport/service.py` → `PassportService.build(context, decision, materials,
  environmental, fingerprint=None)`** loads the schema **once** at construction,
  runs the builder, **validates** the assembled passport against the schema and
  stamps `passport_version`, the schema `version`, `engine_version` and an injected
  `created_at`. All collaborators (config, schema, builder, clock) are injected →
  deterministic tests. The fingerprint is **optional**: an absent fingerprint yields
  a well-defined empty fingerprint section plus a warning, never an error.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `passport/models.py` | Frozen `DeviceIdentity`/`Classification`/`DecisionSummary`/`MaterialSummary`/`EnvironmentalSummary`/`FingerprintSummary`/`ConfidenceSummary`/`PassportMetadata`/`DevicePassport`; ordered reasoning/warnings + `to_dict` + deterministic `to_json`. |
| **External schema** | `passport/data/schema.yaml` | Versioned YAML: thirteen ordered sections with per-section kind, fields and confidence-field range contract. |
| **Schema loader & validator** | `passport/schema.py` | Fixed `SectionKind` vocabulary; strict `load_schema()` → immutable `PassportSchema`; `validate_passport()` structural + range check; aggressive validation. |
| **Builder** | `passport/builder.py` | `PassportBuilder`: summarize → compose confidence (arithmetic mean) → content-addressed id → narrate; verbatim composition, clamp/round; ordered reasoning/warnings. |
| **Config** | `passport/config.py` | Schema locator + passport version + presentation caps in one frozen dataclass; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `passport/service.py` | `build(context, decision, materials, environmental, fingerprint=None)` → immutable, schema-validated passport; schema loaded once; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the passport core is a **library**, not a service
surface. A future orchestrator chains it onto the upstream engines in-process —
note the **five** inputs (`context`, `decision`, `materials`, `environmental`,
`fingerprint`):

```python
from device_ai.circular import CircularService
from device_ai.passport import PassportService

decision = CircularService().decide(
    context, knowledge, recoverability, environmental
)                                                                    # M2.2

passport = PassportService().build(
    context, decision, materials, environmental, fingerprint
)                                                                    # M2.3
passport.passport_id          # "ET-PP-…" content-addressed, timestamp-independent
passport.passport_version     # stamped semantic version
passport.eco_id               # carried from the DeviceContext
passport.classification       # device type + confidence
passport.decision_summary     # recommended action + priority + confidence
passport.material_summary     # recoverable/hazardous mass + confidence
passport.environmental_summary# carbon/energy/water saved + indices + confidence
passport.fingerprint_summary  # fingerprint id + encoder provenance (or empty)
passport.confidence_summary   # arithmetic-mean overall + the four components
passport.reasoning            # ordered, human-readable explanations
passport.warnings             # operator-facing cautions
passport.to_dict()            # fully serializable
passport.to_json()            # deterministic, canonical JSON
```

M2.3 adds two **opt-in** environment variables (`PASSPORT_SCHEMA_PATH`,
`PASSPORT_VERSION`; defaults reproduce the reference behaviour, so an existing
deployment is unchanged) and one new error type, `PASSPORT_ERROR` (a typed
`DeviceAIError`, 500, with the loader raising `PASSPORT_SCHEMA_ERROR` and the
validator raising `PASSPORT_VALIDATION_ERROR`, both 422, on a malformed schema or
a non-conformant passport), surfaced to orchestrating code rather than through the
HTTP envelope.

## Device Passport Validation & Integrity Engine (M2.4)

Milestone M2.4 ships the **Device Passport Validation & Integrity Engine**: an
internal-only, deterministic **checker** that consumes the M2.3 `DevicePassport`
and produces a single, immutable **`PassportIntegrityReport`** — the passport's
independent trust verdict. Every engine up to and including M2.3 *produces* the
passport; this engine deliberately **produces nothing new about the device** — it
answers *"is this passport well-formed, and has it been tampered with since it was
built?"*. It **re-validates** the assembled passport against an **external,
versioned** YAML **validation rule-set** and computes a **SHA-256 canonical
integrity hash** over the passport's deterministic serialization, so any later
byte-level mutation is detectable by recomputation. The report carries a
**validation status** (`valid` / `valid_with_warnings` / `invalid`), the
**canonical hash** and its **algorithm**, the observed **schema version** and
**passport version**, the ordered **checked sections** (each with its `kind`,
`present` and `valid` flags), and ordered **warnings** and **errors**. It
**re-checks and hashes — it never re-scores a dimension, re-recommends an action,
assigns a value or mutates the passport**. The validation rule-set — which sections
must be present, each section's kind and field contract, and which fields must be
confidences in `[0, 1]` — lives in an **external, versioned** YAML file behind a
**strict loader**, so the integrity contract is **data, not logic**. It mounts **no
router**, adds **no endpoint**, and leaves the `/predict` contract **unchanged**. It
implements **no blockchain, digital signatures, QR codes, CBOR, ownership history,
lifecycle events or database persistence** — those remain later milestones. Full
details live in [`docs/engineering/integrity.md`](docs/engineering/integrity.md).

### Design — external rule-set, inverted trust boundary, canonical hash

- **`integrity/data/rules.yaml`** is the external, versioned validation rule-set: a
  `version` and thirteen ordered `sections` mirroring the passport schema, each with
  a `kind` (`string` / `object` / `array`), the `fields` an object section must
  carry, the `confidence_fields` that must be numeric in `[0, 1]` and an optional
  `required` flag (only `fingerprint_summary` is optional). It describes the
  passport's **integrity contract**, reviewable and bumpable without touching code.
- **`integrity/rules.py`** owns the **strict loader**: `load_rules()` turns the file
  into immutable `SectionRule`/`IntegrityRuleSet` value objects, **validating
  aggressively** (version present, sections a mapping, every `kind` known, object
  sections declaring non-empty non-duplicate `fields`, string sections declaring
  none, every `confidence_field` present in its section's fields, a boolean
  `required`) and failing with a typed `PassportIntegrityRuleError`. A malformed
  **rule-set is an engine fault** — it is **raised**, exactly like the passport
  schema loader.
- **`integrity/validator.py` → `PassportIntegrityValidator`** performs the two-part
  check. **Structural:** for every rule section it records a `CheckedSection`
  (`present` / `valid`) and appends ordered, de-duplicated warnings (a missing
  *optional* section) and errors (a missing *required* section, a wrong section
  kind, a missing object field, a confidence field that is absent, non-numeric,
  boolean or outside `[0, 1]`). **Integrity:** it serializes the passport to its
  deterministic canonical JSON and hashes the bytes with SHA-256. A malformed
  **passport is untrusted input** — it is **reported** as ordered errors on the
  report, **never raised**. This trust boundary is the deliberate **inverse** of the
  M2.3 assembler (which raises `PassportValidationError` on its own output): the
  integrity engine treats the passport as data to be judged, not trusted.
- **`integrity/config.py` → `IntegrityConfig`** is a thin locator + knob
  (`rules_path`, `hash_algorithm`); both map from env via `from_settings()`, and the
  rules path resolves against the `device_ai` package root when relative.
- **`integrity/service.py` → `IntegrityService.validate(passport)`** loads the
  rule-set **once** at construction, drives the validator and stamps the observed
  `schema_version` and `passport_version`, the rule-set `version`, `engine_version`
  and an injected `created_at`. All collaborators (config, rule-set, validator,
  clock) are injected → deterministic tests.

### Capabilities

| Concern | Module | What it provides |
|---|---|---|
| **Domain model** | `integrity/models.py` | Frozen `ValidationStatus`/`CheckedSection`/`PassportIntegrityReport`; status + canonical hash + schema/passport versions + ordered checked sections + ordered warnings/errors + `is_valid`/counts + `to_dict`/deterministic `to_json`. |
| **External rule-set** | `integrity/data/rules.yaml` | Versioned YAML: thirteen ordered sections with per-section kind, fields, confidence-field range contract and optional-section flag. |
| **Rule-set loader** | `integrity/rules.py` | Fixed `SectionKind` vocabulary; strict `load_rules()` → immutable `IntegrityRuleSet`; aggressive validation; **raises** on a malformed rule-set. |
| **Validator** | `integrity/validator.py` | `PassportIntegrityValidator`: structural section/field/confidence checks (ordered, de-duplicated warnings + errors) + SHA-256 canonical integrity hash; **reports** a malformed passport, never raises. |
| **Config** | `integrity/config.py` | Rule-set locator + hash algorithm in one frozen dataclass; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `integrity/service.py` | `validate(passport)` → immutable integrity report; rule-set loaded once; version/clock stamping; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the integrity engine is a **library**, not a service
surface. A future orchestrator chains it directly onto the M2.3 passport core
in-process — it consumes the **one** artefact the passport core produces:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService

passport = PassportService().build(
    context, decision, materials, environmental, fingerprint
)                                                                    # M2.3

report = IntegrityService().validate(passport)                       # M2.4
report.status                 # ValidationStatus (valid / valid_with_warnings / invalid)
report.is_valid               # True unless status is INVALID
report.canonical_hash         # 64-char SHA-256 hex over the canonical serialization
report.hash_algorithm         # "sha256"
report.schema_version         # observed passport schema version
report.passport_version       # observed passport version
report.checked_sections       # ordered CheckedSection tuple (name/kind/present/valid)
report.warnings               # ordered, de-duplicated cautions
report.errors                 # ordered, de-duplicated structural failures
report.to_dict()              # fully serializable
report.to_json()              # deterministic, canonical JSON
```

M2.4 adds two **opt-in** environment variables (`INTEGRITY_RULES_PATH`,
`INTEGRITY_HASH_ALGORITHM`; defaults reproduce the reference behaviour, so an
existing deployment is unchanged) and one new error type, `PASSPORT_INTEGRITY_ERROR`
(a typed `DeviceAIError`, 500, with the loader raising the
`PASSPORT_INTEGRITY_RULE_ERROR` subclass, 422, on a malformed rule-set or an
unsupported hash algorithm), surfaced to orchestrating code rather than through the
HTTP envelope.

## Trust & Provenance Engine (M2.5)

M2.5 is an internal-only, **deterministic trust evaluator**. It consumes the four
upstream artefacts the pipeline already produced — the immutable `DevicePassport`
(M2.3), its `PassportIntegrityReport` (M2.4), the normalized
`DecisionKnowledgeReport` (M2.1) and the actionable `DecisionReport` (M2.2) — and
emits a single, immutable **`PassportTrustReport`**. It answers one question about
the passport: *how much can this document be trusted as a faithful representation
of the device?* Unlike M2.3 (which *assembles* the passport) and M2.4 (which
*checks* it), the trust engine carries **no inference and no evidence collection of
its own**: it reads the existing confidence and consistency signals its four inputs
already carry, blends them into a weighted-average score, and maps that score to a
level. Full details live in [`docs/engineering/trust.md`](docs/engineering/trust.md).

**The report carries the eight required fields** — a normalized `trust_score`
(`[0, 1]` weighted average), a mapped `trust_level` (`high` / `medium` / `low` /
`untrusted`), the four sub-axes `identity_confidence`, `evidence_consistency`,
`decision_confidence` and `integrity_confidence`, ordered `reasoning` and ordered
`warnings` — plus the four `TrustAxis` records (each with its value, catalogue
**weight** and a **reason**) and provenance (`engine_version`, `rules_version`, an
optional `created_at`).

The four sub-axes are transparent projections of existing signals — never new
inferences:

| Axis | Projected from | How |
|---|---|---|
| **Identity confidence** | passport identity + classification | mean of identity completeness (fraction of the strong fields `model`/`serial`/`imei`/`mac` present) and classification confidence. |
| **Evidence consistency** | passport + knowledge + decision device types, conflict flag | `1.0` when all present types agree with no conflict; `0.8` agree-but-conflict; `0.4`/`0.2` disagree (no-conflict/conflict); `0.5` when no type resolved. |
| **Decision confidence** | knowledge + circular decision | arithmetic mean of the decision-knowledge overall confidence and the circular-decision confidence. |
| **Integrity confidence** | integrity report | `1.0` when `valid`; `1.0 − penalty×warnings` when `valid_with_warnings`; `0.0` when `invalid`. |

The `trust_score` is the catalogue-weighted average of the four axes
(`Σ(valueᵢ × weightᵢ) / Σweightᵢ`, clamped and rounded to six places); the
`trust_level` is the score mapped through the catalogue's descending score floors.
Both are re-derivable by hand from the `axes` and thresholds. The engine's scoring
policy — the per-axis blend weights and the level thresholds — lives **outside the
code** in an external, versioned catalogue (`trust/data/rules.yaml`) behind a
**strict loader** that fails with a typed `PassportTrustRuleError` on any
structural problem. A malformed **catalogue** *raises* (an engine fault); inputs
that merely **score low** are *reported* as a low level and ordered warnings, never
raised.

Component map (mirrors the M2.4 layering):

| Component | Location | Responsibility |
|---|---|---|
| **Domain models** | `trust/models.py` | Frozen `TrustLevel`, `TrustAxis` and `PassportTrustReport`, each with its own `to_dict()`; canonical `to_json()`. |
| **Catalogue loader** | `trust/rules.py` | Fixed `CANONICAL_AXES` vocabulary; strict `load_rules()` → immutable `TrustRuleSet` (`weight_for`, `level_for`); **raises** on a malformed catalogue. |
| **Engine** | `trust/engine.py` | `TrustEngine.evaluate(...)`: project four reports → four axes → weighted-average score → mapped level; ordered reasoning + warnings; deterministic. |
| **Config** | `trust/config.py` | Catalogue locator + low-trust floor + two projection knobs in one frozen dataclass; env mapping via `from_settings()`; package-root path resolution. |
| **Orchestration** | `trust/service.py` | `assess(passport, integrity, knowledge, decision)` → immutable trust report; catalogue loaded once; version/clock stamping; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the trust engine is a **library**, not a service
surface. A future orchestrator chains it directly onto the M2.3/M2.4 output
in-process — it consumes the **four** artefacts the pipeline already produced:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService
from device_ai.trust import TrustService, TrustLevel

passport = PassportService().build(
    context, decision, materials, environmental, fingerprint
)                                                                    # M2.3
integrity = IntegrityService().validate(passport)                    # M2.4

report = TrustService().assess(passport, integrity, knowledge, decision)  # M2.5
report.trust_score            # normalized [0, 1] weighted average
report.trust_level            # TrustLevel (high / medium / low / untrusted)
report.identity_confidence    # the four sub-axes, also on report.axes
report.evidence_consistency
report.decision_confidence
report.integrity_confidence
report.axes                   # ordered TrustAxis tuple (name/value/weight/reason)
report.reasoning              # ordered, human-readable reasons
report.warnings               # ordered operator cautions
report.to_dict()              # fully serializable
report.to_json()              # deterministic, canonical JSON
```

M2.5 adds two **opt-in** environment variables (`TRUST_RULES_PATH`,
`TRUST_MIN_SCORE`; defaults reproduce the reference behaviour, so an existing
deployment is unchanged) and one new error type, `PASSPORT_TRUST_ERROR` (a typed
`DeviceAIError`, 500, with the loader raising the `PASSPORT_TRUST_RULE_ERROR`
subclass, 422, on a malformed catalogue), surfaced to orchestrating code rather
than through the HTTP envelope.

## Blockchain Ledger Core (M3.1)

M3.1 is the **first component of milestone M3** — an internal-only,
**deterministic immutable-ledger builder**. It consumes the three upstream
artefacts the passport pipeline already produced — the immutable `DevicePassport`
(M2.3), its `PassportIntegrityReport` (M2.4) and its `PassportTrustReport` (M2.5)
— and emits a tamper-evident **`Blockchain`**: an ordered chain of **`Block`**
objects, each carrying one **`LedgerRecord`** payload and one **`BlockHeader`**
that links it to the previous block via a deterministic SHA-256 hash. It answers
one question: *how do we record this passport in an append-only, independently
verifiable audit trail?* Unlike M2.3 (which *assembles* the passport), M2.4
(which *checks* it) and M2.5 (which *scores* it), the ledger core carries **no
inference and no evidence collection of its own**: it snapshots the three
reports' key outcomes into a record, hashes it, and chains it. Full details live
in [`docs/engineering/ledger.md`](docs/engineering/ledger.md).

**The chain is built by local hash-chaining alone** — **no** Hyperledger Fabric,
Ethereum, consensus, proof-of-work, smart contracts, wallets, digital signatures,
REST endpoints, networking or persistence. Each `LedgerRecord` snapshots the
passport id + version (M2.3), the canonical integrity hash + engine version
(M2.4), and the trust score + level + engine version (M2.5). Each block's
`previous_hash` is the SHA-256 digest of the prior block's header (or a genesis
sentinel of 64 zeros for the first block) and its `record_hash` is the SHA-256
digest of its own record, so any later mutation of a block's contents or the
chain's order breaks the recomputed hashes and is detected on verification. The
future Hyperledger Fabric backend in
[`docs/engineering/09_BLOCKCHAIN.md`](../../docs/engineering/09_BLOCKCHAIN.md) is a
**separate** concern that can later anchor these hashes.

The four sub-artefacts are frozen, slotted value objects, each with its own
`to_dict()` and canonical `to_json()`:

| Artefact | Meaning |
|---|---|
| **`LedgerRecord`** | The block payload — a snapshot of the passport id/version, integrity hash/engine version, and trust score/level/engine version. |
| **`BlockHeader`** | The chain link — `index`, optional `timestamp`, `previous_hash` (prior header's SHA-256 or the genesis sentinel), `record_hash` (this record's SHA-256). |
| **`Block`** | One immutable block: its `header` + single `record`, with `index`/`previous_hash`/`record_hash` convenience properties delegating to the header. |
| **`Blockchain`** | The ordered chain: `blocks`, `version`, `is_valid`, `block_count`, optional `created_at`. |

`verify_chain` recomputes the chain from scratch and checks **sequential indices**
(from `0`), **previous-hash linking** (the genesis sentinel, then each prior
header's recomputed hash) and **record-hash matching** (each block's own record).
A malformed **config** or an unsupported hash algorithm (engine faults) *raise*
(`LedgerConfigError` / `LedgerError`); a mutated block or re-ordered chain is
never raised — it is *reported* as `is_valid == False`, because detecting that
tampering is exactly the job the core exists to do.

Component map (mirrors the M2.4/M2.5 layering):

| Component | Location | Responsibility |
|---|---|---|
| **Domain models** | `ledger/models.py` | Frozen `LedgerRecord`, `BlockHeader`, `Block`, `Blockchain`, each with its own `to_dict()`; canonical `to_json()`. |
| **Config loader** | `ledger/config.py` | Frozen `LedgerConfig`; strict `load_config()` validating hash algorithm / versions / hex genesis; **raises** `LedgerConfigError` on a malformed file. |
| **Builder** | `ledger/builder.py` | `LedgerBuilder`: `create_record` → `create_block` → `create_chain` / `append_block` / `verify_chain`; deterministic SHA-256 hashing and previous-hash linking. |
| **Orchestration** | `ledger/service.py` | `genesis` / `append` / `append_record` / `build_chain` / `verify` → immutable chain; config loaded once; version/clock stamping; all collaborators injected. |

### Internal-only — no endpoints

Like every engine before it, the ledger core is a **library**, not a service
surface. A future orchestrator chains it directly onto the M2.3/M2.4/M2.5 output
in-process — it consumes the **three** artefacts the pipeline already produced:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService
from device_ai.trust import TrustService
from device_ai.ledger import LedgerService

passport = PassportService().build(
    context, decision, materials, environmental, fingerprint
)                                                                    # M2.3
integrity = IntegrityService().validate(passport)                    # M2.4
trust = TrustService().assess(passport, integrity, knowledge, decision)  # M2.5

ledger = LedgerService()                                             # M3.1
chain = ledger.genesis(passport, integrity, trust)          # first device (index 0)
chain = ledger.append(chain, passport2, integrity2, trust2) # subsequent devices
chain.is_valid                # structural validation status
ledger.verify(chain)          # re-verify on demand (tamper detection)
chain.blocks                  # ordered Block tuple (header + record)
chain.to_dict()               # fully serializable ledger
chain.to_json()               # deterministic, canonical JSON
```

M3.1 adds **no** environment variables — the ledger's policy (hash algorithm,
versions, genesis sentinel) lives entirely in the external, versioned
`ledger/data/ledger.yaml` behind a strict loader, and `from_settings()` returns
the default config. It adds one new error type, `LEDGER_ERROR` (a typed
`DeviceAIError`, 500, for an unsupported hash algorithm) with the loader raising
the `LEDGER_CONFIG_ERROR` subclass (422) on a malformed config — surfaced to
orchestrating code rather than through the HTTP envelope. The `/predict` contract
is **unchanged**.

## Ledger Backend Abstraction Layer (M3.2)

M3.2 is the **second component of milestone M3**. M3.1 produces a `Blockchain` as
an in-memory value but never says **where a chain lives** or **how it is
written**; M3.2 answers that without committing to a technology. It introduces a
technology-agnostic **`LedgerBackend`** protocol and makes the `LedgerService`
persist chains through an *injected* backend, depending only on that protocol — so
the ledger technology (in-memory, a mock Fabric channel, a mock Ethereum
contract, or a future *real* anchor) can change without touching the domain or the
service. Full details live in
[`docs/engineering/ledger.md`](docs/engineering/ledger.md).

**Still no real ledger technology** — **no** Hyperledger Fabric SDK, chaincode,
certificates, consensus, Ethereum RPC, smart contracts, wallets, digital
signatures, networking or persistence. All three backends are **deterministic**
and **in-memory**; the two mocks emit technology-*shaped* metadata only, to prove
the abstraction. The service owns chain **identity** — it derives a stable,
content-addressed `chain_id` from the chain's genesis block and passes it to the
backend — so each backend is a pure key-value store and never re-implements
identity logic.

The `LedgerBackend` protocol (`@runtime_checkable`) is four methods, and every
`write` returns an immutable **`LedgerReceipt`** (`chain_id`, `backend`,
`metadata`):

| Method | Contract |
|---|---|
| `write(chain_id, chain) → LedgerReceipt` | Persist `chain` under `chain_id` (last-write-wins); return a receipt with the id and backend metadata. |
| `read(chain_id) → Blockchain \| None` | The stored chain, or **`None`** for an unknown id — never raises on a miss. |
| `exists(chain_id) → bool` | Whether a chain is stored under `chain_id`. |
| `list_ids() → list[str]` | Every stored chain id (order not guaranteed). |

Three implementations ship — the service drives all three identically, differing
**only** in the metadata each records:

| Backend | `name` | Receipt metadata |
|---|---|---|
| **`MemoryLedgerBackend`** | `memory` | `block_count`. The default (constructed when none is injected) and the one used throughout the test suite. |
| **`MockFabricLedgerBackend`** | `mock_fabric` | Fabric-*shaped*: a monotonic `tx_id` (`fabric-tx-00000001`, …), `channel` (`ecotrace-ledger`, injectable), `block_number`. |
| **`MockEthereumLedgerBackend`** | `mock_ethereum` | Ethereum-*shaped*: a content-addressed `tx_hash` (`"0x" + SHA-256(chain.to_json())`), monotonic `nonce`/`block_number`, `gas_used` (`21000`, injectable), `contract` (`0xEcoTraceLedger`, injectable). |

The `LedgerService` gains a persistence surface built entirely on the protocol,
with the backend injected exactly like the config, builder and clock before it
(`LedgerService(*, config=None, builder=None, backend=None, clock=_utc_now)`,
defaulting to `MemoryLedgerBackend()`):

```python
from device_ai.ledger import LedgerService, MockFabricLedgerBackend

# Default in-memory backend — nothing to wire — or inject any conforming backend.
ledger = LedgerService(backend=MockFabricLedgerBackend())   # M3.2

chain = ledger.genesis(passport, integrity, trust)          # M3.1 (unchanged)
receipt = ledger.save(chain)          # → LedgerReceipt(chain_id, backend, metadata)
ledger.exists(receipt.chain_id)       # True
ledger.load(receipt.chain_id) == chain  # round-trips
ledger.list_ids()                     # [receipt.chain_id]
```

M3.2 is **purely additive**: the `backend=` parameter is keyword-only with a
default, so every existing construction and every M3.1 method behaves exactly as
before, and all 60 M3.1 tests pass unchanged. It adds **no** new environment
variables, **no** new error types and leaves the `/predict` contract **unchanged**.

## Device Lifecycle Ledger Engine (M3.3)

M3.3 is the **third component of milestone M3** and the first to model a device's
*complete history* rather than a single passport verdict. It is an internal-only,
**deterministic device-history builder**: a caller records an ordered sequence of
immutable **`LifecycleEvent`** objects (each a `LifecycleEventType` plus an
optional actor, location, note and timestamp), the engine validates that ordering
against an **external, versioned state machine**, and composes it into an
immutable **`LifecycleRecord`**. Full details live in
[`docs/engineering/lifecycle.md`](docs/engineering/lifecycle.md).

The state machine is **policy, not logic** — it lives in
`lifecycle/data/transitions.yaml` behind a strict loader (`load_rules`) that
validates aggressively and fails with a typed **`LifecycleRuleError`** on any
structural problem (an unknown or missing event type, a self-transition or
duplicate target, no terminal event, an empty/unknown initial event, …). The
shipped rules encode an e-waste lifecycle: `registered` is the sole initial
event, `disposed` the sole terminal one, with a fork at `assessed`
(refurbish / recycle / dispose) and a legal loop (`refurbished → in_use`):

| Event type | Legal successors |
|---|---|
| `registered` (initial) | `in_use`, `collected` |
| `in_use` | `collected` |
| `collected` | `in_transit`, `assessed` |
| `in_transit` | `assessed`, `collected` |
| `assessed` | `refurbished`, `recycled`, `disposed` |
| `refurbished` | `in_use`, `recycled` |
| `recycled` | `disposed` |
| `disposed` (terminal) | — |

The stateless **`LifecycleEngine`** is three methods — `validate(events, rules)`
(is the ordering a legal path?), `build_record(...)` (validate then snapshot into
a `LifecycleRecord` with the verdict, event count, current state and provenance)
and `can_append(record, event, rules)` (the incremental predicate). An illegal
ordering — a non-initial genesis event, an undeclared transition, or an event
after a terminal one — is **reported** as `is_valid == False`, never raised; only
a malformed rules file (an engine fault) raises. The injectable
**`LifecycleService`** façade loads the rules once at construction and stamps
engine/rules versions (and an optional timestamp) onto every record; like every
service before it, every collaborator is constructor-injected with a sensible
default:

```python
from device_ai.lifecycle import LifecycleEventType, LifecycleService

E = LifecycleEventType
svc = LifecycleService()                             # loads the shipped rules once

record = svc.build("ET-PP-0000000001", [
    svc.event(E.REGISTERED, actor="mint"),
    svc.event(E.IN_USE),
    svc.event(E.COLLECTED, location="Bengaluru hub"),
    svc.event(E.ASSESSED),
    svc.event(E.RECYCLED),
    svc.event(E.DISPOSED),
])
assert record.is_valid and record.current_state == "disposed"

svc.append(record, svc.event(E.IN_USE))              # is_valid == False (after terminal)
```

**Ledger integration through the M3.2 backend abstraction.** The engine models a
device's *history*; the M3.1 ledger anchors a passport's *verdicts*. The service
correlates the two **through the injected `LedgerService`** — never a concrete
store — so it works identically across every backend:

```python
from device_ai.ledger import LedgerService, MockFabricLedgerBackend
from device_ai.lifecycle import LifecycleService

svc = LifecycleService(ledger=LedgerService(backend=MockFabricLedgerBackend()))
svc.is_anchored(chain_id)      # → bool   (delegates to ledger.exists)
svc.anchored_chain(chain_id)   # → Blockchain | None  (delegates to ledger.load)
svc.anchored_ids()             # → list[str]  (delegates to ledger.list_ids)
```

M3.3 is **purely additive** and **internal-only**: it adds the `lifecycle/`
package and two typed exceptions (`LifecycleError`, `LifecycleRuleError`) and one
env-driven knob (`LIFECYCLE_RULES_PATH`, defaulting to the packaged rules), and
touches **no** upstream engine, **no** router and **no** part of the `/predict`
contract. It implements **no** Hyperledger Fabric, chaincode, smart contracts,
REST endpoints, networking, GPS tracking, event streaming, QR scanning, wallets
or digital signatures — those are out of scope for M3.3.

## Configuration

All configuration is via environment variables (parsed once at startup).
Copy `.env.example` to `.env` to override. Defaults live in
`configs/settings.py`.

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind interface |
| `PORT` | `8100` | Bind port |
| `MODEL_DIR` | `models` | Root of versioned model artifacts |
| `UPLOAD_DIR` | `uploads` | Transient upload storage (optional) |
| `DATASET_DIR` | `datasets` | Root of the managed dataset sub-folders |
| `ARTIFACT_DIR` | `artifacts` | Root of training artifacts (`checkpoints`/`exports`/`reports`) + model registry (M1.3) |
| `MLRUNS_DIR` | `mlruns` | Root of experiment-tracking runs (M1.3) |
| `EXPERIMENT_TRACKER` | `json` | Run-tracking backend: `json` \| `mlflow` \| `none` (M1.3) |
| `TRAINING_SEED` | `42` | Default RNG seed for reproducible training runs (M1.3) |
| `DETECTOR_WEIGHTS` | `yolov8n.pt` | Detector artifact (file/dir under `MODEL_DIR`); falls back to mock if absent (M1.4) |
| `DETECTOR_IMAGE_SIZE` | `640` | Inference image size in px for the YOLO detector (M1.4) |
| `DETECTOR_CONFIDENCE_THRESHOLD` | `0.25` | Minimum kept-detection confidence (M1.4) |
| `CLIP_MODEL_NAME` | `ViT-B-32` | OpenCLIP architecture name (backend-only) (M1.5) |
| `CLIP_PRETRAINED` | `laion2b_s34b_b79k` | OpenCLIP pretrained-weights tag (M1.5) |
| `CLIP_WEIGHTS` | `clip` | CLIP artifact locator under `MODEL_DIR`; falls back to mock if absent (M1.5) |
| `FINGERPRINT_METRIC` | `cosine` | Default similarity metric: `cosine` \| `euclidean` \| `manhattan` (M1.5) |
| `FINGERPRINT_MATCH_THRESHOLD` | `0.85` | Similarity (0..1) at/above which two fingerprints match (M1.5) |
| `FINGERPRINT_BACKEND` | `memory` | Fingerprint persistence backend: `memory` \| `json` (M1.5) |
| `FINGERPRINT_STORE_DIR` | `fingerprints` | Directory for the JSON fingerprint backend (M1.5) |
| `OCR_BACKEND` | `easyocr` | OCR text backend: `easyocr` (auto-degrades to mock) \| `mock` (M1.6) |
| `OCR_LANGUAGES` | `["en"]` | Language codes passed to the EasyOCR reader (M1.6) |
| `OCR_WEIGHTS` | `ocr` | EasyOCR model-storage locator under `MODEL_DIR`; falls back to mock if absent (M1.6) |
| `OCR_USE_GPU` | `false` | Request GPU inference from the EasyOCR reader (M1.6) |
| `OCR_MIN_CONFIDENCE` | `0.30` | Recognition confidence below which EasyOCR rows are discarded (M1.6) |
| `BARCODE_ENABLED` | `true` | Decode QR/barcodes alongside text (M1.6) |
| `RECOVERABILITY_REFURBISH_MIN_REUSABILITY` | `0.65` | Reusability floor for a refurbish recommendation (M1.8) |
| `RECOVERABILITY_REPAIR_MIN_REPAIRABILITY` | `0.55` | Repairability floor for a repair recommendation (M1.8) |
| `RECOVERABILITY_RECYCLE_MIN_RECYCLABILITY` | `0.45` | Recyclability floor for a recycle recommendation (M1.8) |
| `RECOVERABILITY_LOW_CONFIDENCE_THRESHOLD` | `0.50` | Fused confidence below which review is forced (M1.8) |
| `COMPONENT_PROFILES_PATH` | `components/data/components.yaml` | Locator of the external component-profile catalogue (YAML/JSON), resolved against the `device_ai` package root when relative (M1.9) |
| `COMPONENT_MIN_PRESENCE_CONFIDENCE` | `0.05` | Presence confidence at/below which an inferred component is dropped from the report (M1.9) |
| `MATERIAL_PROFILES_PATH` | `materials/data/materials.yaml` | Locator of the external material-profile catalogue (YAML/JSON), resolved against the `device_ai` package root when relative (M1.10) |
| `MATERIAL_MIN_CONFIDENCE` | `0.05` | Confidence at/below which an inferred material is dropped from the report (M1.10) |
| `ENVIRONMENTAL_FACTORS_PATH` | `environmental/data/factors.yaml` | Locator of the external conversion-factor catalogue (YAML/JSON), resolved against the `device_ai` package root when relative (M1.11) |
| `ENVIRONMENTAL_MIN_CONFIDENCE` | `0.05` | Confidence at/below which a recovered material is ignored when aggregating environmental savings (M1.11) |
| `DECISION_KNOWLEDGE_PATH` | `decision/data/knowledge.yaml` | Locator of the external decision-knowledge catalogue (YAML/JSON), resolved against the `device_ai` package root when relative (M2.1) |
| `DECISION_MIN_CONFIDENCE` | `0.05` | Confidence at/below which an upstream confidence source is dropped from the overall-confidence blend (M2.1) |
| `CIRCULAR_RULES_PATH` | `circular/data/rules.yaml` | Locator of the external circular-decision rule catalogue (YAML/JSON), resolved against the `device_ai` package root when relative (M2.2) |
| `CIRCULAR_MIN_CONFIDENCE` | `0.35` | Aggregated confidence at/below which a recommendation is flagged low-confidence with an operator warning; never changes the action (M2.2) |
| `PASSPORT_SCHEMA_PATH` | `passport/data/schema.yaml` | Locator of the external device-passport schema (YAML/JSON), resolved against the `device_ai` package root when relative; the strict validator checks every built passport against it (M2.3) |
| `PASSPORT_VERSION` | `1.0.0` | Semantic version stamped onto every produced device passport; bumped when the passport's structure changes (M2.3) |
| `INTEGRITY_RULES_PATH` | `integrity/data/rules.yaml` | Locator of the external passport validation rule-set (YAML/JSON), resolved against the `device_ai` package root when relative; the strict validator re-checks every passport against it before hashing (M2.4) |
| `INTEGRITY_HASH_ALGORITHM` | `sha256` | Hash algorithm for the canonical passport integrity hash; an unsupported value raises `PassportIntegrityError` (M2.4) |
| `TRUST_RULES_PATH` | `trust/data/rules.yaml` | Locator of the external trust catalogue (YAML/JSON), resolved against the `device_ai` package root when relative; holds the per-axis blend weights and the level thresholds behind a strict loader (M2.5) |
| `TRUST_MIN_SCORE` | `0.4` | Trust score at or below which a low-trust warning is flagged on the report; never changes the mapped trust level (M2.5) |
| `LIFECYCLE_RULES_PATH` | `lifecycle/data/transitions.yaml` | Locator of the external lifecycle transition-rules state machine (YAML/JSON), resolved against the `device_ai` package root when relative; the strict loader validates it (every event type declared once, ≥1 terminal event, known initial events) before the engine runs (M3.3) |
| `MAX_IMAGES` | `6` | Max images per request |
| `MAX_FILE_SIZE` | `10485760` | Max bytes per image (10 MB) |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `JSON_LOGS` | `false` | JSON logs when `true` |
| `MODEL_VERSION` | `1.0.0` | Version tag returned with predictions |
| `DUPLICATE_HAMMING_THRESHOLD` | `5` | Max perceptual-hash distance for a near-duplicate |
| `BLUR_THRESHOLD` | `100.0` | Variance-of-Laplacian below which an image is blurry |
| `BRIGHTNESS_DARK_THRESHOLD` | `40.0` | Mean luminance below which an image is too dark |
| `BRIGHTNESS_BRIGHT_THRESHOLD` | `220.0` | Mean luminance above which an image is too bright |
| `SPLIT_SEED` | `42` | Seed for deterministic dataset splitting |

## Running locally

Requires **Python 3.12+**.

```bash
cd intelligence/device_ai

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

# Run from the parent folder so `device_ai` is importable as a package:
cd ..
uvicorn device_ai.app:app --host 0.0.0.0 --port 8100 --reload
```

Then open `http://localhost:8100/docs`.

## Running with Docker

```bash
cd intelligence/device_ai

# Build & run
docker compose up --build

# Health check
curl http://localhost:8100/health
```

The image uses a slim Python 3.12 base, installs **only** the core runtime
dependencies, runs as a **non-root** user, and defines a container
**healthcheck** against `/health`.

## Testing

```bash
cd intelligence/device_ai
pip install -r requirements-dev.txt
pytest                      # from within device_ai/
# or, with coverage:
pytest --cov=device_ai --cov-report=term-missing
```

The suite covers the health/version endpoints, image validation (size,
MIME, corruption, count bounds), the predict endpoint contract and the
EcoID / pipeline units. The **M1.2** additions cover the dataset pipeline
end-to-end: perceptual hashing and duplicate detection, quality metrics,
YOLO annotation validation, deterministic splitting, augmentation, YOLO/COCO/VOC
export, statistics, versioning, reporting, and the six `/dataset/*` endpoints.
The **M1.3** additions cover the training platform: run-config validation and
Hydra-compatible composition, the `BaseTrainer` lifecycle (via a `MockTrainer`),
callbacks, pure-NumPy metrics, the JSON/Null experiment trackers (with the
MLflow import-guard), the model registry and artifact manager, the export
adapters' skip behaviour, the evaluation report, and the three CLIs — reaching
**99%** coverage on `device_ai/training`:

```bash
pytest tests --cov=device_ai.training --cov-report=term-missing
```

The **M1.4** additions cover the Device Detection Engine — all in the base
environment with injected fakes (no torch/ultralytics/GPU): the `YOLODetector`
parse/map/aggregate path, threshold filtering, the not-loaded guard and weight
resolution; the `YOLOTrainer.fit()` delegation, checkpoint copy, ONNX export
record, model-registry registration and the resume tag; the `DetectionEvaluator`
metric/confusion extraction and HTML rendering; and an **integration** test
asserting `/predict` returns the unchanged schema when driven by a real
`YOLODetector`.

The **M1.5** additions cover the Device Fingerprinting Engine — again entirely in
the base environment with injected fakes (no torch/open-clip): the similarity
metrics (identical → 1.0, orthogonal cosine → 0.5, symmetry, distance
monotonicity, unit-interval bounds); the hash-backed fingerprint
(determinism, canonical encoding, SHA-256 shape, EcoID format, `to_dict`/`from_dict`
round-trip); the `VerificationEngine` (`MATCH`/`NO_MATCH` around the threshold,
metric override, dimension-mismatch error); both repositories (round-trip,
`exists`, `list_ids`, JSON disk persistence, path-traversal rejection); the
`FingerprintService` (generate→persist→get, determinism, compare by EcoID); the
three `/fingerprint/*` endpoints (happy paths, 404, validation errors); the
`CLIPEncoder` not-ready degradation when the backend is absent; and a
backward-compatibility test asserting `/predict` is unchanged.

The **M1.6** additions cover the OCR Intelligence Engine — again entirely in the
base environment with injected fakes (no easyocr/opencv/torch): the pure pattern
matchers (IMEI Luhn accept/reject, MAC match/normalization, confusion
normalization on IDs only, manufacturer keyword table without false positives,
serial heuristic, label helpers); the domain models (`FieldType` order,
`to_dict`/`from_dict` round-trip, `OCRIdentity` projection); the `OCRParser`
(label-aware extraction, confidence combination/clamp, best-selection, barcode/QR
→ fields, embedded IMEI/serial mining); the `MockOCRBackend`/`MockBarcodeReader`
determinism and the `EasyOCRBackend`/`OpenCVBarcodeReader` not-ready guards with
injected `recognize_fn`/`decode_fn`; the `OCRService` (`extract` provenance
stamping, `parse`, `identity_for`); the three `/ocr/*` endpoints (happy paths,
validation reuse, out-of-range `422`); and backward-compatibility tests asserting
`/predict` is unchanged and the optional fingerprint-identity seam omits the
`identity` key when empty.

The **M1.7** additions cover the Multi-Modal Fusion Engine — entirely in the base
environment with directly constructed frozen result objects (no images, backends
or clock): the domain layer (`FusionAttribute` ordering, `Claim.key`
normalization, every `Evidence` builder mapping/placeholder-rejection, and the
`ResolvedAttribute`/`Conflict`/`DeviceContext` accessors, `to_dict` and
immutability) and the engine across all four required scenarios — **agreement**
(noisy-OR lifts `0.8`+`0.8` → `0.96`, three-module source union), **disagreement**
(conflict recorded, higher-confidence winner, support-share damping, the
device-type-vs-OCR-identity case), **partial evidence** (OCR-only;
detection+fingerprint without OCR; source-hash fallback/override) and **missing
evidence** (empty context) — plus mean-of-attributes confidence, unit-interval
bounds, declaration-order output, determinism, version/clock stamping and
provenance preservation.

The **M1.8** additions cover the Recoverability Intelligence Engine — entirely in
the base environment with hand-built frozen `DeviceContext`s (no images, models,
fusion run or filesystem; an injected clock makes `created_at` deterministic):
the device-profile table (canonical lookup, case/whitespace normalization,
synonym aliases, unknown fallback preserving the caller label, every score a
valid `[0, 1]` probability, aliases pointing at real keys, HIGH-hazard flags,
immutability); each of the seven rules in isolation (baseline seeding, identity
bonuses/penalty+warning, battery hazard floor + recycling penalty, CRT high
hazard forcing disposal, conflict/low-confidence confidence damping + forced
review, unknown-device forced review) plus the `RuleEngine` order, custom rule
set and determinism; the `ScoringEngine` fold (dimensions summed/clamped/rounded,
`0.1+0.2==0.3`, hazard max, confidence product/compounding) and **every** branch
of the recommended-action decision table (HIGH-hazard override beats forced
review, refurbish boundary inclusive, MANUAL_REVIEW fallthrough); and the
end-to-end `assess()` across identifiable / hazardous / conflicted /
low-confidence / partial-identity / unknown-device contexts with determinism,
provenance carry-over, JSON shape and report immutability.

The **M1.9** additions cover the Component Intelligence Engine — entirely in the
base environment with hand-built frozen `DeviceContext`s and `RecoverabilityReport`s
(no images, models or fusion run; an injected clock makes `created_at`
deterministic; only the profile/service tests read the shipped catalogue from
disk): the **external catalogue and its loader** (the shipped file's invariants —
every `base_likelihood` a valid `[0, 1]` probability, every category valid, every
alias pointing at a real profile — coverage parity with the recoverability
classes, normalized/alias-aware/unknown-fallback lookups, aggressive loader
validation against hand-written good/bad `tmp_path` catalogues (missing version,
empty profiles, unknown category, out-of-range/boolean likelihood, unknown
`implied_by`, dangling alias, missing `unknown`), JSON parity, and the
`from_settings` mapping); the **inference fold** against a small hand-built profile
(presence confidence from the prior, clamp/round, identity corroboration matching
vs. non-matching signals, hazard corroboration with `UNKNOWN` not corroborating,
the min-presence floor, the overall-confidence blend, unknown-type/conflict
damping, ordered reasoning/warnings); and the end-to-end `analyze()` across an
identifiable laptop, a hazardous CRT, an unknown device and a conflicted context,
plus determinism, provenance carry-over (engine/profile versions + injected
clock), JSON shape, report immutability and an injected custom library/config.

The **M1.10** additions cover the Material Intelligence Engine — again entirely in
the base environment with hand-built frozen `DeviceContext`s and, for the
inference tests, hand-built `RecoverabilityReport`s and `ComponentReport`s (no
images, models or fusion run; an injected clock makes `created_at` deterministic;
the profile/service tests build the two upstream reports by actually running the
recoverability and component engines, and read the shipped catalogue from disk):
the **external catalogue and its loader** (the shipped file's invariants — every
`mass_g` non-negative, every category a valid `MaterialCategory`, every
`source_components` entry a valid `ComponentCategory`, every alias pointing at a
real profile — coverage parity with the component device classes, hazardous
materials present for the CRT/battery profiles, normalized/alias-aware/unknown-
fallback lookups, aggressive loader validation against hand-written good/bad
`tmp_path` catalogues (missing file, malformed YAML, missing version, unknown
category, negative/non-numeric mass, bad source component, dangling alias, missing
`unknown` fallback, empty materials list), JSON parity, and the `from_settings`
mapping); the **inference fold** against a small hand-built profile (nominal-mass
passthrough independent of confidence, source-component gating dropping absent
materials, unconditional materials always present, strongest-source presence
driving confidence, the min-confidence floor, the overall-confidence blend,
unknown-type/conflict damping, recoverable/hazardous mass partitions, ordered
reasoning/warnings); and the end-to-end `analyze()` across an identifiable laptop
(materials + recoverable/hazardous weight > 0, no material more certain than the
overall estimate), a hazardous CRT surfacing leaded glass, an unknown device using
the generic fallback + warning, and a conflicted context, plus determinism,
provenance carry-over (engine/profile versions + injected clock), JSON shape,
report immutability, eco_id carry-over and an injected custom library/config.

The **M1.11** additions cover the Environmental Intelligence Engine — again
entirely in the base environment (no images, models or fusion run; only the
external catalogues are read from disk; the service tests build the four upstream
reports by actually running the recoverability, component and material engines):
the **external catalogue and its loader** (the shipped file's invariants —
non-negative factors, every `MaterialCategory` covered, critical categories
flagged, precious metal the largest carbon factor — the never-failing `factor_for`
fallback, aggressive loader validation against hand-written good/bad `tmp_path`
catalogues (missing file, malformed YAML, missing version, unknown category,
negative/non-numeric/boolean/missing factor, empty factors, missing default), JSON
parity, and the `from_settings` mapping); the **inference fold** against a small
hand-built factor library (mass→savings conversion, linear scaling, no-clamping of
physical metrics, per-category aggregation, default-factor fallback,
recoverable/floor filtering, landfill/critical quantities, circularity and
hazard-reduction indices, the separate confidence blend and that it never scales a
metric, reasoning/warnings, and every `HazardLevel`); and the end-to-end
`analyze()` across an identifiable laptop, a hazardous CRT, an unknown device and a
conflicted context, plus determinism, provenance/version stamping, the injected
clock, JSON shape and report immutability.

The **M2.1** additions cover the Decision Knowledge Engine — again entirely in the
base environment (no images, models or fusion run; only the external catalogues
are read from disk; the service tests build the five upstream reports by actually
running the recoverability, component, material and environmental engines): the
**external catalogue and its loader** (the shipped file's invariants — every
dimension defined, only canonical signals named, a positive weight per dimension,
strictly-positive saturation constants — `weights_for`, aggressive loader
validation against hand-written good/bad `tmp_path` catalogues (missing file,
malformed YAML, empty, missing version, missing normalization, non-positive
saturation, missing/unknown dimension, unknown signal, negative/boolean/all-zero
weight, unknown/all-zero/missing confidence), JSON parity, and the `from_settings`
mapping); the **inference fold** against a small hand-built knowledge base
(pass-through scores, the hazard-severity mapping for every level, environmental
saturation and clamping, mass fractions with the zero-mass guard, identity
completeness, the per-dimension weighted mean, the evidence breakdown, the
unit-interval invariant, the separate confidence blend with its floor and that it
never scales a score, reasoning/warnings, device-type resolution, provenance and
determinism); and the end-to-end `analyze()` across an identifiable laptop, a
hazardous CRT, an unknown device and a conflicted context, plus the
**normalized-evidence-only** invariant (no recommendation/monetary keys),
determinism, provenance/version stamping, the injected clock, JSON shape, report
immutability and injected knowledge/config.

The **M2.2** additions cover the Circular Decision Engine — **80** new tests,
again entirely offline (no images, models or fusion run; only the external
catalogues are read from disk; the service tests build the four upstream reports by
actually running the recoverability, component, material, environmental and
decision-knowledge engines): the **external catalogue and its loader**
(`test_circular_rules.py` — the shipped file's invariants (rules sorted by
precedence, unique ids and precedences, only canonical signals/operators named,
in-range thresholds, known actions/priorities, a valid default), the
condition/rule matching semantics (operator predicates, missing signal read as
`0.0`, conjunction), `to_dict` round-trips, aggressive loader validation against
hand-written good/bad `tmp_path` catalogues (missing file, malformed YAML, empty,
non-mapping root, missing version, no/non-list rules, missing default, a rule with
no conditions, unknown signal/operator/action/priority, out-of-range threshold,
negative/boolean precedence, boolean threshold, out-of-range confidence factor,
duplicate id, duplicate precedence, precedence sorting), and JSON parity); the
**deterministic evaluation** (`test_circular_engine.py` against a small hand-built
catalogue and hand-built reports — signal pass-through, the hazard-severity mapping
for every level, the upstream-force and conflict flags, identity completeness,
precedence (lowest wins), triggered-rule ordering, determinism, every action and
every priority reachable, the default fallback, confidence aggregation
(pass-through, compounding factors, action invariance), reasoning/warnings, and
provenance/device-type resolution); and the end-to-end `decide()`
(`test_circular_service.py` against the shipped catalogue — an identifiable laptop,
a hazardous CRT → `hazardous_disposal`/high, an unknown device → `manual_review`
and a conflicted context, plus the **no-monetary-field** invariant, determinism,
provenance/version stamping, the injected clock, JSON shape, report immutability,
at-most-one-winner, and injected config/catalogue / `from_settings` mapping).

The **M2.3** additions cover the Device Passport Core — **61** new tests, again
entirely offline (no images, models or fusion run; only the external schema is read
from disk; the service tests build the upstream reports by actually running the
recoverability, component, material, environmental, decision-knowledge and circular
engines): the **external schema and its loader/validator** (`test_passport_schema.py`
— the shipped file's invariants (version `1.0.0`, thirteen ordered sections, the
required section names, object sections carrying fields, the confidence-field range
contract), aggressive loader validation against hand-written malformed schemas
(missing file, empty, missing version, missing/empty sections, unknown kind, an
object section with a null or empty `fields` list, a confidence field absent from
its section's fields), a full conformant payload validating cleanly, and validator
rejections (missing section, wrong section kind, missing object field, out-of-range
and boolean confidence)); the **deterministic builder** (`test_passport_builder.py`
against hand-built upstream reports — identity/classification/decision/material/
environmental/fingerprint verbatim composition, the empty-fingerprint section +
warning, the **arithmetic-mean** overall confidence `(0.9+0.85+0.8+0.75)/4`, the
unit-interval bound, the content-addressed passport id (prefix + fixed length,
determinism, changes with the device identity, ignores the timestamp), metadata
provenance carry-over, the passport-version config fallback, the composed reasoning
lead line, the de-duplicated warnings union, the reasoning/warnings caps, canonical
sorted-compact JSON, the **no-monetary-field** invariant and immutability); and the
end-to-end `build()` (`test_passport_service.py` running the real upstream engines —
an identifiable laptop passport, **schema re-validation** of the serialized form,
the default-schema load (thirteen sections), a no-fingerprint passport, version and
injected-clock stamping, determinism across service instances, a stable passport id
across instances, the confidence bound, a conflicted context, injected config and
the `from_settings` mapping, plus the **no-monetary-field** invariant and
immutability).

The **M2.4** additions cover the Device Passport Validation & Integrity Engine —
**51** new tests, again entirely offline (no images, models or fusion run; only the
external rule-set is read from disk; the service tests build a passport by actually
running the recoverability, component, material, environmental, decision-knowledge,
circular and passport engines): the **external rule-set and its loader**
(`test_integrity_rules.py` — the shipped file's invariants (version `1.0.0`,
thirteen sections, the required section names, `fingerprint_summary` optional,
object sections carrying fields, the confidence-field declarations), aggressive
loader validation against hand-written malformed rule-sets (missing file, empty,
missing version, missing/empty sections, unknown kind, an object section with a null
or empty `fields` list, a confidence field absent from its section's fields, a
string section carrying fields, a non-boolean `required`, a duplicate field), JSON
parity, and the `SectionRule.to_dict` / `SectionKind.values` value objects); the
**unit-level validator** (`test_integrity_validator.py` against hand-built passports
and hand-built rule-sets — the happy path (valid, hashed), all three verdict states
(valid / valid-with-warnings / invalid), every structural-error kind (missing
required section, wrong kind, non-mapping object, missing object field,
out-of-range and boolean confidence), the optional-section warning, error ordering
and de-duplication, the SHA-256 hash (fixed-length hex, determinism, tamper
detection, present even for an invalid passport) and the unsupported-algorithm
engine fault); and the end-to-end `validate()` (`test_integrity_service.py` running
the real upstream engines — a well-formed passport validating as valid with a
64-hex hash and thirteen checked sections, the default rule-set load, a
no-fingerprint passport still valid, version and injected-clock stamping,
determinism and a stable hash across service instances, tamper detection, the
`sha512` override producing a 128-char digest, the `from_settings` mapping, plus the
**no-monetary-field** invariant and immutability).

The **M2.5** additions cover the Trust & Provenance Engine — **73** new tests,
again entirely offline (no images, models or fusion run; only the external
catalogue is read from disk; the service tests build the four inputs by actually
running the recoverability, component, material, environmental, decision-knowledge,
circular, passport and integrity engines): the **external catalogue and its loader**
(`test_trust_rules.py` — the shipped file's invariants (version `1.0.0`, all four
axes weighted in canonical order with a positive total, the four levels sorted by
descending floor with a `0.0` floor), the `level_for` mapping and inclusive floors,
aggressive loader validation against hand-written malformed catalogues (missing
file, empty, non-mapping root, missing version, missing/empty weights, unknown/
missing axis, negative/all-zero/boolean weight, missing/empty levels, unknown/
duplicate/missing level, no-`0.0`-floor, out-of-range floor, JSON parity,
unparseable YAML), and the `AxisWeight` / `TrustLevelRule` value objects); the
**deterministic engine** (`test_trust_engine.py` against hand-built reports and a
hand-built catalogue — each axis in isolation (identity completeness full/half/
empty, evidence agreement/conflict/disagreement/undefined, decision mean, integrity
valid/invalid/warnings-damped), the weighted-average score, weight biasing, the
invalid→untrusted path, clamping/rounding, the ordered reasoning covering every
axis and the four warning kinds (low-trust, invalid-integrity, integrity-warnings,
passport-warnings), and determinism); and the end-to-end `assess()`
(`test_trust_service.py` against the shipped catalogue running the real upstream
engines — a well-formed passport scoring into a valid report with four ordered
axes, the default catalogue load, provenance/version stamping, the injected clock,
determinism, score stability across service instances, injected config /
`from_settings` mapping, a raised floor flagging a low-trust warning, plus the
**no-monetary-field** invariant, immutability and JSON round-tripping).

The **M3.1** additions cover the Blockchain Ledger Core — **60** new tests, again
entirely offline (no images, models or fusion run; only the external config is
read from disk; the service tests build the three inputs by actually running the
recoverability, component, material, environmental, decision-knowledge, circular,
passport, integrity and trust engines): the **four frozen value objects**
(`test_ledger_models.py` — fixed `to_dict` key order and values, `created_at`/
`timestamp` `None` serialization, canonical sorted-compact `to_json`, the `Block`
convenience properties delegating to the header, the nested `Block`/`Blockchain`
serialization, immutability and the **no networking/consensus/monetary surface**
invariant); the **external config and its loader** (`test_ledger_config.py` — the
shipped file loading and validating, defaults matching the module constants,
relative/absolute path resolution, custom YAML/JSON loading with default fallback,
aggressive loader validation against hand-written malformed files (missing file,
empty, non-mapping root, missing version, unsupported/empty hash algorithm,
non-hex genesis) and the `from_settings` mapping); the **deterministic builder**
(`test_ledger_builder.py` against hand-built reports — record/block/chain
creation, the genesis sentinel, previous-hash linking (the computed hash of the
prior header), deterministic record hashing, distinct records hashing differently,
empty/single/three-block chain validation, tamper detection (wrong index, mutated
record, broken previous link), the unsupported-algorithm engine fault, a
`sha3_256` alternate, and determinism (byte-identical chains, canonical JSON));
and the end-to-end service (`test_ledger_service.py` against the shipped config
running the real upstream engines — record creation from real artefacts,
`genesis`/`append`/`append_record`/`build_chain`, intact-chain verification and
tamper detection, determinism across service instances, the injected clock, the
default config load, plus the **no networking/consensus/monetary surface**
invariant and immutability).

The **M3.2** additions cover the Ledger Backend Abstraction Layer — **29** new
tests, again entirely offline (a `_sample_artifacts` helper hand-crafts the
passport/integrity/trust inputs, so no upstream engines run). A single **shared
backend contract** (`test_ledger_backend.py`) runs against **all three**
implementations via a parametrized fixture — `@runtime_checkable` protocol
satisfaction (`isinstance`), write/read round-trip, `read` returning `None` for an
unknown id, `exists`, `list_ids`, overwrite (last-write-wins) and the receipt's
`chain_id`/`backend` — alongside per-backend metadata checks (memory `block_count`;
Fabric `tx_id`/`channel`/`block_number` and its monotonic transaction counter;
Ethereum `tx_hash`/`nonce`/`gas_used`/`contract`, the advancing nonce and the
**deterministic** content-addressed `tx_hash`) and the service-level
`save`/`load`/`exists`/`list_ids` driving an injected backend. Together M3.1 + M3.2
add **89** ledger tests, all passing.

The **M3.3** additions cover the Device Lifecycle Ledger Engine — **68** new
tests across four modules, all offline (no images, models or upstream engines run;
only the external rules file is read from disk): the **three value objects**
(`test_lifecycle_models.py` — the event-type wire values and `values()` ordering,
fixed `to_dict` key order and values, `occurred_at`/`created_at` `None`
serialization, canonical sorted-compact `to_json`, the `is_empty`/`event_types`
properties, immutability and the **no GPS/networking/streaming surface**
invariant); the **strict rules loader** (`test_lifecycle_rules.py` — the shipped
rules loading and validating, every event type declared once in canonical order,
the `registered` initial and `disposed` terminal events, expected transitions, a
JSON round-trip, ~18 malformed-rules rejection cases (missing/empty/non-mapping,
missing version/transitions/initial_events, incomplete transitions, unknown
key/target, self-transition, duplicate target, no terminal event,
empty/duplicate/unknown initial events, non-list targets), the typed error's
`code`/`path` and the `LifecycleTransition` helpers); the **deterministic engine**
(`test_lifecycle_engine.py` against a hand-built rule set — `validate` over
empty/genesis/non-initial/linear/illegal/post-terminal/refurbish-loop sequences,
`build_record` provenance stamping and invalid-path-is-data, and `can_append`);
and the **injectable service** (`test_lifecycle_service.py` against the shipped
rules — config resolution, default rule-loading and injected ledger, the
clock-stamped/clockless `event` factory, `build`/`append`/`can_append`, clockless
determinism, append not mutating the original, and **ledger integration through
the backend abstraction** — reporting absence for unknown ids and seeing a chain
anchored via a `MockEthereumLedgerBackend`). Together M3.1 + M3.2 + M3.3 add
**157** ledger/lifecycle tests, all passing.

## Code quality

```bash
black .        # formatting
isort .        # import ordering
ruff check .   # linting (google docstrings, type-annotation rules)
mypy device_ai # static typing
```

Standards (`docs/engineering/08_AI.md`): strict typing, Google docstrings,
Black formatting, structured logging, no hardcoded model paths, no globals,
dependency injection where appropriate.

## Future integration points

Each mock is a drop-in behind an abstract interface in
`inference/predictor.py`. To integrate a real model:

1. Implement the relevant interface (`Detector`, `ConditionAssessor`,
   `OCREngine`, `MaterialEstimator`, `EmbeddingEncoder`) with a real adapter
   that loads its artifact via `ModelRegistry` (no hardcoded paths).
2. Register it in `inference/pipeline.py` (replace `build_mock_pipeline`
   with a real-model factory) — the API and pipeline are unchanged.
3. Add a `BaseTrainer` subclass under `training/` and register it in the
   `TrainerRegistry` (implement only the five model-specific hooks); the M1.3
   platform provides tracking, checkpointing, registration, evaluation and
   export for free.
4. Install `requirements-models.txt` and mount artifacts into `MODEL_DIR`.

| Interface | Mock | Real model |
|---|---|---|
| `Detector` | `MockDetector` | **YOLOv8 (Ultralytics) — shipped in M1.4** ✅ |
| `EmbeddingEncoder` | `MockEmbeddingEncoder` | **OpenCLIP — shipped in M1.5** ✅ |
| `OCREngine` | `MockOCREngine` | **EasyOCR — shipped in M1.6** ✅ (standalone `/ocr/*` engine; `/predict`'s mock stays frozen) |
| `ConditionAssessor` | `MockConditionAssessor` | OpenCV features + classifier |
| `MaterialEstimator` | `MockMaterialEstimator` | **Deterministic material engine — shipped in M1.10** ✅ (standalone internal `materials/` engine; `/predict`'s mock stays frozen) |
| `ConditionAssessor` | `MockConditionAssessor` | OpenCV features + classifier |

> Beyond the `/predict` interfaces above, milestones **M1.11** (Environmental
> Intelligence Engine), **M2.1** (Decision Knowledge Engine), **M2.2** (Circular
> Decision Engine), **M2.3** (Device Passport Core), **M2.4** (Device Passport
> Validation & Integrity Engine), **M2.5** (Trust & Provenance Engine) and
> **M3.1** (Blockchain Ledger Core) ship as standalone internal `environmental/`,
> `decision/`, `circular/`, `passport/`, `integrity/`, `trust/` and `ledger/`
> libraries consumed directly in-process — they add no interface to `/predict`,
> whose mock pipeline stays frozen.

## Roadmap

- **M1.1** — microservice skeleton, validation pipeline,
  deterministic mocks, tests, Docker. ✅
- **M1.2** — dataset intelligence pipeline: import, hashing,
  quality metrics, duplicate detection, annotation validation, augmentation,
  splitting, YOLO/COCO/VOC export, statistics, versioning, reporting. ✅
- **M1.3** — AI training & MLOps platform: typed run config
  (Hydra-compatible), abstract `BaseTrainer` lifecycle, callbacks, pure-NumPy
  metrics, evaluation reports, PyTorch/TorchScript/ONNX export adapters,
  pluggable experiment tracking (JSON/MLflow), JSON model registry, and
  `train`/`evaluate`/`export` CLIs. No model trained. ✅
- **M1.4** — real **YOLO detector** on the M1.3 platform:
  `YOLODetector` behind the unchanged `Detector` interface (guarded real/mock
  swap), `YOLOTrainer` delegating to Ultralytics (resume, early stopping,
  checkpointing, MLflow, ONNX export), `DetectionEvaluator` (mAP/precision/
  recall/F1, confusion matrix, JSON + HTML report). `/predict` contract
  unchanged — only device type/confidence/bbox are real. ✅
- **M1.5** — **Device Fingerprinting Engine**: pluggable
  **OpenCLIP** encoder (guarded real/mock swap), L2-normalized embeddings,
  hash-backed **EcoTrace Fingerprints**, configurable similarity metrics
  (cosine/euclidean/manhattan), a match/no-match **Verification Engine**, a
  storage-agnostic fingerprint repository (memory/JSON), and three
  `/fingerprint/*` endpoints. `/predict` contract unchanged. ✅
- **M1.6** — **OCR Intelligence Engine**: a pluggable
  **EasyOCR** text backend and **OpenCV** QR/barcode reader (guarded real/mock
  swap) feeding a pure **normalization/parser layer** that extracts
  confidence-scored identity fields (manufacturer, model, serial, IMEI, MAC, QR,
  barcode) with IMEI **Luhn** validation and OCR-confusion normalization; three
  `/ocr/*` endpoints; an **optional, backward-compatible** identity seam into the
  M1.5 fingerprint engine. `/predict` contract unchanged. ✅
- **M1.7** — **Multi-Modal Fusion Engine**: an internal-only
  engine that merges the detector, fingerprint and OCR outputs onto a shared
  **attribute space** and produces a single, normalized, **immutable**
  `DeviceContext` — aggregating confidence across heterogeneous evidence
  (**noisy-OR** agreement + **support-share** damping), detecting **conflicts**
  between modules (e.g. detected device type vs. OCR identity) with deterministic
  winner selection, and preserving full per-module provenance for downstream AI.
  No new endpoint; `/predict` contract unchanged. ✅
- **M1.8** — **Recoverability Intelligence Engine**: an
  internal-only, deterministic rule engine that consumes the fusion engine's
  immutable `DeviceContext` and produces an explainable `RecoverabilityReport`
  (repairability / reusability / recyclability, hazard level, aggregated
  confidence, recommended end-of-life action, ordered reasoning + warnings) from
  device-type profiles + identity completeness + hazard heuristics + fusion
  confidence. Modular rules, pure scoring, explicit decision table, all
  thresholds configurable. No new endpoint; `/predict` contract unchanged. ✅
- **M1.9** — **Component Intelligence Engine**: an internal-only,
  deterministic inference engine that consumes the fusion engine's immutable
  `DeviceContext` and the recoverability engine's `RecoverabilityReport` and
  produces an explainable `ComponentReport` — the likely internal electronic
  components of the device (each with a presence confidence), a single overall
  confidence, and ordered reasoning + warnings — inferring from device type + OCR
  identity + recoverability hazard + **versioned component profiles stored in an
  external YAML/JSON catalogue**. Priors + bounded corroboration, a strict
  validating loader, all weights configurable. No new endpoint; `/predict`
  contract unchanged. ✅
- **M1.10** — **Material Intelligence Engine**: an internal-only,
  deterministic inference engine that consumes the fusion engine's immutable
  `DeviceContext`, the recoverability engine's `RecoverabilityReport` and the
  component engine's `ComponentReport` and produces an explainable `MaterialReport`
  — the recoverable and hazardous materials the device is made of (each with an
  estimated mass, a confidence and its source components), device-level total /
  recoverable / hazardous weight totals, a single overall confidence, and ordered
  reasoning + warnings — inferring from the component inventory + **versioned
  material profiles stored in an external YAML/JSON catalogue** + recoverability and
  device confidence. Source-gated inclusion, nominal mass with independently derived
  confidence, a strict validating loader, all weights configurable. No new endpoint;
  `/predict` contract unchanged. ✅
- **M1.11** — **Environmental Intelligence Engine**: an internal-only,
  deterministic engine that consumes the fusion engine's `DeviceContext`, the
  recoverability, component and material reports and produces an explainable
  `EnvironmentalImpactReport` — avoided **carbon** (kg CO₂e), **energy** (MJ) and
  **water** (L) savings from recovering each material, device-level totals, a
  single overall confidence, and ordered reasoning + warnings — from
  **versioned conversion factors stored in an external YAML/JSON catalogue** with
  a strict validating loader. No new endpoint; `/predict` contract unchanged. ✅
- **M2.1** — **Decision Knowledge Engine**: an internal-only,
  deterministic engine that consumes all five upstream artefacts (`DeviceContext`
  plus the recoverability, component, material and environmental reports) and
  produces a single, normalized `DecisionKnowledgeReport` — six `[0, 1]` evidence
  dimensions (repairability, reusability, recycling, hazard, environmental
  priority, material value), a **separately blended** overall confidence, and
  ordered reasoning + warnings — by projecting the upstream reports onto eleven
  canonical signals and blending them with **catalogue-driven weights** from an
  external YAML/JSON knowledge base behind a strict validating loader. It computes
  **normalized evidence only** — no recommended action, no economic/monetary
  valuation, no optimization. No new endpoint; `/predict` contract unchanged. ✅
- **M2.2** — **Circular Decision Engine**: an internal-only,
  deterministic rule-evaluation engine that consumes four upstream artefacts
  (`DeviceContext`, `DecisionKnowledgeReport`, `RecoverabilityReport`,
  `EnvironmentalImpactReport`) and produces the pipeline's **first actionable
  recommendation**, a `DecisionReport` — a recommended **end-of-life action**
  (reusing the recoverability engine's `RecommendedAction`), a triage **priority**,
  an aggregated **confidence**, the **rules that fired** (explicit precedence,
  winner flagged) and ordered reasoning + warnings — by projecting the reports onto
  sixteen canonical signals and matching them against a **precedence-ordered,
  catalogue-driven** rule set from an external YAML/JSON catalogue behind a strict
  validating loader. **Deterministic, auditable**, with confidence on a separate
  axis; **no economic/monetary valuation, no optimization**. No new endpoint;
  `/predict` contract unchanged. ✅
- **M2.3** — **Device Passport Core**: an internal-only,
  deterministic **assembler** that consumes five upstream artefacts
  (`DeviceContext`, `DecisionReport`, `MaterialReport`, `EnvironmentalImpactReport`,
  `DeviceFingerprint`) and **composes** them into a single, immutable
  `DevicePassport` — a content-addressed **passport id**, a stamped **passport
  version** and **EcoID**, device **identity** and **classification**, condensed
  **decision / material / environmental / fingerprint** summaries, a transparent
  **confidence summary** (the overall value the plain **arithmetic mean** of the
  upstream confidences), provenance **metadata**, and ordered reasoning + warnings.
  It **composes existing reports — it never re-scores or re-recommends**; the
  passport's **structure** lives in an external, versioned YAML **schema** behind a
  **strict validator**, and every passport serializes to **deterministic, canonical
  JSON**. **No** blockchain, QR, CBOR, digital signatures, ownership history,
  lifecycle events or persistence. No new endpoint; `/predict` contract unchanged. ✅
- **M2.4** — **Device Passport Validation & Integrity
  Engine**: an internal-only, deterministic **checker** that consumes the M2.3
  `DevicePassport` and produces a single, immutable `PassportIntegrityReport` — a
  **validation status** (valid / valid-with-warnings / invalid), a deterministic
  **SHA-256 canonical integrity hash**, the observed **schema** and **passport**
  versions, ordered **checked sections** (kind / present / valid) and ordered
  **warnings** + **errors** — by **re-validating** the passport against a
  **catalogue-driven** validation rule-set from an external YAML/JSON file behind a
  **strict loader**, then hashing the passport's **canonical serialization** so any
  later mutation is detectable. The trust boundary is **inverted** from the
  assembler: a malformed **rule-set** is **raised**, a malformed **passport** is
  **reported**. It **re-checks and hashes — it never re-scores, re-recommends or
  mutates the passport**. **No** blockchain, digital signatures, QR, CBOR, ownership
  history, lifecycle events or persistence. No new endpoint; `/predict` contract
  unchanged. ✅
- **M2.5** — **Trust & Provenance Engine**: an
  internal-only, deterministic **trust evaluator** that consumes the four upstream
  artefacts (`DevicePassport`, `PassportIntegrityReport`, `DecisionKnowledgeReport`,
  `DecisionReport`) and produces a single, immutable `PassportTrustReport` — a
  normalized **trust score** (`[0, 1]` weighted average), a mapped **trust level**
  (high / medium / low / untrusted), four transparent sub-axes (**identity
  confidence**, **evidence consistency**, **decision confidence**, **integrity
  confidence**) and ordered **reasoning** + **warnings** — by **projecting** the
  existing confidence and consistency signals its inputs already carry onto the four
  axes and **blending** them with **catalogue-driven weights** from an external
  YAML/JSON catalogue behind a **strict loader**, then mapping the score to a level
  via the catalogue's thresholds. It **grades an existing verdict — it carries no
  inference and no evidence of its own**; a malformed **catalogue** is **raised**, a
  low-trust **input** is **reported**. **No** blockchain, smart contracts, digital
  signatures, QR, wallets, ownership history, marketplace, carbon credits or
  persistence. No new endpoint; `/predict` contract unchanged. ✅
- **M3.1** — **Blockchain Ledger Core**: an
  internal-only, deterministic **immutable-ledger builder** that consumes the
  three upstream artefacts (`DevicePassport`, `PassportIntegrityReport`,
  `PassportTrustReport`) and produces a tamper-evident **`Blockchain`** — an
  ordered chain of **`Block`** objects, each carrying one **`LedgerRecord`**
  payload and one **`BlockHeader`** that links it to the previous block via
  deterministic SHA-256 hash-chaining. Each record snapshots the passport id +
  version (M2.3), the canonical integrity hash + engine version (M2.4), and the
  trust score + level + engine version (M2.5). Each block's `previous_hash` is the
  SHA-256 digest of the prior block's header (or a genesis sentinel of 64 zeros
  for the first block) and its `record_hash` is the SHA-256 digest of its own
  record, so any later mutation of a block's contents or the chain's order breaks
  the recomputed hashes and is detected on verification. The core's operational
  knobs (hash algorithm, versions, genesis sentinel) live in an **external,
  versioned** YAML/JSON file behind a **strict loader** that fails with a typed
  `LedgerConfigError` on any structural problem. A malformed **config** or an
  unsupported hash algorithm (engine faults) *raise*; a mutated block or re-ordered
  chain is *reported* as `is_valid == False`. **The chain is built by local
  hash-chaining alone** — **no** Hyperledger Fabric, Ethereum, consensus,
  proof-of-work, smart contracts, wallets, digital signatures, REST endpoints,
  networking or persistence. The future Hyperledger Fabric backend in
  `docs/engineering/09_BLOCKCHAIN.md` is a **separate** concern that can later
  anchor these hashes. No new endpoint; `/predict` contract unchanged. ✅
- **M3.2 (this milestone)** — **Ledger Backend Abstraction Layer**: a
  technology-agnostic **`LedgerBackend`** protocol (`@runtime_checkable`;
  `write`/`read`/`exists`/`list_ids`) and three deterministic, in-memory
  implementations — **`MemoryLedgerBackend`**, **`MockFabricLedgerBackend`**,
  **`MockEthereumLedgerBackend`** — that let the **`LedgerService`** persist chains
  through an *injected* backend, depending only on the protocol, so the ledger
  technology can change without touching the domain or service. The service owns
  chain **identity** (a content-addressed `chain_id` derived from the genesis
  block), so each backend is a pure key-value store; every `write` returns a
  **`LedgerReceipt`** (`chain_id`, `backend`, `metadata`) with the two mocks
  emitting Fabric-/Ethereum-*shaped* metadata (transaction id/channel/block number;
  content-addressed tx hash/nonce/gas/contract). **Still no** real Fabric SDK,
  chaincode, certificates, consensus, Ethereum RPC, smart contracts, wallets,
  digital signatures, networking or persistence — the mocks prove the abstraction,
  not wire behaviour. Purely additive over M3.1 (`backend=` is keyword-only with a
  `MemoryLedgerBackend` default); no new env vars, no new error types; no new
  endpoint; `/predict` contract unchanged. ✅
- **M3.3 (this milestone)** — **Device Lifecycle Ledger Engine**: an
  internal-only, deterministic **device-history builder** that models the complete
  lifecycle of a device as an ordered sequence of immutable **`LifecycleEvent`**
  objects and validates that ordering against an **external, versioned state
  machine** (`LifecycleRuleSet`, loaded from `lifecycle/data/transitions.yaml`
  behind a strict loader), composing the result into an immutable
  **`LifecycleRecord`** (device id, ordered events, validity verdict, current
  state, provenance). The shipped rules encode an e-waste lifecycle — `registered`
  initial, `disposed` terminal, a fork at `assessed` (refurbish/recycle/dispose)
  and a legal `refurbished → in_use` loop. The stateless **`LifecycleEngine`**
  (`validate` / `build_record` / `can_append`) reports an illegal ordering as
  `is_valid == False` — never raised; only a malformed **rules file** *raises* a
  typed **`LifecycleRuleError`**. The injectable **`LifecycleService`** stamps
  provenance and correlates a history with an anchored passport chain **through the
  injected `LedgerService`** (`is_anchored`/`anchored_chain`/`anchored_ids`),
  depending only on the M3.2 `LedgerBackend` abstraction — never a concrete store.
  **No** Hyperledger Fabric, chaincode, smart contracts, REST endpoints,
  networking, GPS tracking, event streaming, QR scanning, wallets or digital
  signatures. Purely additive; one new env knob (`LIFECYCLE_RULES_PATH`); no new
  endpoint; `/predict` contract unchanged. ✅
- **M3.4+ (future)** — economic valuation on top of the M2.2 recommendation;
  a *real* Hyperledger Fabric / Ethereum backend behind the M3.2 `LedgerBackend`
  protocol, anchoring the M3.1 ledger chain and the M3.3 lifecycle history;
  digital signatures over the M2.3 passport, its M2.4 integrity hash and its M2.5
  trust report; QR/CBOR passport encodings; ownership history and persistence;
  marketplace, carbon-credit and fleet-analytics integration.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See top-level `PROJECT.md`,
`CLAUDE.md`, `AGENTS.md` and `docs/engineering/` for platform-wide standards._
