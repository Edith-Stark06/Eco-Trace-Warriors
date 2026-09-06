# EcoTrace India — Device Intelligence Engine (DIE)

> AI microservice for e-waste **device intelligence**: turn device photos
> into structured data (device type, brand, condition, recoverable
> materials, carbon score) behind a clean REST API.

**Module:** `intelligence/device_ai`
**Status:** Finalization (post-P9). Production checkpoint is **frozen**
(`docker_data/device_ai/models/best.pt`, SHA256
`c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92`) and ML
experimentation is closed — see `docs/FINAL_PROJECT_STATUS.md` for current
project-wide status. The milestone history below (M1.4–M1.10) describes how
this service's architecture was built and remains accurate for that purpose.

**Milestone history — M1.10** — **Material Intelligence Engine**: an
internal-only, deterministic inference engine that consumes the fusion engine's
(M1.7) immutable `DeviceContext`, the recoverability engine's (M1.8)
`RecoverabilityReport` and the component engine's (M1.9) `ComponentReport` and
produces an explainable `MaterialReport` — the recoverable and hazardous
materials the device is made of, each with an estimated mass and confidence plus
the source components it derives from, and device-level recoverable / hazardous
weight totals with ordered human-readable reasoning and warnings — inferring from
the component inventory + versioned material profiles + recoverability and device
confidence, with the material knowledge stored in an **external, versioned**
YAML/JSON catalogue. It ships **no new endpoint** and leaves the `/predict` API
contract **unchanged and backward-compatible**. (Built on M1.9 — a component
inference engine; M1.8 — a recoverability rule engine; M1.7 — a multi-modal
fusion engine; M1.6 — an OCR intelligence engine; M1.5 — an OpenCLIP fingerprint
engine; and M1.4 — a real Ultralytics YOLO detector.)
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
16. [Configuration](#configuration)
17. [Running locally](#running-locally)
18. [Running with Docker](#running-with-docker)
19. [Testing](#testing)
20. [Code quality](#code-quality)
21. [Future integration points](#future-integration-points)
22. [Roadmap](#roadmap)

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
- **M1.10 (this milestone)** — **Material Intelligence Engine**: an internal-only,
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
- **M1.11** — carbon estimation; the Digital Device Passport; market-value
  estimation; blockchain-anchored lifecycle records.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See top-level `PROJECT.md`,
`CLAUDE.md`, `AGENTS.md` and `docs/engineering/` for platform-wide standards._
