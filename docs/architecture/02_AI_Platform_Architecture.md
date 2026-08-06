# 02. AI Platform Architecture

**Document Version:** 1.0  
**Status:** Active  
**Last Updated:** 2026-08-06  
**Target Audience:** IEEE YESIST 2026 Reviewers, Enterprise Architects, Research Engineers, Patent Reviewers

---

## Executive Summary

The **Device Intelligence Engine (DIE)** is a production-grade, modular AI platform built as an independent Python 3.14 / FastAPI microservice. It orchestrates computer-vision models (YOLOv8 object detection, OpenCLIP visual embeddings, EasyOCR text extraction), fusion engines (material estimation, condition assessment, environmental impact scoring), and a complete MLOps pipeline (training, evaluation, export, versioning) to power the EcoTrace India e-waste lifecycle management system.

**Key Architectural Principles:**

1. **Mock-vs-Real Model Swapping:** Every inference component implements a stable abstract interface. Mock implementations ship by default (deterministic, no dependencies, zero-weight). Real models (YOLO, CLIP, OCR) are loaded behind the same interface when their optional dependencies resolve, so the `/predict` contract and API response schema remain byte-compatible across the mock → real transition.

2. **Dependency Injection Everywhere:** Settings, models, registries, experiment trackers, clocks and Git commits are constructor-injected. No module reads `os.environ` outside `Settings`. No hardcoded paths. Tests inject fakes; production wires singletons.

3. **Honest Degradation:** Missing artifacts or uninstalled backends (`ultralytics`, `open-clip-torch`, `easyocr`, `torch`, `onnx`) leave components "not ready" rather than raising. The service degrades to mocks with logged warnings, never silently pretending a model ran.

---

## 2. AI Platform Overview

The Device Intelligence Engine (DIE) is a **standalone FastAPI microservice** at `intelligence/device_ai`, independent of the backend REST API, PostgreSQL, blockchain and passport layers. It exposes a single frozen public contract (`POST /predict`) and three internal-only services (dataset pipeline, training CLI, evaluation CLI) that never touch the HTTP surface.

**Core Responsibilities:**

- **Inference:** YOLOv8 object detection → device type, brand, bounding boxes  
- **Visual Embedding:** OpenCLIP ViT-B/32 → 512-dim normalized feature vector  
- **Text Extraction:** EasyOCR + OpenCV barcode reader → serial numbers, model IDs  
- **Material Estimation:** Per-device-type composition (aluminum, copper, PCB, battery, plastic)  
- **Condition Assessment:** Physical wear classification (Excellent/Good/Fair/Poor)  
- **Carbon Scoring:** Derived metric: `base(50) + condition_weight × material_value`, clamped [0,100]  
- **EcoID Generation:** Unique public identifier `ET-YYYY-XXXXXXXX` (UUID-backed or sequential)  
- **Dataset Intelligence:** Import, duplicate detection, YOLO annotation validation, train/val/test splitting, augmentation, export (YOLO/COCO/Pascal VOC), quality reports  
- **Training Orchestration:** Abstract `BaseTrainer` lifecycle (seeding, epoch loop, callbacks, checkpointing, auto-registration), model registry, experiment tracking (JSON/MLflow), artifact management  
- **Evaluation & Export:** Confusion matrices, classification metrics (accuracy/precision/recall/F1/mAP), PyTorch/TorchScript/ONNX export with honest backend-unavailable skips

**Out of Scope (Documented Elsewhere):**
- Web frontend (React dashboard)
- Backend REST APIs (`/api/v1/...` — Node.js/Express)
- PostgreSQL persistence
- Blockchain ledger (Hyperledger Fabric, milestone M3.1)
- Digital Passport engine (M2.x)
- Trust catalogue (M2.5)
- Lifecycle state machine (M3.3)
- Decision Intelligence (circular economy scoring, M2.4)

---

## 3. AI Design Philosophy

**1. Models Are Advisory, Not Authoritative**  
The AI platform performs inference and produces predictions; it does not enforce business rules or lifecycle state transitions. Detection confidence, condition scores, and material estimates are advisory inputs consumed by the backend's decision engine (M2.4) and lifecycle orchestrator (M3.3). The platform never rejects a request because a device type is "unknown" or a confidence is "too low" — it returns what it computed, and the backend decides what to do with it.

**2. No Business Logic Inside Models**  
Models answer "what is this?" — never "what should I do about it?" The YOLO detector returns bounding boxes and class labels. The condition assessor returns a wear classification. The material estimator returns fractional compositions. The platform composes these into a `PredictionResult`, but it does not decide whether the device is "recyclable" or compute a "trust score" — those are business rules implemented in the passport/trust engines.

**3. Preprocessing Is Separate**  
Image validation, decoding, resizing, normalization, and augmentation live in `preprocessing/`, not inside model wrappers. Every model adapter receives already-validated `LoadedImage` objects (decoded Pillow images with cached metadata). Tests can inject fake images without touching PIL; production wires the real validator.

**4. Model Artifact Locations Come From Configuration**  
No module hardcodes `/models/yolo.pt`. The `Settings` object (Pydantic `BaseSettings`, parsed once at startup from `.env`) declares `detector_weights`, `clip_weights`, `ocr_weights` — all resolved relative to `MODEL_DIR`. Adapters receive these paths via dependency injection. Tests override settings; production points at real artifacts.

**5. Each Component Is Independently Testable**  
Every inference component (Detector, ConditionAssessor, OCREngine, MaterialEstimator, EmbeddingEncoder) implements an abstract protocol with a single public method (`detect`, `assess`, `extract`, `estimate`, `embed`). Mock implementations ship deterministic outputs derived from input content hashes. Real adapters load weights conditionally. The pipeline composes components via keyword-only constructor injection, so tests wire all-mocks, all-real, or any mix without touching the API.

---

## 4. Layered Architecture

The AI platform is organized into **five conceptual layers**, from HTTP transport down to persistence:

```
┌─────────────────────────────────────────────────────────────┐
│  API Layer (FastAPI routes, schemas, middleware, errors)   │
│  • GET  /  /health  /version                                │
│  • POST /predict (frozen contract)                          │
│  • Three internal routers: /dataset, /fingerprint, /ocr     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Service Layer (orchestration facades)                      │
│  • PredictionPipeline (inference orchestration)             │
│  • DatasetService (import → split → augment → export)       │
│  • FingerprintService (CLIP + similarity + dedup)           │
│  • OCRService (EasyOCR + barcode + parser)                  │
│  • LifecycleService (OUT OF SCOPE — M3.3, see §2)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Inference Engines (model adapters + fusion)                │
│  • Detector (Mock / YOLODetector)                           │
│  • ConditionAssessor (Mock)                                 │
│  • OCREngine (Mock / EasyOCRBackend)                        │
│  • MaterialEstimator (Mock)                                 │
│  • EmbeddingEncoder (Mock / CLIPEncoder)                    │
│  • ComponentEngine, RecoverabilityEngine, EnvironmentalEngine│
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Training & MLOps (BaseTrainer, ModelRegistry, Evaluator)  │
│  • RunConfig, TrainerRegistry, ArtifactManager              │
│  • ExperimentTracker (JSON / MLflow)                        │
│  • Callbacks (ModelCheckpoint, EarlyStopping, Logging)      │
│  • Evaluator, Metrics, Exporter (PyTorch/TorchScript/ONNX)  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Preprocessing & Utilities                                  │
│  • ImageValidator, LoadedImage, image_loader                │
│  • MetadataGenerator, DuplicateDetector, StatisticsCalculator│
│  • Logging (Loguru + InterceptHandler), Settings (Pydantic) │
└─────────────────────────────────────────────────────────────┘
```

**Layer Responsibilities:**

1. **API Layer:** Thin routes that validate inputs (ImageValidator), delegate to the pipeline, serialize responses (Pydantic schemas). Adds per-request observability (RequestContextMiddleware: request_id, latency_ms). Translates domain exceptions (DeviceAIError) into HTTP error envelopes via registered exception handlers.

2. **Service Layer:** Orchestration facades that compose engines/repositories. `PredictionPipeline` is the single collaborator the `/predict` route depends on. `DatasetService` wires importer → duplicate detector → splitter → augmenter → exporter → versioning → reporting.

3. **Inference Engines:** Each model component implements a stable abstract protocol (Detector, ConditionAssessor, etc.). Mock implementations ship by default. Real adapters (YOLODetector, CLIPEncoder, EasyOCRBackend) guard their imports and degrade to mocks when backends are unavailable.

4. **Training & MLOps:** `BaseTrainer` captures the common training lifecycle (seeding, epoch loop, metric aggregation, callbacks, checkpointing, auto-registration). Model-specific hooks (build_model, train_step, validation_step, train_loader, val_loader) are deferred to subclasses (e.g., future `YOLOTrainer`, `CLIPTrainer`).

5. **Preprocessing & Utilities:** Image decoding/validation, dataset metadata extraction, duplicate detection, logging configuration, hashing utilities, Git commit extraction.

---

## 5. Package Organization

The AI platform is organized into **19 top-level packages** under `intelligence/device_ai`, each with a single, well-defined responsibility:

```
device_ai/
├── api/                # FastAPI routes, schemas, middleware, dependencies
├── configs/            # Settings (Pydantic), logging configuration
├── dataset/            # Import, split, augment, export, versioning, reporting
├── evaluation/         # Metrics, confusion matrices, evaluation documents
├── fingerprint/        # Visual similarity, deduplication (M1.5)
├── fusion/             # Multi-model result fusion (condition + material scoring)
├── inference/          # Core: pipeline, predictor protocols, YOLO, CLIP, EcoID
├── ocr/                # EasyOCR backend, barcode reader, text parser
├── preprocessing/      # Image validator, loader, augmentation transforms
├── training/           # BaseTrainer, RunConfig, registry, experiments, callbacks
│   ├── core/           # trainer.py, evaluator.py, exporter.py, metrics.py
│   ├── experiments/    # tracker.py (JSON/MLflow), mlflow.py
│   ├── registry/       # model_registry.py, artifact_manager.py
│   └── utils/          # seeding, timing, git_utils, env resolution
├── components/         # Component recoverability engine (M2.2)
├── environmental/      # Environmental impact scoring (M2.3)
├── materials/          # Material composition estimation
├── recoverability/     # Economic recoverability scoring (M2.2)
├── utils/              # Hashing, file_utils, image_utils, Git helpers
├── exceptions.py       # Typed domain exception hierarchy
├── app.py              # ASGI entrypoint (module-level `app = create_app()`)
├── application.py      # Application factory `create_app(settings)`
└── train.py            # Training CLI shim → training.cli.train_main

OUT OF SCOPE (see §2):
├── circular/           # Circular economy metrics (M2.4 Decision Engine)
├── decision/           # Decision Intelligence (M2.4)
├── integrity/          # Integrity verification (M2.5)
├── ledger/             # Blockchain ledger core (M3.1/M3.2)
├── lifecycle/          # Lifecycle state machine (M3.3)
├── passport/           # Digital Passport engine (M2.1)
├── trust/              # Trust catalogue (M2.5)
```

**Key Packages (In Scope):**

- **`api/`**: Four routes (`/`, `/health`, `/version`, `/predict`) + three internal routers (`/dataset`, `/fingerprint`, `/ocr`). `dependencies.py` centralizes singleton construction (`get_pipeline`, `get_registry`, `get_fingerprint_encoder`, `get_ocr_backend`). `middleware.py` adds `RequestContextMiddleware` (request_id, latency logging). `errors.py` registers exception handlers that translate `DeviceAIError` into standard error envelopes.

- **`inference/`**: `pipeline.py` (PredictionPipeline orchestration), `predictor.py` (abstract protocols + mock implementations), `yolo_detector.py` (real YOLOv8), `clip_encoder.py` (real OpenCLIP), `ecoid.py` (EcoID generator), `registry.py` (ModelRegistry for loading trained artifacts).

- **`training/`**: `core/trainer.py` (BaseTrainer lifecycle), `config.py` (RunConfig, Hydra-compatible YAML loader), `registry/model_registry.py` (JSON-backed provenance store), `registry/artifact_manager.py` (checkpoints/exports/reports layout), `experiments/tracker.py` (JSON/MLflow experiment tracking), `core/evaluator.py` (confusion matrices, metrics), `core/exporter.py` (PyTorch/TorchScript/ONNX export with honest backend-unavailable skips).

- **`dataset/`**: `service.py` (DatasetService orchestration), `importer.py`, `duplicates.py` (perceptual hash-based duplicate detection), `validator.py` (YOLO annotation validation), `splitter.py` (stratified train/val/test splitting), `augmenter.py` (Albumentations-based augmentation), `exporter.py` (YOLO/COCO/Pascal VOC export), `versioning.py` (DatasetVersionManager), `reporting.py` (quality reports).

- **`preprocessing/`**: `validator.py` (ImageValidator: count/size/MIME/resolution checks), `image_loader.py` (LoadedImage: decode once, cache metadata).

- **`configs/`**: `settings.py` (Settings: Pydantic BaseSettings, parsed once at startup), `logging.py` (Loguru configuration, console/JSON sinks, InterceptHandler for stdlib logging).

---

## 6. Dependency Graph

The AI platform's module dependencies flow **downward** through the layers, with strict boundaries:

```
┌────────────────────────────────────────────────────────────┐
│ app.py / application.py (ASGI entrypoint, factory)        │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ api/ (routes, dependencies, middleware, schemas, errors)   │
└────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ inference/      │  │ dataset/        │  │ fingerprint/     │
│ pipeline        │  │ service         │  │ service          │
└─────────────────┘  └─────────────────┘  └──────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ predictor       │  │ importer        │  │ verification     │
│ yolo_detector   │  │ splitter        │  │ repository       │
│ clip_encoder    │  │ augmenter       │  │                  │
│ ecoid           │  │ exporter        │  │                  │
└─────────────────┘  └─────────────────┘  └──────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ preprocessing/  │  │ metadata        │  │ ocr/             │
│ validator       │  │ duplicates      │  │ backends         │
│ image_loader    │  │ statistics      │  │ parser           │
└─────────────────┘  └─────────────────┘  └──────────────────┘
         ↓                    ↓                    ↓
┌────────────────────────────────────────────────────────────┐
│ utils/ (hashing, file_utils, image_utils, Git helpers)    │
│ configs/ (Settings, logging)                               │
│ exceptions.py (typed domain errors)                        │
└────────────────────────────────────────────────────────────┘
```

**Training Platform Dependencies (Parallel to Inference):**

```
┌────────────────────────────────────────────────────────────┐
│ train.py (CLI shim) → training/cli.py                      │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ training/core/trainer.py (BaseTrainer lifecycle)           │
└────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ config.py       │  │ registry/       │  │ experiments/     │
│ RunConfig       │  │ model_registry  │  │ tracker          │
│ load_config     │  │ artifact_mgr    │  │ (JSON/MLflow)    │
└─────────────────┘  └─────────────────┘  └──────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ core/callbacks  │  │ core/evaluator  │  │ core/exporter    │
│ core/metrics    │  │ core/metrics    │  │ (Torch/ONNX)     │
└─────────────────┘  └─────────────────┘  └──────────────────┘
```

**Key Dependency Rules:**

1. **API never imports inference internals** (predictor protocols, YOLO/CLIP adapters). It depends only on `PredictionPipeline` and `DatasetService` facades.

2. **No circular dependencies.** `utils/` and `configs/` are leaf modules. `exceptions.py` is imported everywhere but imports nothing domain-specific.

3. **Optional dependencies are guarded.** `ultralytics`, `open-clip-torch`, `easyocr`, `torch`, `onnx`, `mlflow`, `hydra-core` are imported inside try/except blocks. Missing backends degrade to mocks or skip exports rather than raising ImportError.

4. **Settings flow downward.** `configs/settings.py` is imported by `api/dependencies.py` and `training/cli.py`. Every service/adapter receives settings via constructor injection.

5. **Training is independent of inference.** `BaseTrainer` does not import `PredictionPipeline`. `ModelRegistry` is shared (both training and inference read registered artifacts), but training never calls `/predict`.

---

## 7. AI Service Architecture

The AI platform exposes **four public HTTP endpoints** and **three internal-only services**:

### Public HTTP Surface (FastAPI)

```
GET  /               → RootResponse (liveness: service, version, docs)
GET  /health         → HealthResponse (readiness: overall status, per-component ready flags, model_dir_available)
GET  /version        → VersionResponse (service, version, model_version, api contract)
POST /predict        → PredictionResponse (frozen M1.1 contract, backward-compatible across milestones)
```

**`/predict` Contract (Frozen):**

- **Request:** Multipart/form-data with 1–`MAX_IMAGES` image files (JPEG/PNG/WebP)
- **Response:** `PredictionResponse` schema (eco_id, device_type, brand, confidence, condition, ocr, materials, carbon_score, embedding_id, model_version)
- **Guarantees:** Schema shape is frozen. Mock → real model transitions change only the *values* (confidence becomes genuine, brand stays placeholder until manufacturer model ships), never the keys.

### Internal Services (No HTTP Surface)

1. **Dataset Pipeline** (`POST /dataset/*` — internal router, not exposed to backend):
   - Import images from external directories
   - Duplicate detection (perceptual hashing)
   - YOLO annotation validation
   - Train/val/test splitting (stratified)
   - Augmentation (Albumentations: flip, rotate, brightness, contrast, noise)
   - Export (YOLO, COCO, Pascal VOC)
   - Versioning (DatasetVersionManager: manifest, Git commit, timestamp)
   - Quality reports (JSON + self-contained HTML)

2. **Fingerprint Service** (`POST /fingerprint/*` — internal router, M1.5):
   - Visual similarity search via CLIP embeddings
   - Duplicate device detection (cosine/euclidean/manhattan distance)
   - EcoID lookup by similarity threshold
   - Persistence: in-memory or JSON file backend

3. **OCR Service** (`POST /ocr/*` — internal router, M1.6):
   - EasyOCR text recognition (multi-language)
   - OpenCV barcode/QR code reader
   - Structured parser (serial number, model ID extraction via regex patterns)

### Service Orchestration

**`PredictionPipeline`** (the single collaborator `/predict` depends on):

```python
class PredictionPipeline:
    def __init__(self, *, 
                 detector: Detector,
                 condition: ConditionAssessor,
                 ocr: OCREngine,
                 material: MaterialEstimator,
                 embedding: EmbeddingEncoder,
                 ecoid_generator: EcoIDGenerator,
                 model_version: str):
        # All components injected, no globals, no hardcoded paths
    
    def predict(self, images: list[LoadedImage]) -> PredictionResult:
        # Orchestration order (each step is independent):
        detection = self.detector.detect(images)
        embedding_vector = self.embedding.embed(images)
        condition = self.condition.assess(images)
        ocr_result = self.ocr.extract(images)
        materials = self.material.estimate(images, detection.device_type)
        carbon_score = self._carbon_score(condition, materials)
        eco_id = self.ecoid_generator.generate()
        return PredictionResult(...)
    
    def health(self) -> dict[str, bool]:
        # Per-component readiness (is_ready property)
        return {
            "detector": self.detector.is_ready,
            "condition": self.condition.is_ready,
            ...
        }
```

**Factory Functions (Dependency Injection):**

`api/dependencies.py` centralizes singleton construction:

- `get_pipeline() -> PredictionPipeline` (cached, builds YOLODetector if artifact resolves, else all-mock)
- `get_registry() -> ModelRegistry` (cached, JSON-backed provenance store)
- `get_fingerprint_encoder() -> EmbeddingEncoder` (cached, CLIPEncoder if backend present, else mock)
- `get_ocr_backend() -> OCRBackend` (cached, EasyOCRBackend if installed, else mock)
- `get_validator(settings) -> ImageValidator` (per-request, cheap, no state)
- `get_dataset_service(settings) -> DatasetService` (per-request, wires layout/importer/splitter/etc.)

---

## 8. Configuration Management

Configuration is centralized in a single **Pydantic `BaseSettings` class** (`configs/settings.py`) parsed once at startup from `.env` (or environment variables). No module reads `os.environ` directly.

### Settings Structure

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=False, 
        extra="ignore"
    )
    
    # Service
    app_name: str = "Device Intelligence Engine"
    environment: Literal["development", "staging", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = Field(default=8100, ge=1, le=65535)
    model_version: str = "1.0.0"
    
    # Directories
    model_dir: Path = Path("models")
    upload_dir: Path = Path("uploads")
    dataset_dir: Path = Path("data/datasets")
    artifact_dir: Path = Path("artifacts")
    mlruns_dir: Path = Path("mlruns")
    
    # YOLO Detector (M1.4)
    detector_weights: str = "yolo/device-detector.pt"
    detector_image_size: int = 640
    detector_confidence_threshold: float = 0.25
    
    # OpenCLIP Encoder (M1.5)
    clip_weights: str = "clip/open_clip_pytorch_model.bin"
    clip_model_name: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"
    
    # OCR (M1.6)
    ocr_backend: OCRBackendName = "easyocr"
    ocr_weights: str = "ocr/"
    ocr_languages: list[str] = ["en"]
    ocr_use_gpu: bool = False
    ocr_min_confidence: float = 0.5
    barcode_enabled: bool = True
    
    # Upload Constraints
    max_images: int = 10
    min_images: int = 1
    max_file_size: int = 10 * 1024 * 1024  # 10 MB
    
    # Training
    experiment_tracker: ExperimentTracker = "json"  # json | mlflow | none
    
    # Fingerprinting (M1.5)
    fingerprint_backend: FingerprintBackend = "memory"  # memory | json
    fingerprint_store_dir: Path = Path("data/fingerprints")
    fingerprint_metric: SimilarityMetricName = "cosine"
    fingerprint_match_threshold: float = 0.85
    
    # Logging
    log_level: LogLevel = "INFO"
    json_logs: bool = False
```

### Configuration Lifecycle

1. **Startup (`app.py` → `application.py`):**
   - `Settings()` is instantiated once (reads `.env`, validates types, applies defaults)
   - Stored in `app.state.settings` (FastAPI app context)
   - Cached via `@lru_cache(maxsize=1)` in `get_settings()` (dependency injection)

2. **Dependency Injection:**
   - Routes receive settings via `Depends(get_settings)`
   - Service constructors accept `settings: Settings` (injected by factories)
   - Tests override settings by calling `reset_dependency_caches()` and providing a custom `Settings` instance

3. **Path Resolution:**
   - All relative paths (`detector_weights`, `clip_weights`, `ocr_weights`) are resolved relative to `model_dir`
   - `api/dependencies.py` performs resolution: `weights = Path(settings.detector_weights); if not weights.is_absolute(): weights = settings.model_dir / weights`

### Design Rationale

- **Single Source of Truth:** Every configurable value lives in `Settings`. No scattered `os.getenv()` calls.
- **Type Safety:** Pydantic validates types at parse time. Invalid values (e.g., `port=99999`, `log_level="LOUD"`) raise `ValidationError` at startup, never in production.
- **Test Overrides:** Tests construct a `Settings` object with custom values, inject it, and call `reset_dependency_caches()` to rebuild singletons.
- **Environment Parity:** The same `.env` format works in development, staging, and production. Environment-specific overrides are layered (`.env` → `.env.staging` → actual env vars).

---

## 9. Model Abstraction Layer

Every inference component implements a **stable abstract protocol** with mock and real implementations behind the same interface:

### Abstract Protocols (`inference/predictor.py`)

```python
class BaseModel(ABC):
    """Common metadata contract for every model component."""
    name: str = "base"
    version: str = "mock-1.0.0"
    
    @property
    def is_ready(self) -> bool:
        """Whether the component is loaded and ready to serve."""
        return True  # Mocks are always ready


class Detector(BaseModel):
    name = "detector"
    
    @abstractmethod
    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        """Return device type/brand/confidence/detections for a batch."""


class ConditionAssessor(BaseModel):
    name = "condition"
    
    @abstractmethod
    def assess(self, images: list[LoadedImage]) -> ConditionResult:
        """Return condition label (Excellent/Good/Fair/Poor) and score."""


class OCREngine(BaseModel):
    name = "ocr"
    
    @abstractmethod
    def extract(self, images: list[LoadedImage]) -> OCRResult:
        """Return extracted serial number and model identifier."""


class MaterialEstimator(BaseModel):
    name = "material"
    
    @abstractmethod
    def estimate(self, images: list[LoadedImage], device_type: str) -> MaterialResult:
        """Return normalized material composition (fractions sum to ~1.0)."""


class EmbeddingEncoder(BaseModel):
    name = "clip"
    
    @abstractmethod
    def embed(self, images: list[LoadedImage]) -> EmbeddingVector:
        """Return L2-normalized visual embedding for a batch."""
    
    def encode(self, images: list[LoadedImage]) -> EmbeddingResult:
        """Return embedding identifier (default derives from embed())."""
```

### Mock Implementations (M1.1, Deterministic, Zero-Weight)

**Design:** Mock outputs are derived from a stable SHA-256 seed of the batch's concatenated per-image content hashes, so identical inputs always yield identical predictions—no `random` module, no trained weights, fully reproducible.

```python
class MockDetector(Detector):
    version = "mock-detector-1.0.0"
    
    def detect(self, images: list[LoadedImage]) -> DetectionResult:
        seed = _batch_seed(images)  # SHA-256 → int
        return DetectionResult(
            device_type=_pick(_DEVICE_TYPES, seed),  # ["Laptop", "Smartphone", ...]
            brand=_pick(_BRANDS, seed >> 3),
            confidence=_confidence(seed, low=0.80, high=0.99),
            detections=[],  # Empty until real YOLO
        )
```

**Material Profiles:** Per-device-type nominal compositions (fractions sum to 1.0):

```python
_MATERIAL_PROFILES = {
    "Laptop": {"plastic": 0.42, "aluminum": 0.26, "copper": 0.15, "pcb": 0.10, "battery": 0.07},
    "Smartphone": {"plastic": 0.30, "aluminum": 0.22, "copper": 0.14, "pcb": 0.18, "battery": 0.16},
    ...
}
```

**Mock Embedding:** Pseudo-embedding via deterministic LCG (Numerical Recipes constants) over 512-dim space, L2-normalized:

```python
class MockEmbeddingEncoder(EmbeddingEncoder):
    dimension = 512
    
    def embed(self, images: list[LoadedImage]) -> EmbeddingVector:
        seed = _batch_seed(images)
        state = seed
        raw = []
        for _ in range(self.dimension):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            raw.append(state / 0x7FFFFFFF - 1.0)
        return EmbeddingVector(
            values=l2_normalize(tuple(raw)),
            dimension=self.dimension,
            normalized=True
        )
```

### Real Implementations (M1.4+, Optional Backends)

**YOLODetector** (`inference/yolo_detector.py`, M1.4):

- **Backend:** `ultralytics` (YOLO v8)
- **Loading:** Guarded import; degrades to mock when backend unavailable
- **Inference:** Runs YOLO over batch, collects per-object detections, aggregates highest-confidence detection as device_type/confidence/bounding_box
- **Brand:** Placeholder "Unknown" until manufacturer model ships (later sprint)

```python
class YOLODetector(Detector):
    version = "yolo-detector-1.0.0"
    
    def __init__(self, *, weights_path, image_size=640, confidence_threshold=0.25, label_map=None, model=None):
        if model is not None:
            self._model = model  # Injected for tests
        elif weights_path is not None:
            self._model = self._load(weights_path)  # Load from disk
        else:
            self._model = None
    
    @property
    def is_ready(self) -> bool:
        return self._model is not None
    
    def _load(self, weights_path):
        resolved = self._resolve_weights(weights_path)  # File or dir/model.pt
        if resolved is None:
            logger.warning("No detector artifact found; detector not loaded.")
            return None
        yolo_cls = _import_yolo()  # try: from ultralytics import YOLO
        if yolo_cls is None:
            logger.warning("ultralytics not installed; detector not loaded.")
            return None
        try:
            model = yolo_cls(str(resolved))
        except Exception as exc:
            logger.warning(f"Failed to load detector: {exc}")
            return None
        logger.info(f"Loaded YOLO detector from '{resolved}'.")
        return model
    
    def detect(self, images):
        if not self.is_ready:
            raise ModelNotLoadedError("YOLO detector has no model loaded.")
        frames = [img.image for img in images]
        results = self._run_inference(frames)  # model.predict(frames, imgsz=..., conf=...)
        detections = self._parse_results(results)  # Extract boxes/confidences/classes
        return self._aggregate(detections)  # Best detection → DetectionResult
```

**CLIPEncoder** (`inference/clip_encoder.py`, M1.5):

- **Backend:** `open-clip-torch` (OpenCLIP ViT-B/32)
- **Inference:** Encodes per-image, mean-pools batch, L2-normalizes → single 512-dim unit vector
- **Degradation:** Mock encoder when backend unavailable

```python
class CLIPEncoder(EmbeddingEncoder):
    def __init__(self, *, weights_path, model_name="ViT-B-32", pretrained="laion2b_s34b_b79k", dimension=512, device=None, encode_fn=None):
        self._dimension = dimension
        self.version = f"openclip-{model_name.lower()}-1.0.0"
        if encode_fn is not None:
            self._encode_fn = encode_fn  # Injected for tests
        else:
            self._encode_fn = self._build_backend(weights_path)
    
    def _build_backend(self, weights_path):
        open_clip = _import_open_clip()  # try: import open_clip
        torch = _import_torch()
        if open_clip is None or torch is None:
            logger.warning("open-clip-torch/torch not installed; CLIP encoder not loaded.")
            return None
        return self._load_model(open_clip, torch, weights_path)
    
    def embed(self, images):
        if self._encode_fn is None:
            raise EncoderNotReadyError("OpenCLIP encoder has no model loaded.")
        raw = self._encode_fn(images)  # Per-image features
        return self._aggregate(raw)  # Mean-pool + L2-normalize
```

**EasyOCRBackend** (`ocr/backends.py`, M1.6):

- **Backend:** `easyocr.Reader` (multi-language text recognition)
- **Degradation:** Mock OCR (returns empty strings) when backend unavailable

---

## 10. Inference Pipeline

The `PredictionPipeline` orchestrates **six independent inference steps** and derives a carbon score, producing a complete `PredictionResult`:

### Execution Flow

```
POST /predict (multipart images)
         ↓
ImageValidator.validate_batch(uploads)
  • Count check (MIN_IMAGES ≤ count ≤ MAX_IMAGES)
  • Per-file size check (≤ MAX_FILE_SIZE)
  • MIME type allowlist (JPEG/PNG/WebP)
  • Decode (PIL.Image, eager .load() to surface corruption)
  • Resolution bounds check
         ↓
[List[LoadedImage]: decoded once, metadata cached]
         ↓
PredictionPipeline.predict(images)
  ┌─────────────────────────────────────────────┐
  │ 1. Detector.detect(images)                  │
  │    → device_type, brand, confidence, bbox   │
  ├─────────────────────────────────────────────┤
  │ 2. EmbeddingEncoder.embed(images)           │
  │    → 512-dim L2-normalized vector           │
  ├─────────────────────────────────────────────┤
  │ 3. ConditionAssessor.assess(images)         │
  │    → label (Excellent/Good/Fair/Poor), score│
  ├─────────────────────────────────────────────┤
  │ 4. OCREngine.extract(images)                │
  │    → serial_number, model                   │
  ├─────────────────────────────────────────────┤
  │ 5. MaterialEstimator.estimate(images, type) │
  │    → composition dict (fractions sum ~1.0)  │
  ├─────────────────────────────────────────────┤
  │ 6. _carbon_score(condition, materials)      │
  │    → base(50) + weight × value, [0,100]     │
  ├─────────────────────────────────────────────┤
  │ 7. EcoIDGenerator.generate()                │
  │    → ET-YYYY-XXXXXXXX                       │
  └─────────────────────────────────────────────┘
         ↓
PredictionResult (frozen dataclass)
         ↓
_to_response(result) → PredictionResponse (Pydantic schema)
         ↓
JSON response to client
```

### Carbon Score Formula

```python
def _carbon_score(condition: ConditionResult, materials: MaterialResult) -> float:
    """Derive environmental recovery score from condition and materials."""
    _BASE_CARBON_SCORE = 50.0
    _CONDITION_WEIGHTS = {
        "Excellent": 1.0,
        "Good": 0.85,
        "Fair": 0.65,
        "Poor": 0.4,
    }
    _MATERIAL_CARBON_VALUE = {
        "aluminum": 60,
        "copper": 55,
        "pcb": 45,
        "battery": 40,
        "plastic": 15,
    }
    
    weight = _CONDITION_WEIGHTS.get(condition.label, 0.5)
    value = sum(
        _MATERIAL_CARBON_VALUE.get(mat, 0) * frac
        for mat, frac in materials.composition.items()
    )
    score = _BASE_CARBON_SCORE + weight * value
    return round(max(0.0, min(100.0, score)), 2)
```

**Design Rationale:**
- **Base 50:** Neutral starting point (any device has some recovery potential)
- **Condition weight:** Better condition → higher multiplier (resale/refurbishment potential)
- **Material value:** High-value materials (aluminum, copper) boost score; low-value (plastic) contribute less
- **Clamping [0,100]:** Output is always a valid percentage

### Pipeline Factories

```python
def build_mock_pipeline(*, model_version: str, year: int, sequence_start: int = 1) -> PredictionPipeline:
    """All-mock pipeline (M1.1 baseline, deterministic, zero dependencies)."""
    return PredictionPipeline(
        detector=MockDetector(),
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=year, sequence_start=sequence_start),
        model_version=model_version,
    )

def build_detection_pipeline(*, detector: Detector, model_version: str, year: int, sequence_start: int = 1) -> PredictionPipeline:
    """Real YOLO detector + mock rest (M1.4 partial-real transition)."""
    return PredictionPipeline(
        detector=detector,  # Real YOLODetector
        condition=MockConditionAssessor(),
        ocr=MockOCREngine(),
        material=MockMaterialEstimator(),
        embedding=MockEmbeddingEncoder(),
        ecoid_generator=EcoIDGenerator(year=year, sequence_start=sequence_start),
        model_version=model_version,
    )
```

**Progressive Real-Model Integration:**
- M1.1: All mocks
- M1.4: Real YOLO detector, mock rest
- M1.5: Real YOLO + real CLIP encoder, mock OCR/condition/material
- M1.6: Real YOLO + CLIP + EasyOCR, mock condition/material
- Future: All real models

---

## 11. Training Platform

The training platform is a **complete MLOps pipeline** independent of the inference service. It provides abstract lifecycle orchestration, experiment tracking, model registry, artifact management, evaluation, and export—all designed for reproducibility and testability.

### Core Components

**`BaseTrainer`** (`training/core/trainer.py`):  
Abstract lifecycle capturing everything common to training any model. Subclasses implement five hooks:

```python
class BaseTrainer(ABC):
    framework: str = "base"  # "torch", "ultralytics", etc.
    monitor_metric: str = "val_loss"
    monitor_mode: str = "min"  # "min" or "max"
    
    @abstractmethod
    def build_model(self) -> Any:
        """Construct the untrained model."""
    
    @abstractmethod
    def train_loader(self) -> Iterable[Any]:
        """Return training batches for one epoch."""
    
    @abstractmethod
    def val_loader(self) -> Iterable[Any]:
        """Return validation batches for one epoch."""
    
    @abstractmethod
    def train_step(self, model, batch) -> dict[str, float]:
        """Run one training step, return metrics (must include 'loss')."""
    
    @abstractmethod
    def validation_step(self, model, batch) -> dict[str, float]:
        """Run one validation step, return metrics (prefixed 'val_')."""
    
    def save_checkpoint(self, model, path: Path) -> None:
        """Persist checkpoint (overridable, default writes text marker)."""
    
    def fit(self) -> TrainingHistory:
        """Execute full training lifecycle, return history."""
```

**Fit Lifecycle:**

```
1. Seed RNGs (config.training.seed)
2. Build model (build_model())
3. Open tracked run (tracker.run(run_id, experiment_name, config))
4. For each epoch:
   a. Aggregate training metrics (train_loader → train_step)
   b. Aggregate validation metrics (val_loader → validation_step, prefix "val_")
   c. Dispatch callbacks (on_epoch_end: logging, checkpointing, early stopping)
   d. Break if state.stop_training (early stopping fired)
5. Write checkpoint (save_checkpoint)
6. Auto-register ModelRecord (registry.register)
7. Return TrainingHistory (epochs_completed, training_time, best_epoch, etc.)
```

### RunConfig (Hydra-Compatible)

```yaml
# configs/default.yaml
defaults:
  - training
  - optimizer

model_name: device-detector
trainer: mock  # TrainerRegistry key
experiment_name: die-training
tags:
  milestone: M1.3
  author: team

# training.yaml
batch_size: 16
epochs: 100
device: auto  # auto | cpu | cuda
mixed_precision: false
workers: 4
seed: 42
image_size: 640
dataset_version: latest
model_version: 1.0.0
early_stopping_patience: 10

# optimizer.yaml
optimizer: adamw
learning_rate: 0.001
weight_decay: 0.0
momentum: 0.9
scheduler: cosine
warmup_epochs: 5
```

**Loading:**  
`load_config("configs/default.yaml")` composes `training.yaml` and `optimizer.yaml` via the `defaults` list (PyYAML only, no Hydra required). Validates into frozen `RunConfig` (Pydantic).

---

## 12. Dataset Management

The dataset pipeline is a **complete intelligence workflow** for preparing e-waste training data. It orchestrates import, quality analysis, duplicate detection, annotation validation, stratified splitting, augmentation, export, versioning, and reporting—entirely offline (no HTTP surface).

### Dataset Layout (`dataset/layout.py`)

```
DATASET_DIR/
├── raw/                # Imported images, original resolution
├── processed/          # Cleaned/renamed images (future: deduplication)
├── cleaned/            # Final curated set (future: manual review)
├── labels/             # YOLO annotations (.txt, one per image)
├── metadata/           # Per-image analysis (JSON: dimensions, hash, corruption)
├── splits/             # Train/val/test manifests (one .txt per split)
├── augmented/          # Augmented training images (optional, M1.2)
├── quality_reports/    # Dataset quality JSON/HTML reports
├── exports/            # Exported datasets (YOLO, COCO, Pascal VOC)
└── versions/           # Version manifests (Git commit, timestamp, statistics)
```

### Core Operations

**1. Import (`dataset/importer.py`):**
- Copies images from external directory to `raw/`
- Optional deduplication (perceptual hash: same visual content rejected)
- Sanitizes filenames (removes special characters, enforces extension)
- Returns `ImportSummary` (total/copied/skipped/duplicates)

**2. Metadata Generation (`dataset/metadata.py`):**
- Scans directory, decodes images (PIL), extracts: width, height, file size, SHA-256, format
- Detects corruption (PIL decode failure)
- Writes per-image JSON to `metadata/`
- Returns `list[ImageRecord]`

**3. Duplicate Detection (`dataset/duplicates.py`):**
- Perceptual hashing via `imagehash.phash` (8×8 DCT-based hash)
- Groups images with Hamming distance ≤ threshold (default 5)
- Returns `DuplicateReport` (groups, count)

**4. Annotation Validation (`dataset/validator.py`):**
- YOLO format: `<class_id> <x_center> <y_center> <width> <height>` (normalized [0,1])
- Checks: annotation file exists, coordinates in bounds, class IDs valid
- Returns `AnnotationReport` (valid/invalid/missing counts, error details)

**5. Splitting (`dataset/splitter.py`):**
- Stratified split (preserves per-class distribution): train/val/test (default 0.7/0.2/0.1)
- Writes three `.txt` manifests to `splits/` (one filename per line)
- Returns `SplitAssignment` (per-split image counts)

**6. Augmentation (`dataset/augmenter.py`):**
- Albumentations-based: horizontal flip, rotate (±15°), brightness/contrast (±0.2), Gaussian noise (var=0.01)
- Applies per-image, writes augmented copies to `augmented/`
- Preserves annotations (transforms bounding boxes)
- Returns `AugmentationResult` (original/augmented counts)

**7. Export (`dataset/exporter.py`):**
- **YOLO:** `images/` + `labels/` directories, `data.yaml` config
- **COCO:** Single `annotations.json` (images, annotations, categories arrays)
- **Pascal VOC:** Per-image XML annotations (`<annotation><object><bndbox>`)
- Writes to `exports/<format>/`, returns `ExportResult`

**8. Versioning (`dataset/versioning.py`):**
- `DatasetVersionManager`: JSON-backed version manifest store
- Records: version ID, timestamp, Git commit, split sizes, statistics (mean dimensions, class distribution)
- Resolves `"latest"` to newest version
- Returns `DatasetVersion`

**9. Reporting (`dataset/reporting.py`):**
- Builds quality report: image count, dimension statistics, class distribution, duplicate groups, annotation coverage
- Outputs JSON + self-contained HTML (no external assets, no JavaScript)

---

## 13. Model Registry

The `ModelRegistry` (`training/registry/model_registry.py`) is a **JSON-backed provenance store** that records the complete lineage of every trained artifact: model name, version, dataset version, timestamp, Git commit, achieved metrics, framework, export formats, artifact location, and tags.

### ModelRecord Structure

```python
@dataclass(frozen=True, slots=True)
class ModelRecord:
    name: str                          # Logical model name (e.g., "device-detector")
    version: str                       # Semantic version (e.g., "1.0.0")
    dataset_version: str               # Dataset snapshot the model was trained on
    created_at: str                    # ISO-8601 UTC timestamp
    git_commit: str                    # Short Git commit hash (or "unknown")
    framework: str                     # Training framework ("torch", "ultralytics", "mock")
    metrics: dict[str, float]          # Final epoch metrics (accuracy, loss, mAP, etc.)
    export_formats: tuple[str, ...]    # Available exports ("pytorch", "torchscript", "onnx")
    artifact_location: str             # POSIX path to checkpoint file
    tags: dict[str, str]               # Free-form metadata (milestone, author, experiment)
    
    @property
    def key(self) -> str:
        return f"{self.name}:{self.version}"
```

### Operations

```python
# Append a new record
registry.register(record) -> ModelRecord

# List all models
registry.list_models() -> list[ModelRecord]

# Get all versions of a model
registry.versions("device-detector") -> list[ModelRecord]

# Get latest version
registry.latest("device-detector") -> ModelRecord | None

# Get exact version
registry.get("device-detector", "1.0.0") -> ModelRecord  # raises ModelNotFoundError if missing

# Resolve "latest" or explicit version
registry.resolve("device-detector", "latest") -> ModelRecord
registry.resolve("device-detector", "1.2.3") -> ModelRecord
```

### Storage Format

Persisted as `<artifact_dir>/model_registry.json`:

```json
[
  {
    "artifact_location": "artifacts/checkpoints/device-detector-1.0.0.pt",
    "created_at": "2026-08-05T10:23:45.123456",
    "dataset_version": "v1-20260805",
    "export_formats": ["pytorch", "onnx"],
    "framework": "torch",
    "git_commit": "abc1234",
    "metrics": {"accuracy": 0.92, "val_loss": 0.15},
    "name": "device-detector",
    "tags": {"milestone": "M1.3", "author": "team"},
    "version": "1.0.0"
  }
]
```

### Design Rationale

- **Append-Only:** New records are appended; existing records are never modified. This preserves the full training history.
- **Single File:** All records live in one JSON document for simplicity. Future scale: migrate to SQLite or a real registry service.
- **Injected Timestamps/Commits:** `created_at` and `git_commit` are passed in by the trainer (which gets them from injected clock/Git helpers), never read from wall clock/subprocess inside the registry. This keeps the registry pure and reproducible.
- **Resolves "latest":** `registry.resolve(name, "latest")` returns the newest record for a model, so training configs can declare `dataset_version: latest` and the trainer resolves at runtime.

---

## 14. Evaluation Framework

The evaluation framework (`training/core/evaluator.py`) turns raw predictions or pre-computed metrics into **machine-readable JSON documents and self-contained HTML reports** for model assessment.

### Evaluation Document Structure

```python
{
    "model_name": "device-detector",
    "model_version": "1.0.0",
    "dataset_version": "v1-20260805",
    "generated_at": "2026-08-05T14:23:45.123456",
    "num_samples": 1000,
    "metrics": {
        "accuracy": 0.92,
        "precision": 0.91,
        "recall": 0.90,
        "f1": 0.905,
        "mAP": 0.88
    },
    "confusion_matrix": {
        "labels": ["Laptop", "Smartphone", "Tablet"],
        "matrix": [[450, 20, 5], [15, 380, 10], [8, 12, 100]]
    },
    "benchmark": {
        "status": "placeholder",
        "note": "Inference benchmarking deferred to model implementation.",
        "latency_ms": null,
        "throughput_fps": null,
        "device": "",
        "batch_size": null
    }
}
```

### Evaluator API

```python
class Evaluator:
    def evaluate(self, *, model_name, model_version, y_true, y_pred, 
                 class_names, generated_at, dataset_version="", 
                 num_classes=None, average="macro") -> dict:
        """Compute metrics from raw labels and build evaluation document."""
        
    def to_html(self, document: dict) -> str:
        """Render evaluation document as self-contained HTML."""
```

**Computed Metrics (`training/core/metrics.py`):**

- **Accuracy:** `(TP + TN) / total`
- **Precision (per-class + averaged):** `TP / (TP + FP)`
- **Recall (per-class + averaged):** `TP / (TP + FN)`
- **F1 (per-class + averaged):** `2 * (precision * recall) / (precision + recall)`
- **mAP (mean Average Precision):** Area under precision-recall curve, averaged over classes
- **Confusion Matrix:** `[true_rows × predicted_cols]`

**Averaging Modes:**
- `macro`: Unweighted mean of per-class metrics
- `weighted`: Weighted by support (# samples per class)
- `micro`: Global TP/FP/FN aggregation

### HTML Report

Self-contained, no external CSS/JS, renders:

1. **Header:** Model name, version, dataset version, generation timestamp
2. **Metrics Table:** Accuracy, precision, recall, F1, mAP
3. **Confusion Matrix:** HTML table (true rows × predicted columns)
4. **Benchmark Section:** Placeholder note (real latency/throughput deferred to model-implementation milestones)

**Design Rationale:**

- **Reproducible:** `generated_at` injected (not wall-clock read inside evaluator)
- **Self-Contained HTML:** No CDN dependencies, no JavaScript, works offline
- **Honest Placeholder:** Benchmark section explicitly marked "placeholder" rather than fake numbers
- **Mirrors Dataset Reporting:** Same JSON+HTML pattern as `dataset/reporting.py`

---

## 15. Experiment Tracking

The training platform supports **three experiment tracking backends**: JSON (default, zero dependencies), MLflow (optional, feature-rich), and None (tracking disabled).

### ExperimentTracker Protocol

```python
class ExperimentTracker(Protocol):
    backend: str  # "json" | "mlflow" | "none"
    
    def run(self, *, run_id: str, experiment_name: str = "", 
            config: dict[str, Any] | None = None) -> RunHandle:
        """Open a tracked run context."""

class RunHandle(Protocol):
    run_id: str
    
    def log_params(self, params: dict[str, Any]) -> None:
        """Record hyper-parameters (typically once at start)."""
    
    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        """Record per-epoch metrics."""
    
    def set_summary(self, summary: dict[str, Any]) -> None:
        """Record final run-level metadata (training_time, git_commit, etc.)."""
    
    def __enter__(self) -> RunHandle: ...
    def __exit__(self, ...) -> None: ...
```

### JSON Tracker (Default)

**Storage:** `<mlruns_dir>/<run_id>/` with three files:

```
mlruns/
└── device-detector-1.0.0-20260805-142345/
    ├── params.json        # Hyper-parameters (RunConfig serialized)
    ├── metrics.json       # Per-epoch metrics [{step: 0, loss: 0.5, ...}, ...]
    └── meta.json          # Run identity + summary (training_time, git_commit, best_epoch)
```

**Design:**
- Each write persists the whole file (atomic updates)
- No server required, works in base environment
- Compatible with MLflow directory structure (can be imported later)

### MLflow Tracker (Optional)

**Activation:** `EXPERIMENT_TRACKER=mlflow` + `mlflow` package installed

**Features:**
- Full MLflow UI (`mlflow ui --backend-store-uri <mlruns_dir>`)
- Comparison across runs, hyperparameter sweeps
- Model artifact registry (separate from local JSON registry)

**Degradation:** If `EXPERIMENT_TRACKER=mlflow` but `mlflow` is not installed, falls back to JSON tracker with logged warning.

### NullTracker

**Activation:** `EXPERIMENT_TRACKER=none`

**Behavior:** No-op context manager, discards all logged data. Used when training is orchestrated by an external system (e.g., Kubernetes Jobs with centralized tracking).

---

## 16. Export Pipeline

The export pipeline (`training/core/exporter.py`) produces **three artifact formats** from a trained model: PyTorch weights (`.pt`), TorchScript (`.torchscript`), and ONNX (`.onnx`). Every format is handled by an adapter implementing the `ModelExporter` protocol.

### Export Formats

| Format | Backend | Use Case | Status |
|--------|---------|----------|--------|
| **PyTorch** | `torch.save` | Native weights, further training | Exported when torch present, skipped otherwise |
| **TorchScript** | `torch.jit.script` | Production inference (Python-free) | Exported when torch present, skipped otherwise |
| **ONNX** | `torch.onnx.export` | Cross-framework deployment (TensorRT, ONNX Runtime) | Exported when torch+onnx present, skipped otherwise |

**TensorRT:** Explicitly out of scope for M1.3.

### ExportRecord

```python
@dataclass(frozen=True, slots=True)
class ExportRecord:
    export_format: str       # "pytorch" | "torchscript" | "onnx"
    status: str              # "exported" | "skipped" | "failed"
    location: str            # POSIX path (empty when not written)
    message: str             # Reason for skip/failure
```

### Honest Backend-Unavailable Skips

**Design Principle:** Missing dependencies yield `status="skipped"` with a clear message rather than raising ImportError. The caller always gets a complete outcome list (one record per requested format), so export absence is explicit and logged rather than silent.

```python
class PyTorchExporter:
    def export(self, model, destination, **kwargs) -> ExportRecord:
        if not _torch_available():  # try: import torch
            return SkippedExport(
                "pytorch", 
                "PyTorch is not installed; export skipped."
            )
        # Perform torch.save(model.state_dict(), destination)
        return ExportRecord("pytorch", "exported", str(destination))
```

**Rationale:** The training platform is fully exercisable in the base environment (M1.3 milestone scope: no models are trained, no torch installed). Every exporter's skip path is unit-tested with fakes; the torch-present path is marked `# pragma: no cover`.

### Export CLI

```bash
python -m device_ai.cli export \
    --model device-detector \
    --version 1.0.0 \
    --formats pytorch torchscript onnx
```

**Output:**
```
Export 'pytorch' → artifacts/exports/device-detector-1.0.0.pt (exported)
Export 'torchscript' skipped: PyTorch is not installed; export skipped.
Export 'onnx' skipped: PyTorch is not installed; export skipped.
```

---

## 17. Mock vs Production Models

The AI platform is designed for **progressive real-model integration** via a stable abstract interface. Mock implementations ship by default; real models are loaded when their optional dependencies resolve.

### Swapping Strategy

**Interface Stability:**
Every inference component (Detector, ConditionAssessor, OCREngine, MaterialEstimator, EmbeddingEncoder) implements an abstract protocol with:
- `name: str` — component identifier
- `version: str` — artifact version
- `is_ready: bool` — readiness flag
- One abstract method: `detect()`, `assess()`, `extract()`, `estimate()`, or `embed()`

**Mock → Real Transition:**
```python
# M1.1: All mocks
pipeline = PredictionPipeline(
    detector=MockDetector(),
    condition=MockConditionAssessor(),
    ocr=MockOCREngine(),
    material=MockMaterialEstimator(),
    embedding=MockEmbeddingEncoder(),
    ...
)

# M1.4: Real YOLO, mock rest
pipeline = PredictionPipeline(
    detector=YOLODetector(weights_path=...),  # Real
    condition=MockConditionAssessor(),
    ocr=MockOCREngine(),
    material=MockMaterialEstimator(),
    embedding=MockEmbeddingEncoder(),
    ...
)

# M1.5: Real YOLO + CLIP
pipeline = PredictionPipeline(
    detector=YOLODetector(weights_path=...),
    condition=MockConditionAssessor(),
    ocr=MockOCREngine(),
    material=MockMaterialEstimator(),
    embedding=CLIPEncoder(weights_path=...),  # Real
    ...
)
```

**Dependency Injection Factory (`api/dependencies.py`):**
```python
@lru_cache(maxsize=1)
def get_pipeline() -> PredictionPipeline:
    settings = get_settings()
    detector = _build_detector(settings)
    if detector is not None and detector.is_ready:
        logger.info("Serving with real YOLO detector.")
        return build_detection_pipeline(detector=detector, ...)
    logger.info("Detector unavailable; serving mock pipeline.")
    return build_mock_pipeline(...)
```

### Readiness Contract

**`is_ready` Property:**
- **Mocks:** Always `True` (no dependencies, deterministic)
- **Real Adapters:** `True` only when artifact loaded and backend available

**Honest Degradation:**
```python
class YOLODetector(Detector):
    def _load(self, weights_path):
        resolved = self._resolve_weights(weights_path)
        if resolved is None:
            logger.warning("No detector artifact found.")
            return None  # Not ready
        yolo_cls = _import_yolo()
        if yolo_cls is None:
            logger.warning("ultralytics not installed.")
            return None  # Not ready
        try:
            model = yolo_cls(str(resolved))
        except Exception as exc:
            logger.warning(f"Failed to load: {exc}")
            return None  # Not ready
        return model  # Ready
    
    @property
    def is_ready(self) -> bool:
        return self._model is not None
```

### Testing Strategy

**Unit Tests (Inject Fakes):**
```python
def test_yolo_detector_aggregation():
    fake_model = FakeYOLOModel(boxes=[...], confidences=[...], classes=[...])
    detector = YOLODetector(model=fake_model)  # Inject
    result = detector.detect(images)
    assert result.device_type == "Laptop"
```

**Integration Tests (Mock Pipeline):**
```python
def test_predict_endpoint():
    response = client.post("/predict", files=[...])
    assert response.status_code == 200
    # Mock detector returns deterministic device_type
    assert response.json()["device_type"] == "Laptop"
```

**E2E Tests (Real Pipeline, CI Skips):**
```python
@pytest.mark.skipif(not torch_available(), reason="torch not installed")
def test_real_yolo_detector():
    detector = YOLODetector(weights_path="models/yolo.pt")
    assert detector.is_ready
    result = detector.detect(images)
    assert 0.0 <= result.confidence <= 1.0
```

---

## 18. Dependency Injection Strategy

The AI platform follows **constructor injection everywhere**: every service, adapter, and engine receives its collaborators as keyword-only constructor parameters with sensible defaults. No module reads global state or singletons directly.

### Injection Patterns

**1. Settings Injection:**
```python
class DatasetService:
    def __init__(self, settings: Settings, *, clock: Callable[[], datetime] = _utc_now):
        self._settings = settings
        self._clock = clock
        self._layout = DatasetLayout.from_settings(settings).ensure()
        self._metadata = MetadataGenerator.from_settings(settings)
```

**2. Model Component Injection:**
```python
class PredictionPipeline:
    def __init__(self, *,
                 detector: Detector,
                 condition: ConditionAssessor,
                 ocr: OCREngine,
                 material: MaterialEstimator,
                 embedding: EmbeddingEncoder,
                 ecoid_generator: EcoIDGenerator,
                 model_version: str):
        # All keyword-only, no defaults, caller wires them
```

**3. Training Collaborator Injection:**
```python
class BaseTrainer:
    def __init__(self, config: RunConfig, settings: Settings, *,
                 artifacts: ArtifactManager | None = None,
                 tracker: ExperimentTracker | None = None,
                 registry: ModelRegistry | None = None,
                 callbacks: list[Callback] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 commit: str | None = None):
        self.artifacts = artifacts or ArtifactManager.from_settings(settings)
        self.tracker = tracker or build_tracker(settings)
        self.registry = registry or ModelRegistry.from_settings(settings)
        self._clock = clock or datetime.now
        self._commit = commit
```

**4. Clock/Git Injection (Reproducibility):**
```python
# Production
service = DatasetService(settings, clock=lambda: datetime.now(UTC))

# Test
fixed_time = datetime(2026, 8, 5, 14, 0, 0, tzinfo=UTC)
service = DatasetService(settings, clock=lambda: fixed_time)
```

### Factory Functions (`api/dependencies.py`)

Centralized singleton construction with `@lru_cache(maxsize=1)`:

```python
@lru_cache(maxsize=1)
def get_pipeline() -> PredictionPipeline:
    settings = get_settings()
    detector = _build_detector(settings)
    if detector and detector.is_ready:
        return build_detection_pipeline(detector=detector, ...)
    return build_mock_pipeline(...)

@lru_cache(maxsize=1)
def get_registry() -> ModelRegistry:
    return ModelRegistry(get_settings().model_dir)

def get_validator(settings: Settings | None = None) -> ImageValidator:
    return ImageValidator(settings or get_settings())
```

### Test Overrides

```python
def test_pipeline_with_custom_settings():
    custom_settings = Settings(max_images=5, detector_weights="custom.pt")
    reset_dependency_caches()  # Clear @lru_cache
    
    with patch("api.dependencies.get_settings", return_value=custom_settings):
        pipeline = get_pipeline()
        assert pipeline is not None
```

### Design Rationale

- **No Global Singletons:** Services don't import `global_settings` or `global_registry`. They receive them.
- **Test Isolation:** Tests inject fakes without touching production code.
- **Reproducibility:** Injected clocks/Git hashes make runs deterministic.
- **Explicit Contracts:** Keyword-only params document what each service needs.

---

## 19. Error Handling

The AI platform uses a **typed domain exception hierarchy** (`exceptions.py`) that cleanly separates transport (HTTP) from domain logic. Every exception carries a stable machine-readable `code` and an HTTP status hint for the API layer.

### Exception Hierarchy

```python
class DeviceAIError(Exception):
    """Base class for all Device Intelligence Engine domain errors."""
    code: str = "DEVICE_AI_ERROR"
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    
    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

# Validation Errors (422 Unprocessable Entity)
class ValidationError(DeviceAIError): ...
class NoImagesProvidedError(ValidationError): ...
class TooManyImagesError(ValidationError): ...
class FileTooLargeError(ValidationError): ...
class UnsupportedMediaTypeError(ValidationError): ...
class CorruptedImageError(ValidationError): ...
class ImageDimensionError(ValidationError): ...

# Inference Errors (500/503)
class InferenceError(DeviceAIError): ...
class ModelNotLoadedError(InferenceError):
    http_status = HTTPStatus.SERVICE_UNAVAILABLE

# Dataset Errors (400/404/422)
class DatasetError(DeviceAIError): ...
class DatasetNotFoundError(DatasetError): ...
class EmptyDatasetError(DatasetError): ...
class AnnotationValidationError(DatasetError): ...
class UnsupportedExportFormatError(DatasetError): ...
class InvalidSplitError(DatasetError): ...

# Training Errors (400/404/500)
class TrainingError(DeviceAIError): ...
class ConfigError(TrainingError): ...
class ModelNotFoundError(TrainingError): ...
class ModelRegistryError(TrainingError): ...
class ExportError(TrainingError): ...
```

### Exception Translation (`api/errors.py`)

```python
def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers that translate domain errors to HTTP."""
    
    @app.exception_handler(DeviceAIError)
    async def handle_device_ai_error(request: Request, exc: DeviceAIError):
        request_id = request.headers.get("X-Request-ID")
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "request_id": request_id,
            },
        )
```

### Error Response Schema

```json
{
  "success": false,
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds the maximum allowed size of 10.0 MB.",
    "details": {
      "filename": "large_image.jpg",
      "size": 12582912,
      "max_file_size": 10485760
    }
  },
  "request_id": "req_a1b2c3d4"
}
```

### Design Rationale

- **No HTTP Imports in Domain:** `exceptions.py` only imports `http.HTTPStatus` (standard library). No FastAPI, no Starlette. The domain is transport-agnostic.
- **Stable Error Codes:** `code` is SCREAMING_SNAKE_CASE, never changes across releases, consumed by frontend for i18n/conditional UI.
- **Structured Details:** `details` dict carries context (filename, limits, paths) without parsing `message` strings.
- **HTTP Hint:** `http_status` suggests an appropriate status code; the API layer may override (e.g., rate-limiting wraps `TooManyImagesError` with 429).

---

## 20. Logging

The AI platform uses **Loguru** for structured logging with per-request correlation via `request_id`. Standard-library logging (Uvicorn/FastAPI) is redirected into Loguru through an `InterceptHandler`.

### Configuration (`configs/logging.py`)

**Two Sinks:**
1. **Console (default):** Colorized, human-friendly for development
2. **JSON (`JSON_LOGS=true`):** One JSON object per line for log shippers

```python
def configure_logging(settings: Settings) -> None:
    logger.remove()  # Clear existing handlers
    
    if settings.json_logs:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,  # Emit JSON
            backtrace=False,
            diagnose=False,
            enqueue=True,
        )
    else:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format=_console_format,  # Custom format with request_id
            backtrace=False,
            diagnose=False,
            enqueue=True,
        )
    
    # Redirect stdlib logging → Loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(name).handlers = [InterceptHandler()]
```

### Request Context Middleware (`api/middleware.py`)

**`RequestContextMiddleware`** adds per-request observability:

```python
class RequestContextMiddleware:
    async def __call__(self, scope, receive, send):
        request = Request(scope, receive=receive)
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        
        # Inject request_id into scope headers
        scope["headers"].append((b"x-request-id", request_id.encode()))
        
        start = time.perf_counter()
        
        with logger.contextualize(request_id=request_id):
            logger.bind(method=request.method, path=request.url.path).info("Request received")
            try:
                await self._app(scope, receive, send_wrapper)
            finally:
                latency_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.bind(latency_ms=latency_ms, response_status=status).info("Request completed")
```

**Logged Fields:**
- `request_id`: Unique correlation ID (echoed in `X-Request-ID` response header)
- `method`, `path`: HTTP method and URL path
- `latency_ms`: Request duration in milliseconds
- `response_status`: HTTP status code
- `image_count`: Number of uploaded images (logged in routes)
- `eco_id`: Generated EcoID (logged after prediction)

### Console Format

```
2026-08-06 14:23:45.123 | INFO     | device_ai.api.routes:predict:142 | req=req_a1b2c3d4 - Images validated
2026-08-06 14:23:45.567 | INFO     | device_ai.api.routes:predict:143 | req=req_a1b2c3d4 - Prediction complete
2026-08-06 14:23:45.789 | INFO     | device_ai.api.middleware:__call__:79 | req=req_a1b2c3d4 - Request completed
```

### JSON Format

```json
{
  "text": "Request completed",
  "record": {
    "elapsed": {"repr": "0:00:00.456789", "seconds": 0.456789},
    "level": {"name": "INFO", "no": 20},
    "message": "Request completed",
    "name": "device_ai.api.middleware",
    "time": {"repr": "2026-08-06 14:23:45.789+00:00", "timestamp": 1722953025.789},
    "extra": {
      "request_id": "req_a1b2c3d4",
      "method": "POST",
      "path": "/predict",
      "latency_ms": 456.78,
      "response_status": 200
    }
  }
}
```

---

## 21. Testing Strategy

The AI platform follows a **three-tier testing pyramid**: unit tests (fast, isolated, many), integration tests (service-level, real filesystem, moderate), and E2E tests (full HTTP stack, fewer).

### Unit Tests

**Strategy:** Inject fakes, mock no external state, test single units.

```python
# inference/test_yolo_detector.py
def test_yolo_detector_aggregation():
    """Test detection aggregation logic without loading real YOLO."""
    fake_result = FakeYOLOResult(
        boxes=FakeBoxes(
            xyxy=[[10, 20, 100, 200], [50, 60, 150, 250]],
            conf=[0.95, 0.87],
            cls=[0, 1]
        ),
        names={0: "laptop", 1: "smartphone"}
    )
    fake_model = FakeYOLOModel(results=[fake_result])
    detector = YOLODetector(model=fake_model)  # Inject
    
    result = detector.detect(images)
    assert result.device_type == "Laptop"
    assert result.confidence == 0.95
    assert len(result.detections) == 2
```

**Coverage:**
- Mock implementations (deterministic outputs)
- Real adapters' parsing/aggregation (inject fakes, skip torch-present paths)
- Pipeline orchestration (inject all-mock components)
- Dataset metadata extraction, splitting, augmentation (in-memory)
- Training callbacks, metrics, evaluator (inject fixed clock/Git)

### Integration Tests

**Strategy:** Real filesystem, real services, no HTTP. Test service orchestration.

```python
# dataset/test_service_integration.py
def test_dataset_service_end_to_end(tmp_path):
    """Test full dataset pipeline: import → split → augment → export."""
    settings = Settings(dataset_dir=tmp_path)
    service = DatasetService(settings)
    
    # Import images
    summary = service.import_images(source_root)
    assert summary.copied > 0
    
    # Analyze
    records = service.analyze()
    assert len(records) == summary.copied
    
    # Split
    split = service.split_dataset(train=0.7, val=0.2, test=0.1)
    assert split.train + split.val + split.test == len(records)
    
    # Export
    export_result = service.export_dataset("yolo", tmp_path / "exports")
    assert export_result.format == "yolo"
    assert (tmp_path / "exports/yolo/data.yaml").exists()
```

**Coverage:**
- DatasetService full pipeline
- DatasetVersionManager persistence
- ModelRegistry registration/resolution
- Experiment tracker JSON writes
- ArtifactManager directory creation

### E2E Tests (HTTP)

**Strategy:** TestClient (ASGI, no network), real pipeline, skip torch-heavy tests in CI.

```python
# api/test_predict_e2e.py
def test_predict_endpoint_success(client, sample_images):
    """Test /predict with mock pipeline end-to-end."""
    files = [("images", (f"img{i}.jpg", data, "image/jpeg")) for i, data in enumerate(sample_images)]
    response = client.post("/predict", files=files)
    
    assert response.status_code == 200
    body = response.json()
    assert body["eco_id"].startswith("ET-2026-")
    assert body["device_type"] in ["Laptop", "Smartphone", "Tablet", "Monitor", "Desktop"]
    assert 0.0 <= body["confidence"] <= 1.0
    assert 0.0 <= body["carbon_score"] <= 100.0

@pytest.mark.skipif(not torch_available(), reason="torch not installed")
def test_predict_with_real_yolo(client_with_real_models, sample_images):
    """Test /predict with real YOLO detector (CI skips when torch absent)."""
    response = client_with_real_models.post("/predict", files=...)
    assert response.status_code == 200
    # Real YOLO returns actual detections (non-deterministic confidence)
```

**Coverage:**
- `/predict` contract (mock pipeline)
- Error responses (validation errors, model-not-loaded)
- Request-ID correlation, latency logging
- Real-model E2E (marked `@pytest.mark.skipif(not torch_available())`)

### Test Execution

```bash
# All tests (base environment, mocks only)
cd intelligence/device_ai
PYTHONPATH=.. .venv/Scripts/python.exe -m pytest

# With coverage
PYTHONPATH=.. .venv/Scripts/python.exe -m pytest --cov=device_ai --cov-report=html

# Only unit tests (fast)
PYTHONPATH=.. .venv/Scripts/python.exe -m pytest -m "not integration"

# Skip torch-dependent tests
PYTHONPATH=.. .venv/Scripts/python.exe -m pytest -m "not torch"
```

---

## 22. Performance Considerations

The AI platform is designed for **production-grade inference** with careful attention to latency, throughput, and resource utilization.

### Inference Optimization

**Model Loading:**
- Heavy singletons (`PredictionPipeline`, `ModelRegistry`, `CLIPEncoder`, `YOLODetector`) are cached via `@lru_cache(maxsize=1)` and warmed at startup in `_lifespan` context manager
- Models loaded once per process, never per request
- GPU memory managed by backend (torch device placement configurable via `DETECTOR_DEVICE`, `CLIP_DEVICE`)

**Request Processing:**
- Image validation (MIME/size/resolution) runs before expensive decode
- Images decoded once (`LoadedImage.image`), metadata cached (sha256, dimensions)
- Per-component inference is independent (no cross-component blocking)
- Carbon score derived algebraically (no model call)

**Batching:**
- YOLODetector runs inference over the full request batch (e.g., 3 images → single YOLO call)
- CLIPEncoder mean-pools per-image embeddings into single vector
- MaterialEstimator uses nominal per-device-type profiles (no inference)

**Latency Budget (Mock Pipeline, No GPU):**
- Validation + decode: ~50–100ms per image (PIL decode + hash)
- Mock inference: <1ms (deterministic seed → pick from vocabulary)
- Total /predict latency: ~150–300ms for 3 images (network I/O dominant)

**Latency Budget (Real Pipeline, GPU):**
- YOLOv8 (640×640, batch=3): ~20–50ms on NVIDIA T4
- OpenCLIP ViT-B/32 (batch=3): ~30–60ms on NVIDIA T4
- EasyOCR (multi-language): ~100–200ms per image (CPU-bound)
- Total /predict latency: ~500–800ms for 3 images (OCR dominant)

### Throughput

**Concurrent Requests:**
- Uvicorn ASGI server (async request handling)
- Global Interpreter Lock (GIL) released during torch/numpy operations
- `Settings.workers` configures data-loader workers for training (not inference)

**Horizontal Scaling:**
- Stateless service (no session affinity required)
- Model artifacts shared via NFS/S3 (all replicas load same weights)
- Kubernetes Deployment with HPA (target: CPU 70%, replicas: 2–10)

**Bottlenecks:**
- **OCR:** EasyOCR is CPU-bound, single-threaded per request. Mitigation: defer OCR to async background job, return eco_id immediately
- **Image Decode:** PIL decode is CPU-bound. Mitigation: decode in thread pool
- **Model Loading:** Startup warm-up takes 5–10 seconds (YOLO + CLIP). Mitigation: readiness probe delay 15s

---

## 23. Extension Strategy

The AI platform is architected for **progressive capability expansion** without breaking existing contracts or requiring major refactors.

### Adding New Inference Components

**Pattern:** Implement the existing abstract protocol, inject via factory.

```python
# 1. Define new component (e.g., BrandClassifier for manufacturer recognition)
class BrandClassifier(BaseModel):
    name = "brand"
    
    @abstractmethod
    def classify(self, images: list[LoadedImage], device_type: str) -> str:
        """Return manufacturer/brand name."""

# 2. Implement mock (deterministic, zero-weight)
class MockBrandClassifier(BrandClassifier):
    def classify(self, images, device_type):
        return _pick(_BRANDS, _batch_seed(images))

# 3. Implement real adapter (guarded import, honest degradation)
class TorchBrandClassifier(BrandClassifier):
    def __init__(self, *, weights_path, model=None):
        self._model = model or self._load(weights_path)
    
    def classify(self, images, device_type):
        if not self.is_ready:
            raise ModelNotLoadedError("Brand classifier not loaded.")
        # Run inference...

# 4. Update PredictionPipeline to accept new component
class PredictionPipeline:
    def __init__(self, *, ..., brand_classifier: BrandClassifier | None = None):
        self._brand_classifier = brand_classifier
    
    def predict(self, images):
        # ...
        brand = self._brand_classifier.classify(images, detection.device_type) if self._brand_classifier else detection.brand
        # ...

# 5. Update factory (backward-compatible: default None)
def build_detection_pipeline(..., brand_classifier=None):
    return PredictionPipeline(..., brand_classifier=brand_classifier)
```

**Contract Stability:** Existing `/predict` response schema unchanged; `brand` field transitions from placeholder to real value.

---

### Adding New Model Types (Training)

**Pattern:** Subclass `BaseTrainer`, implement five hooks, register in `TrainerRegistry`.

```python
# 1. Implement trainer (e.g., YOLOTrainer for real detector training)
class YOLOTrainer(BaseTrainer):
    framework = "ultralytics"
    monitor_metric = "metrics/mAP50-95(B)"
    monitor_mode = "max"
    
    def build_model(self):
        from ultralytics import YOLO
        return YOLO(self.config.model_name)
    
    def train_loader(self):
        # Return Ultralytics DataLoader
    
    def val_loader(self):
        # Return Ultralytics DataLoader
    
    def train_step(self, model, batch):
        # Run one YOLO training step
        return {"loss": float(results.loss)}
    
    def validation_step(self, model, batch):
        # Run one YOLO validation step
        return {"mAP": float(results.box.map)}

# 2. Register trainer
from device_ai.training.core.registry import default_registry
default_registry.register("yolo", YOLOTrainer)

# 3. Configure run
# configs/yolo.yaml
trainer: yolo
model_name: device-detector
training:
  batch_size: 16
  epochs: 100
  image_size: 640
```

### Adding New Export Formats

**Pattern:** Implement `ModelExporter` protocol, add to `_EXPORTERS` registry.

```python
# 1. Implement exporter (e.g., TensorRT)
class TensorRTExporter:
    export_format = "tensorrt"
    
    def export(self, model, destination, **kwargs):
        if not _tensorrt_available():
            return SkippedExport("tensorrt", "TensorRT not installed.")
        # Perform TRT conversion
        return ExportRecord("tensorrt", "exported", str(destination))

# 2. Register
_EXPORTERS["tensorrt"] = TensorRTExporter
```

### Adding New Dataset Formats

**Pattern:** Implement export function, add to `DatasetExporter` format registry.

```python
# 1. Implement exporter (e.g., TFRecord)
def export_tfrecord(records, splits, output_dir, class_names):
    import tensorflow as tf
    # Write TFRecord files
    return ExportResult(format="tfrecord", location=str(output_dir))

# 2. Register
from device_ai.dataset.exporter import DatasetExporter
DatasetExporter.register_format("tfrecord", export_tfrecord)
```

---

## 24. Current Limitations

The following limitations are **known and documented** as of milestone M3.3:

### Inference

1. **Brand Recognition:** `DetectionResult.brand` is a placeholder ("Unknown") until a manufacturer classification model ships (future sprint). The field exists in the response schema for forward compatibility.

2. **Condition Assessment:** `MockConditionAssessor` returns deterministic labels. A real condition classifier (fine-tuned vision transformer on wear/damage annotations) is planned but not yet implemented.

3. **Material Estimation:** `MockMaterialEstimator` uses nominal per-device-type profiles. A real material-composition model (trained on X-ray/CT scans + teardown data) is research-dependent and deferred to post-MVP.

4. **OCR Accuracy:** EasyOCR is CPU-bound and struggles with low-contrast, skewed, or heavily worn labels. Mitigation: preprocessing (adaptive thresholding, deskewing) planned for M1.7.

5. **Barcode Robustness:** OpenCV barcode reader requires high-quality images. QR codes with damage or occlusion often fail. Mitigation: try multiple decoding libraries (pyzbar, ZXing).

### Training

6. **No Concrete Trainers Ship:** `BaseTrainer` is abstract; no `YOLOTrainer`, `CLIPTrainer`, or `OCRTrainer` ships in M1.3 (milestone scope: lifecycle only, no models trained). Future milestones add concrete implementations.

7. **Distributed Training:** Not supported. Single-GPU or CPU-only. Multi-GPU (DDP/FSDP) requires `torch.distributed` integration, planned for post-MVP scale.

8. **Hyperparameter Search:** No built-in HPO (Optuna/Ray Tune). Manual grid/random search via CLI `--override` flags. Automated search planned for M1.8.

### Dataset

9. **Annotation Tool:** No built-in labeling UI. Expects pre-annotated YOLO `.txt` files. Integration with LabelImg/CVAT/LabelStudio planned for M1.7.

10. **Advanced Augmentation:** Albumentations covers geometric/photometric. Mosaic, MixUp, CutMix (YOLO-native) require dataset-format-aware augmentation, planned for M1.7.

### Infrastructure

11. **Model Versioning:** `ModelRegistry` is local JSON. No S3/GCS backend, no remote registry (MLflow Model Registry requires server). Cloud integration planned for production deployment.

12. **GPU Memory Management:** No automatic batch-size tuning, no gradient checkpointing. OOM on large models/batches requires manual `batch_size` reduction.

13. **Inference Batching:** `/predict` processes one request at a time. No request coalescing or dynamic batching (TorchServe/Triton pattern). Planned for high-throughput production.

---

## 25. Future AI Roadmap

The AI platform is designed for **progressive capability expansion** aligned with the EcoTrace India product roadmap and IEEE YESIST 2026 milestones.

### Phase 1: Foundation (M1.1–M1.6, Complete)

- ✅ Mock-to-real model abstraction layer
- ✅ YOLOv8 device detector (M1.4)
- ✅ OpenCLIP visual embeddings (M1.5)
- ✅ EasyOCR text extraction (M1.6)
- ✅ Dataset intelligence pipeline
- ✅ Training orchestration (BaseTrainer, ModelRegistry, experiment tracking)
- ✅ Evaluation & export framework

### Phase 2: Model Accuracy & Coverage (Post-M1.6)

**Brand Recognition (M1.7):**
- Train multi-class manufacturer classifier (Dell/HP/Apple/Samsung/Lenovo/Asus/Acer/Sony/LG/Panasonic)
- Fine-tune on branded product images + logo detection
- Replace `DetectionResult.brand` placeholder with real predictions

**Condition Assessment (M1.8):**
- Annotate wear/damage dataset (scratches, dents, cracks, screen damage, battery swelling)
- Train vision transformer classifier (Excellent/Good/Fair/Poor with confidence)
- Replace `MockConditionAssessor` with real model

**Material Composition (Research-Dependent):**
- Requires X-ray/CT scan dataset + teardown annotations (academic/industry partnership)
- Train material-composition estimator (aluminum/copper/PCB/battery/plastic fractions)
- Alternative: rule-based lookup table calibrated from teardown studies

**OCR Robustness (M1.7):**
- Preprocessing pipeline: adaptive thresholding, deskewing, contrast enhancement
- Multi-library fallback: EasyOCR → PaddleOCR → Tesseract
- Specialized serial-number regex patterns per manufacturer

### Phase 3: Production Hardening (MVP → Production)

**Inference Optimization:**
- Dynamic batching (TorchServe/Triton pattern): coalesce requests within 50ms window
- Model quantization (INT8) for faster CPU inference
- TensorRT export for GPU deployment
- ONNX Runtime for cross-platform serving

**Horizontal Scaling:**
- Kubernetes Deployment (HPA: target CPU 70%, replicas 2–10)
- Model artifact caching (Redis): share embeddings across replicas
- Async OCR offload: return eco_id immediately, complete OCR in background job

**Monitoring & Observability:**
- Prometheus metrics: `/predict` latency (p50/p95/p99), throughput (req/s), model load time
- Grafana dashboards: per-component latency breakdown, error rates, GPU utilization
- Distributed tracing (OpenTelemetry): correlate requests across backend/AI/blockchain

### Phase 4: Advanced AI Capabilities (Post-MVP)

**Multi-Modal Fusion:**
- Combine visual features (CLIP) + text features (BERT on OCR output) for improved device classification
- Attention-based fusion: learn to weight visual vs textual signals per device category

**Active Learning:**
- Flag low-confidence predictions (confidence < 0.6) for human review
- Retrain models monthly on corrected labels
- Prioritize rare device types (tablets, e-readers, smartwatches) for annotation

**Anomaly Detection:**
- Detect out-of-distribution devices (medical equipment, industrial electronics mistakenly uploaded)
- Flag for manual review rather than auto-classifying

**Explainability:**
- Grad-CAM heatmaps: visualize which image regions drove device-type prediction
- SHAP values: explain material-composition estimates
- Surface explanations in admin dashboard for trust/debugging

### Phase 5: Research Extensions (Academic Collaboration)

**Component-Level Detection:**
- YOLO trained on component-level annotations (RAM, SSD, CPU, GPU, battery, motherboard)
- Per-component recoverability scoring (M2.2 enhancement)

**Lifecycle-Aware Inference:**
- Temporal models: track device condition degradation over multiple uploads
- Predict remaining useful life (RUL) based on visual wear + usage metadata

**Circular Economy Optimization:**
- Reinforcement learning agent: recommend optimal refurbishment/recycling path
- Multi-objective optimization: maximize material recovery + minimize environmental impact

---

## Summary

This document specifies the **AI Platform Architecture** for the EcoTrace India Device Intelligence Engine (DIE), reverse-engineered from the implementation at `intelligence/device_ai`. The architecture is:

1. **Modular:** Abstract protocols (Detector, ConditionAssessor, OCREngine, MaterialEstimator, EmbeddingEncoder) with mock and real implementations behind stable interfaces.

2. **Injectable:** Every service, adapter, and engine receives collaborators via constructor injection (settings, models, registries, trackers, clocks, Git commits).

3. **Degradable:** Missing artifacts or uninstalled backends leave components "not ready" rather than raising. The service degrades to mocks with logged warnings.

4. **Reproducible:** Timestamps, Git commits, and RNG seeds are injected for deterministic, testable runs.

5. **Observable:** Structured logging (Loguru), per-request correlation (request_id), latency tracking, and experiment tracking (JSON/MLflow).

6. **Extensible:** New inference components, training models, export formats, and dataset formats are added via protocol implementation + registry registration.

7. **Production-Ready:** ASGI server (Uvicorn), async request handling, horizontal scaling (Kubernetes HPA), performance budgets, and honest error reporting.

**Out of Scope (Documented Elsewhere):** Web frontend, Backend REST APIs, PostgreSQL, Blockchain ledger, Digital Passport, Trust catalogue, Lifecycle state machine, Decision Intelligence (see §2).

---

**Document End**
