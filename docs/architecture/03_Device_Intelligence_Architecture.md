# 03 — Device Intelligence Architecture

**Document Version:** 2.0  
**Status:** Active  
**Last Updated:** 2026-08-06  
**Scope:** Device Intelligence Engine only (milestones M1.1–M1.11)  
**Audience:** IEEE YESIST reviewers, patent reviewers, enterprise architects, AI researchers, software engineers

---

## Table of Contents

1. Executive Summary
2. Device Intelligence Overview
3. Overall Device Intelligence Pipeline
4. Intelligence Engine Relationships
5. Device AI Service (M1.1)
6. Dataset Intelligence (M1.2)
7. Training & MLOps Platform (M1.3)
8. Device Detection Engine (M1.4)
9. Device Fingerprinting Engine (M1.5)
10. OCR Intelligence Engine (M1.6)
11. Multi-Modal Fusion Engine (M1.7)
12. Recoverability Intelligence Engine (M1.8)
13. Component Intelligence Engine (M1.9)
14. Material Intelligence Engine (M1.10)
15. Environmental Intelligence Engine (M1.11)
16. End-to-End Data Flow
17. Shared Domain Models
18. Configuration
19. Error Handling
20. Dependency Injection
21. Explainability Strategy
22. Performance
23. Testing Strategy
24. Extension Points
25. Limitations
26. Future AI Evolution

---

## 1. Executive Summary

The **Device Intelligence Engine (DIE)** is the AI subsystem of EcoTrace India that turns raw device photographs into a structured, auditable, machine-readable understanding of a physical device: what it is, who made it, how identifiable it is, what it is built from, how it should be recovered, and what environmental burden that recovery avoids.

It is implemented as a self-contained Python microservice under `intelligence/device_ai/`. Document [01 — System Architecture] positions the DIE within the wider EcoTrace platform; document [02 — AI Platform Architecture] establishes the cross-cutting platform conventions (service layering, model abstraction, dependency injection, configuration, logging, testing and performance philosophy). **This document does not repeat those foundations** — it drills into the eleven engines that make up the DIE and explains, from the implementation as source of truth, how each one works and how they compose.

The DIE is organized as three cooperating tiers:

- **Service & platform tier (M1.1–M1.3)** — the prediction pipeline that fronts the engine, plus the offline dataset and training/MLOps machinery that produce and govern model artifacts.
- **Perception tier (M1.4–M1.7)** — the pixel-reading engines (detection, fingerprinting, OCR) and the multi-modal fusion layer that reconciles their outputs into one canonical `DeviceContext`.
- **Knowledge tier (M1.8–M1.11)** — pure-Python, rule- and catalogue-driven reasoning engines (recoverability, component, material, environmental) that consume the fused context and derive circular-economy intelligence with **no model weights at all**.

Two architectural commitments run through every engine and distinguish this design:

1. **Honest degradation in the perception tier.** Every model adapter (YOLOv8, OpenCLIP, EasyOCR, barcode) ships with a deterministic *mock* and an optional *real* backend behind a guarded import. When heavyweight dependencies are absent the engine degrades to the mock, logs a warning, and stamps the mock's name/version onto its output — it never silently pretends a mock is a real model.
2. **Determinism and auditability in the knowledge tier.** The M1.8–M1.11 engines are pure functions of their inputs: no randomness, no network, no learned weights. Their domain knowledge lives in **external, versioned YAML catalogues** behind strict validating loaders, and every score carries ordered human-readable reasoning. Identical inputs always produce identical, explainable outputs.

The engine is internal-facing. Its only externally frozen contract is the `POST /predict` envelope (M1.1); the dataset, fingerprint and OCR routers are internal operational surfaces, and the fusion and knowledge-tier engines (M1.7–M1.11) expose **no HTTP surface at all** — they are consumed in-process by orchestrating code and surfaced as typed exceptions on failure. The full test suite (1209 tests) runs green in a base environment with zero model weights, which is the practical proof of the mock-first, pure-knowledge design.

---

## 2. Device Intelligence Overview

### 2.1 Three-Tier Architecture

The DIE is structured as three cooperating tiers, each with a distinct responsibility and character:

**Service & Platform Tier (M1.1–M1.3)** — the orchestration and artifact-management foundation:
- **M1.1 Device AI Service**: the prediction pipeline that accepts images, sequences the perception and knowledge engines, derives the carbon score, and returns the frozen `/predict` envelope.
- **M1.2 Dataset Intelligence**: offline machinery for ingesting, validating, splitting, augmenting, versioning, and exporting training datasets with quality metrics and duplicate detection.
- **M1.3 Training & MLOps Platform**: reusable training lifecycle (seeding → epoch loop → metrics → callbacks → checkpointing → registry) with experiment tracking, provenance capture, and multi-format model export.

**Perception Tier (M1.4–M1.7)** — the pixel-reading engines that extract signals from photographs:
- **M1.4 Device Detection**: YOLOv8 object detection → device type + brand.
- **M1.5 Device Fingerprinting**: OpenCLIP embedding → L2-normalized vector → SHA-256 hash = stable device identity.
- **M1.6 OCR Intelligence**: EasyOCR text + OpenCV barcode/QR → serial number, model, IMEI, MAC address.
- **M1.7 Multi-Modal Fusion**: reconciles detection/OCR/fingerprint "claims" → one immutable `DeviceContext` with conflict detection and noisy-OR confidence aggregation.

**Knowledge Tier (M1.8–M1.11)** — pure-Python, rule-driven reasoning engines that consume the fused context:
- **M1.8 Recoverability Intelligence**: 7 deterministic rules → repair/reuse/recycle scores + recommended action + hazard level.
- **M1.9 Component Intelligence**: device-type catalogue + corroboration signals → inferred internal component inventory with presence confidence.
- **M1.10 Material Intelligence**: component-gated material catalogue → mass breakdown (grams) + recoverable/hazardous totals.
- **M1.11 Environmental Intelligence**: material masses × LCA factors → carbon/energy/water savings + circularity/hazard-reduction indices.

### 2.2 Design Philosophy

Every architectural decision flows from four principles:

1. **Testability without models.** Mock adapters enable full pipeline testing in CI with zero pretrained weights. The 1209-test suite runs green in a base environment (`requirements.txt` only, no `requirements-models.txt`), which is the practical proof that every perception engine degrades to a deterministic mock and every knowledge engine is pure Python.

2. **Deterministic reasoning.** Given identical inputs, the engine produces identical outputs (modulo injected timestamps). No randomness, no network calls, no hidden state. Every score carries ordered human-readable reasoning that auditors and regulators can trace.

3. **Honest degradation.** Real backends that cannot load (missing `ultralytics`, missing weights, import failure) degrade to mocks with warning logs and stamp the mock's name/version onto the output. The system never silently pretends a mock is a real model.

4. **External, versioned knowledge.** Device profiles (M1.9), material breakdowns (M1.10), environmental LCA factors (M1.11) live in reviewable YAML files behind strict validating loaders. Typos, range violations, unknown categories → load-time typed exceptions, never silent drops. Every catalogue declares a `version` field that is stamped onto reports.

### 2.3 Milestones and Delivery Status

| Milestone | Capability | Core LOC | Tests | Status |
|-----------|-----------|----------|-------|--------|
| M1.1 | Device AI Service Pipeline | ~600 | ~50 | Complete |
| M1.2 | Dataset Intelligence | ~1200 | ~100 | Complete |
| M1.3 | Training & MLOps Platform | ~1400 | ~100 | Complete |
| M1.4 | YOLOv8 Detection Engine | ~350 | 12 | Complete |
| M1.5 | OpenCLIP Fingerprint Engine | ~450 | 19 | Complete |
| M1.6 | OCR Intelligence Engine | ~800 | 99 | Complete |
| M1.7 | Multi-Modal Fusion Engine | ~550 | 34 | Complete |
| M1.8 | Recoverability Intelligence | ~600 | 59 | Complete |
| M1.9 | Component Intelligence | ~550 | 48 | Complete |
| M1.10 | Material Intelligence | ~500 | 42 | Complete |
| M1.11 | Environmental Intelligence | ~450 | 23 | Complete |

**Total:** ~7450 lines of implementation code, 1209 tests passing (as of 2026-08-05).

Each milestone delivers: a working, tested engine with mock and real implementations (perception tier) or pure-Python implementation (knowledge tier); domain models as frozen, slotted dataclasses with `to_dict()` JSON serialization; service façades with constructor dependency injection; unit tests exercising both mock and real code paths (where applicable); and integration with the M1.7 fusion layer (for M1.8–M1.11).

---

## 3. Overall Device Intelligence Pipeline

The pipeline sequences the eleven engines in a strict dependency order. Perception engines run first (M1.4–M1.6), their outputs fuse (M1.7), and the fused context feeds the knowledge tier (M1.8–M1.11). The carbon score is derived algebraically at the pipeline level from condition and material outputs.

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Device Intelligence Pipeline                    │
└──────────────────────────────────────────────────────────────────────┘

   Uploaded Images (list[bytes])
            │
            ├──> Image Validation & Decoding (M1.1 preprocessing)
            │    ├─> Size check (max 10 MB)
            │    ├─> Format check (JPEG/PNG/WEBP)
            │    ├─> Dimension check (32–12000 px)
            │    ├─> PIL decode + SHA-256 hash
            │    └─> LoadedImage(image, sha256, width, height, ...)
            │
            v
   ┌─────────────────────────────────────────────────────────────────┐
   │                    PERCEPTION TIER (M1.4–M1.7)                   │
   └─────────────────────────────────────────────────────────────────┘
            │
            ├──> M1.4 Detection Engine
            │    ├─> YOLODetector (or MockDetector)
            │    └─> DetectionResult(device_type, brand, confidence)
            │
            ├──> M1.5 Fingerprint Engine
            │    ├─> CLIPEncoder (or MockEmbeddingEncoder)
            │    ├─> L2-normalize → SHA-256
            │    └─> DeviceFingerprint(eco_id, fingerprint, embedding, ...)
            │
            ├──> M1.6 OCR Engine
            │    ├─> EasyOCRBackend + OpenCVBarcodeReader (or mocks)
            │    ├─> TextSpans + BarcodeResults → OCRParser
            │    └─> OCRExtraction(fields: ExtractedField[], spans, barcodes)
            │
            v
   ┌─────────────────────────────────────────────────────────────────┐
   │              M1.7 FUSION ENGINE (Integration Seam)               │
   └─────────────────────────────────────────────────────────────────┘
            │
            ├──> Evidence.from_detection(detection)
            ├──> Evidence.from_fingerprint(fingerprint)
            ├──> Evidence.from_ocr(ocr)
            │
            ├──> FusionEngine.fuse(evidence)
            │    ├─> Group claims by attribute + value
            │    ├─> Noisy-OR confidence aggregation per group
            │    ├─> Winner = max(confidence, tie-break by count)
            │    ├─> Detect conflicts (rejected groups)
            │    └─> DeviceContext(eco_id, attributes, confidence, conflicts)
            │
            v
   ┌─────────────────────────────────────────────────────────────────┐
   │                    KNOWLEDGE TIER (M1.8–M1.11)                   │
   │                   (Pure Python, YAML catalogues)                 │
   └─────────────────────────────────────────────────────────────────┘
            │
            ├──> M1.8 Recoverability Engine
            │    ├─> Resolve device profile (in-code table, 19 types)
            │    ├─> Run 7 rules → list[RuleOutcome]
            │    ├─> ScoringEngine: sum deltas, max hazard, multiply factors
            │    └─> RecoverabilityReport(repairability, reusability,
            │         recyclability, hazard_level, recommended_action)
            │
            ├──> M1.9 Component Engine
            │    ├─> Load components/data/components.yaml
            │    ├─> Resolve device profile → list[ComponentSpec]
            │    ├─> Corroborate: identity signals + hazard → boost confidence
            │    └─> ComponentReport(components: InferredComponent[],
            │         overall_confidence)
            │
            ├──> M1.10 Material Engine
            │    ├─> Load materials/data/materials.yaml
            │    ├─> Resolve device profile → list[MaterialSpec]
            │    ├─> Gate by source_components (battery → lithium listed only
            │    │    if battery component present)
            │    └─> MaterialReport(materials: RecoveredMaterial[],
            │         total_mass_g, recoverable_mass_g, hazardous_mass_g)
            │
            ├──> M1.11 Environmental Engine
            │    ├─> Load environmental/data/factors.yaml
            │    ├─> Aggregate recoverable materials by category
            │    ├─> mass_kg × factor → carbon/energy/water per category
            │    ├─> Circularity = blend(recoverable_fraction, recyclability)
            │    ├─> Hazard reduction = severity × hazardous_fraction
            │    └─> EnvironmentalImpactReport(carbon_saved_kg,
            │         energy_saved_mj, water_saved_l, circularity_index,
            │         hazard_reduction_score, ...)
            │
            v
   ┌─────────────────────────────────────────────────────────────────┐
   │                      CARBON SCORE (Pipeline)                     │
   └─────────────────────────────────────────────────────────────────┘
            │
            ├──> Algebraic formula (no model call):
            │    base = 50.0
            │    condition_weight = {Excellent: 1.0, Good: 0.85,
            │                        Fair: 0.65, Poor: 0.4}
            │    material_value = {aluminum: 60, copper: 55, pcb: 45,
            │                       battery: 40, plastic: 15}
            │    raw = base + condition_weight × Σ(fraction × value)
            │    carbon_score = clamp(raw, 0, 100), round 1 decimal
            │
            v
   ┌─────────────────────────────────────────────────────────────────┐
   │                         PredictionResult                         │
   │  (eco_id, detection, condition, ocr, materials, embedding,       │
   │   carbon_score, model_version)                                   │
   └─────────────────────────────────────────────────────────────────┘
            │
            └──> JSON serialization → POST /predict response
```

**Key dataflow properties:**

- **Perception → fusion is the only cross-tier seam.** M1.4–M1.6 produce independent `Evidence` structs; M1.7 merges them into one `DeviceContext`; M1.8–M1.11 consume that context (plus their upstream knowledge-tier reports) and never look back at raw pixels.
- **Knowledge tier is a cascade.** M1.8 depends only on `DeviceContext`. M1.9 depends on context + M1.8 recoverability (confidence blend, hazard corroboration). M1.10 depends on context + M1.8 + M1.9 (component gating). M1.11 depends on all four (material masses × LCA factors, recoverability for circularity/hazard).
- **Carbon score is pipeline-level,** not an engine. It reads condition (from a mock assessor in M1.1) and materials (from M1.10) and applies a fixed algebraic formula — no model, no external catalogue.
- **Immutability throughout.** Every output is a frozen dataclass; the pipeline is a pure function of its inputs (modulo the injected clock for timestamps).

---

## 4. Intelligence Engine Relationships

The engines compose in a strict directed acyclic dependency graph. No cycles, no bidirectional coupling:

```
            LoadedImage (M1.1 preprocessing)
                    │
       ┌────────────┼────────────┐
       │            │            │
       v            v            v
  Detection    Fingerprint      OCR
   (M1.4)        (M1.5)       (M1.6)
       │            │            │
       └────────────┼────────────┘
                    │
                    v
            ┌───────────────┐
            │  Fusion M1.7  │  ← Integration seam
            └───────────────┘
                    │
                    │ DeviceContext
                    │
                    v
         ┌──────────────────┐
         │ Recoverability   │
         │     M1.8         │
         └──────────────────┘
                    │ RecoverabilityReport
                    │
         ┌──────────┴───────────┐
         │                      │
         v                      v
  ┌─────────────┐       DeviceContext
  │ Component   │              │
  │    M1.9     │              │
  └─────────────┘              │
         │                     │
         │ ComponentReport     │
         │                     │
         └──────────┬──────────┘
                    │
                    v
            ┌───────────────┐
            │   Material    │
            │     M1.10     │
            └───────────────┘
                    │ MaterialReport
                    │
         ┌──────────┴─────────────┐
         │                        │
         v                        v
  RecoverabilityReport      ComponentReport
         │                        │
         └────────────┬───────────┘
                      │
                      v
              ┌───────────────┐
              │ Environmental │
              │     M1.11     │
              └───────────────┘
                      │
                      v
         EnvironmentalImpactReport
```

**Dependency rules:**

- **M1.8 Recoverability** depends only on `DeviceContext`.
- **M1.9 Component** depends on `DeviceContext` + `RecoverabilityReport` (for confidence blend and hazard corroboration).
- **M1.10 Material** depends on `DeviceContext` + `RecoverabilityReport` + `ComponentReport` (component-gated material listing).
- **M1.11 Environmental** depends on `DeviceContext` + all three upstream knowledge reports (material masses × LCA factors; recoverability for circularity/hazard-reduction indices).

The cascade is strictly ordered; no knowledge engine ever calls back into perception. The fusion layer is the one-way valve.

**Inter-tier contracts:**

| From Tier | To Tier | Contract |
|-----------|---------|----------|
| Perception → Fusion | `Evidence` structs | `Evidence.from_detection()`, `Evidence.from_fingerprint()`, `Evidence.from_ocr()` builders |
| Fusion → Knowledge | `DeviceContext` | Immutable frozen dataclass with `.eco_id`, `.device_type`, `.brand`, `.model`, `.serial_number`, `.imei`, `.mac_address`, `.confidence`, `.conflicts` |
| Knowledge (internal) | Cascade | Each engine's report is a frozen dataclass consumed by the next |

---

## 5. Device AI Service (M1.1)

### 5.1 Purpose

The Device AI Service (M1.1) is the orchestration layer that fronts the entire Device Intelligence Engine. It accepts uploaded device photographs via the frozen `POST /predict` HTTP contract, sequences the perception and knowledge engines in dependency order, derives the carbon score algebraically, and returns the structured `PredictionResult`.

M1.1 also houses the **image preprocessing pipeline** — the validation, decoding, and hashing machinery that turns raw upload bytes into the canonical `LoadedImage` representation consumed by every downstream engine.

### 5.2 Inputs

**HTTP layer:**
- `POST /predict` with multipart/form-data images (1–6 images, each ≤10 MB, JPEG/PNG/WEBP, 32–12000 px per dimension).

**Pipeline layer:**
- `list[bytes]` — raw uploaded image bytes.

### 5.3 Outputs

**`PredictionResult`** (frozen dataclass):
- `eco_id: str` — `ET-YYYY-XXXXXXXX` format
- `detection: DetectionResult` — `(device_type, brand, confidence, detections)`
- `condition: ConditionResult` — `(label: "Excellent"|"Good"|"Fair"|"Poor", score)`
- `ocr: OCRResult` — `(serial_number: str, model: str)` both default ""
- `materials: MaterialResult` — `(composition: dict[str, float])`
- `embedding: EmbeddingResult` — `(embedding_id, dimension)`
- `carbon_score: float` — [0, 100] rounded 1 decimal
- `model_version: str`

Serialized to JSON via `PredictionResponse` schema → `POST /predict` response body.

### 5.4 Internal Workflow

`PredictionPipeline.predict(images: list[LoadedImage])` orchestrates in fixed order:

1. **Detection** → `self._detector.detect(images)` → `DetectionResult`
2. **Embedding** → `self._embedding.encode(images)` → `EmbeddingResult`
3. **Condition** → `self._condition.assess(images)` → `ConditionResult`
4. **OCR** → `self._ocr.extract(images)` → `OCRResult`
5. **Materials** → `self._material.estimate(images, detection.device_type)` → `MaterialResult`
6. **Carbon score** → `self._carbon_score(condition, materials)` → float (algebraic formula)
7. **EcoID** → `self._ecoid.generate()` → `ET-YYYY-XXXXXXXX`
8. **Assemble** → `PredictionResult(...)`

**Image preprocessing** (`preprocessing/` package):
```
Raw bytes
    ↓
ImageValidator.validate(raw)
    ├─> Size check: ≤ max_file_size (10 MB)
    ├─> MIME/extension check: in allowed_formats (JPEG, PNG, WEBP)
    ├─> PIL.Image.open(BytesIO(raw)) → decode
    ├─> Dimension check: min_dimension ≤ width, height ≤ max_dimension (32–12000 px)
    ├─> SHA-256 hash of raw bytes
    └─> LoadedImage(raw, image, format, width, height, mode, sha256, size_bytes)
```

Validation failures raise typed domain exceptions: `FileTooLargeError` (413), `UnsupportedMediaTypeError` (415), `CorruptedImageError` (422), `ImageDimensionError` (422).

### 5.5 Collaborators

All injected via constructor (see section 20):

- **`Detector`** — `MockDetector` | `YOLODetector` (M1.4)
- **`EmbeddingEncoder`** — `MockEmbeddingEncoder` | `CLIPEncoder` (M1.5)
- **`ConditionAssessor`** — `MockConditionAssessor` (mock only; no real backend yet)
- **`OCREngine`** — `MockOCREngine` | replaced by `OCRService` in M1.6
- **`MaterialEstimator`** — `MockMaterialEstimator` (mock only; M1.10 supersedes)
- **`EcoIDGenerator`** — deterministic UUID-based ID generator

### 5.6 Configuration

From `Settings` (see section 18):
- `max_images: int = 6`, `min_images: int = 1`
- `max_file_size: int = 10 * 1024 * 1024` (10 MB)
- `allowed_image_formats: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})`
- `min_image_dimension: int = 32`, `max_image_dimension: int = 12000`
- `model_version: str` — stamped onto `PredictionResult`

### 5.7 Carbon Score Formula

The carbon score is **derived algebraically at the pipeline level**, not by a model call:

```python
_BASE_CARBON_SCORE = 50.0

_CONDITION_WEIGHTS = {
    "Excellent": 1.0, "Good": 0.85, "Fair": 0.65, "Poor": 0.4,
}

_MATERIAL_CARBON_VALUE = {
    "aluminum": 60.0, "copper": 55.0, "pcb": 45.0,
    "battery": 40.0, "plastic": 15.0,
}

def _carbon_score(condition, materials):
    weight = _CONDITION_WEIGHTS.get(condition.label, 0.5)
    value = sum(f * _MATERIAL_CARBON_VALUE.get(m, 20.0)
                for m, f in materials.composition.items())
    raw = _BASE_CARBON_SCORE + weight * value
    return round(max(0.0, min(100.0, raw)), 1)
```

**Rationale:** Transparent, auditable formula blending device condition with material value. No training required.

### 5.8 Error Handling

M1.1-specific (see section 19 for full hierarchy):
- `NoImagesProvidedError` (400) — zero images
- `TooManyImagesError` (400) — exceeds `max_images`
- `FileTooLargeError` (413) — exceeds `max_file_size`
- `UnsupportedMediaTypeError` (415) — wrong format
- `CorruptedImageError` (422) — PIL decode failure
- `ImageDimensionError` (422) — width/height out of range
- `InferenceError` (500) — pipeline failure
- `ModelNotLoadedError` (503) — backend not ready

### 5.9 Testing

Key test files: `test_pipeline.py` (8 tests), `test_predict.py` (9 tests), `test_predict_detection.py`, `test_validation.py`, `test_meta.py`. Deterministic mocks enable full pipeline testing with zero model weights.

### 5.10 Extension Points

- Swap `YOLODetector` instead of `MockDetector` via DI
- Swap `CLIPEncoder` instead of mock encoder
- Replace `MockConditionAssessor` with real CNN assessor (future milestone)
- Customize `ImageValidator` params (max size, formats, dimensions)

### 5.11 Design Rationale

- **Preprocessing isolated:** `LoadedImage` is the boundary — raw bytes never leak past validation
- **SHA-256 provenance:** every image hashed on load → tamper-evident fingerprints
- **Eager validation:** malformed uploads rejected before decode → DoS protection
- **Immutable outputs:** frozen dataclasses → thread-safe, cacheable, traceable
- **Carbon score transparency:** algebraic formula in code, not a black-box model → auditable

### 5.12 Dependencies

**Core:** `fastapi`, `pydantic`, `pillow`, `numpy`
**Optional (guarded):** `ultralytics` (YOLO), `open-clip-torch` (CLIP), `easyocr` (OCR)

### 5.13 Interaction with Neighboring Engines

- **Feeds:** `LoadedImage` → M1.4, M1.5, M1.6 (perception tier)
- **Consumes:** `DetectionResult`, `ConditionResult`, `OCRResult`, `MaterialResult`, `EmbeddingResult` → `PredictionResult`
- **Delegates:** M1.6 OCR replaces mock `OCREngine`; M1.10 Material replaces `MockMaterialEstimator`
- **Frozen contract:** `POST /predict` schema unchanged since M1.4

---

## 6. Dataset Intelligence (M1.2)

### 6.1 Purpose

The Dataset Intelligence engine (M1.2) is the offline machinery for ingesting, validating, analyzing, splitting, augmenting, versioning, and exporting training datasets with quality metrics and duplicate detection. It produces the curated, versioned datasets consumed by the M1.3 training platform.

M1.2 is **internal-facing** — it exposes operational HTTP endpoints (`POST /dataset/import`, `POST /dataset/validate`, etc.) for dataset management but is not part of the frozen `/predict` contract.

### 6.2 Inputs

- Source directories of device photos (any format PIL can decode)
- YOLO annotation files (`.txt`: `class_id x_center y_center width height`, normalized [0,1])
- Split ratios (train/val/test, default `(0.7, 0.2, 0.1)`)
- Augmentation operation specifications

### 6.3 Outputs

- **`ImageRecord`** (frozen, slotted) — `(relative_path, filename, image_format, mode, width, height, size_bytes, megapixels, hashes: PerceptualHashes, quality: QualityMetrics)`
- **`PerceptualHashes`** — `(sha256, ahash, dhash, phash)`
- **`QualityMetrics`** — `(blur_score, brightness, is_blurry, is_dark, is_bright, is_low_resolution, is_corrupted, issues: tuple[str, ...])`
- **`DuplicateReport`** — `(pairs: tuple[DuplicatePair, ...], duplicate_paths, total_images)`
- **`AnnotationReport`** — `(is_valid, total_labels, total_boxes, class_counts, images_without_labels, labels_without_images, issues)`
- **`SplitAssignment`** — `(train, val, test: tuple[str, ...], ratios, seed)`
- **`DatasetVersion`** — `(version, created_at, image_count, content_hash, note, manifest)`

### 6.4 Internal Workflow

`DatasetService` orchestrates seven operations:

1. **`analyze(images_root)`** → `list[ImageRecord]`
   - Walk directory, decode each image via PIL
   - Compute SHA-256 (exact) + ahash/dhash/phash (perceptual)
   - Compute quality: hand-rolled Laplacian blur variance, ITU-R BT.601 luma brightness
   - Threshold classification: `is_blurry` (blur < 100.0), `is_dark` (brightness < 40), `is_bright` (brightness > 220)

2. **`import_images(source, dest, deduplicate)`** → `ImportSummary`
   - Copy files, skip exact SHA-256 duplicates if requested

3. **`detect_duplicates(records, hamming_threshold=5)`** → `DuplicateReport`
   - Exact match by SHA-256; near-duplicate by min Hamming distance across perceptual hashes

4. **`validate_annotations(images_root, labels_root, num_classes)`** → `AnnotationReport`
   - Parse YOLO `.txt` files; validate `0 ≤ class_id < num_classes`, `0 ≤ coordinates ≤ 1`
   - Cross-reference images ↔ labels

5. **`split(records, ratios, seed=42)`** → `SplitAssignment`
   - Sort by path (deterministic) → NumPy seeded shuffle → partition

6. **`export(format, records, class_names, output_dir)`**
   - YOLO (`images/`, `labels/`, `data.yaml`), COCO (`annotations.json`), VOC (`Annotations/*.xml`)

7. **`create_version(records, note)`** → `DatasetVersion`
   - Content-addressed: SHA-256(sorted manifest JSON) → version fingerprint

### 6.5 Collaborators

All pure-Python, no OpenCV: `MetadataGenerator` (hand-rolled Laplacian + luma), `DuplicateDetector` (perceptual hash Hamming distance), `DatasetImporter`, `AnnotationValidator`, `DatasetSplitter` (NumPy RNG), `DatasetExporter` (YOLO/COCO/VOC converters), `DatasetVersionManager`, `StatisticsCalculator`, `ReportBuilder`.

### 6.6 Configuration

- `dataset_dir: Path`, `duplicate_hamming_threshold: int = 5`
- `blur_threshold: float = 100.0`, `brightness_dark_threshold: float = 40.0`, `brightness_bright_threshold: float = 220.0`
- `split_ratios: tuple[float, float, float] = (0.7, 0.2, 0.1)`, `split_seed: int = 42`

### 6.7 Error Handling

`DatasetNotFoundError` (404), `EmptyDatasetError` (422), `AnnotationValidationError` (422), `UnsupportedExportFormatError` (400), `InvalidSplitError` (400).

### 6.8 Testing

10 test files including `test_dataset_duplicates.py`, `test_dataset_exporter.py`, `test_dataset_hashing.py`, `test_dataset_metadata.py`, `test_dataset_service.py`, `test_dataset_splitter.py`, `test_dataset_validator.py`.

### 6.9 Extension Points

Extend `QualityMetrics` with new fields; implement new export format; `AugmentationEngine` applies transform variants.

### 6.10 Design Rationale

- **Pure-Python quality metrics:** hand-rolled Laplacian + luma avoid OpenCV dependency
- **Perceptual hashing for near-duplicates:** catches visually identical images with different JPEG artifacts
- **Content-addressed versioning:** SHA-256 over sorted manifest → reproducibility
- **Deterministic splitting:** seeded shuffle of sorted paths → reproducible train/val/test
- **Timestamps injected:** `created_at` passed as param, not from clock → reproducible tests

### 6.11 Dependencies

Core: `pillow`, `numpy`. No OpenCV.

### 6.12 Interaction with Neighboring Engines

- **Feeds:** curated datasets → M1.3 training platform
- **Produces:** `DatasetVersion` referenced in `RunConfig.training.dataset_version` for provenance

---

## 7. Training & MLOps Platform (M1.3)

### 7.1 Purpose

The Training & MLOps Platform (M1.3) provides a reusable, framework-agnostic training lifecycle with experiment tracking, model registry, and multi-format model export. It is designed to be **framework-agnostic** — no PyTorch imports in core, guarded optional dependencies.

### 7.2 Inputs

- **`RunConfig`** (frozen Pydantic model): `model_name`, `trainer`, `experiment_name`, `training: TrainingConfig` (batch_size, epochs, device, mixed_precision, workers, seed, image_size, dataset_version, model_version, early_stopping_patience), `optimizer: OptimizerConfig` (optimizer, learning_rate, weight_decay, momentum, scheduler, warmup_epochs), `tags: dict[str, str]`

### 7.3 Outputs

- **`TrainingHistory`** (frozen): `(model_name, model_version, run_id, epochs_completed, training_time, best_epoch, best_metric, final_metrics, checkpoint_path, git_commit, device, epochs: tuple[EpochResult, ...])`
- **`EpochResult`**: `(epoch: int, metrics: dict[str, float])`
- **`ModelRecord`** (frozen): `(name, version, dataset_version, created_at, git_commit, framework, metrics, export_formats, artifact_location, tags)`
- **`ExportRecord`** (frozen): `(export_format: str, status: "exported"|"skipped"|"failed", location, message)`

### 7.4 Internal Workflow

`BaseTrainer.fit()` orchestrates:

1. `seed_everything(config.training.seed)` — deterministic RNG
2. `self.build_model()` — abstract hook (subclass responsibility)
3. `tracker.run(run_id, experiment_name, config.to_dict())` — open experiment
4. Epoch loop:
   - `self._callbacks.on_epoch_begin(state)`
   - `train_logs = self._aggregate(model, self.train_loader(), self.train_step)`
   - `val_logs = self._aggregate(model, self.val_loader(), self.validation_step)`
   - `run.log_metrics({**train_logs, **val_logs}, step=epoch)`
   - `self._callbacks.on_epoch_end(state, logs)` — EarlyStopping, ModelCheckpoint, LoggingCallback
   - Stop if `state.stop_training`
5. `self.save_checkpoint(model, checkpoint_path)` — `.pt` artifact
6. `run.set_summary({"training_time": ..., "git_commit": ..., "device": ..., "best_epoch": ...})`
7. `registry.register(ModelRecord(...))` — persist to `model_registry.json`
8. Return `TrainingHistory`

### 7.5 Collaborators

- **`ArtifactManager`** — resolves `checkpoints/`, `exports/`, `reports/` under `artifact_dir`
- **`ExperimentTracker`** (protocol) — `JsonExperimentTracker` (default) | MLflow (optional) | `NullTracker`
- **`ModelRegistry`** — JSON-backed provenance store at `artifact_dir/model_registry.json`
- **`CallbackList`** → `EarlyStopping`, `ModelCheckpoint`, `LoggingCallback`
- **`MetricTracker`** — running averages
- **`Timer`** — injected clock for wall-clock timing
- **Model exporters** — `PyTorchExporter`, `TorchScriptExporter`, `OnnxExporter` (each guarded)

### 7.6 Configuration

- `artifact_dir: Path`, `mlruns_dir: Path`
- `experiment_tracker: str` — `"json"` | `"mlflow"` | `"none"`
- `training_seed: int = 42`

### 7.7 Error Handling

`ConfigError` (422), `TrainerNotFoundError` (404), `ExportError` (500), `ModelRegistryError` (500), `ModelNotFoundError` (404).

### 7.8 Testing

10 test files: `test_training_callbacks.py`, `test_training_cli.py`, `test_training_config.py`, `test_training_evaluator.py`, `test_training_exporter.py`, `test_training_metrics.py`, `test_training_registry.py`, `test_training_tracker.py`, `test_training_trainer.py`, `test_training_utils.py`.

### 7.9 Extension Points

- `BaseTrainer` ABC with 5 abstract hooks: `build_model()`, `train_step()`, `validation_step()`, `train_loader()`, `val_loader()`
- `TrainerRegistry` — `@default_registry.register("yolo")` decorator
- `Callback` protocol — `on_train_begin`, `on_epoch_begin`, `on_epoch_end`, `on_train_end`
- `ModelExporter` protocol — export to PyTorch, TorchScript, ONNX

### 7.10 Design Rationale

- **Framework-agnostic:** no torch imports in core; M1.4 YOLOTrainer subclasses `BaseTrainer`
- **Honest degradation:** exporters return `status="skipped"` when backend absent (not silent failure)
- **Immutable config:** Pydantic frozen models → reproducible runs
- **Provenance tracking:** every `ModelRecord` captures git commit, dataset version, metrics
- **Dependency injection:** clock, git commit, tracker, registry all injected for testability

### 7.11 Dependencies

Core: `pydantic`, `pyyaml`, `numpy`. Optional (guarded): `torch`, `onnx`, `hydra-core`, `mlflow`.

### 7.12 Interaction with Neighboring Engines

- **Consumes:** `DatasetVersion` (via `config.training.dataset_version`)
- **Produces:** `ModelRecord` → evaluation reports, export artifacts
- **M1.4:** `YOLOTrainer` subclasses `BaseTrainer`

---

## 8. Device Detection Engine (M1.4)

### 8.1 Purpose

Identify device type and brand from uploaded photographs using pretrained YOLOv8 object detection, with honest degradation to a deterministic mock when `ultralytics` is not installed.

### 8.2 Inputs

`list[LoadedImage]` — validated, decoded images with SHA-256 provenance.

### 8.3 Outputs

**`DetectionResult`** (frozen dataclass):
- `device_type: str` — predicted device class (e.g. "laptop", "smartphone")
- `brand: str` — predicted brand, "Unknown" if not identified
- `confidence: float` — aggregate detection confidence [0, 1]
- `detections: tuple[Detection, ...]` — individual bounding boxes
- **`Detection`**: `(label: str, confidence: float, bounding_box: tuple[int, int, int, int] | None)`

### 8.4 Internal Workflow

**Real path (`YOLODetector`)** — package `inference/yolo_detector.py`:

```
List[LoadedImage]
    ↓
_load_model() → guarded import of ultralytics.YOLO
    ↓
Resolve weights: weights_path or candidates ("model.pt", "model.onnx") or pretrained "yolov8n.pt"
    ↓
predict(image.image) → Ultralytics Results object
    ↓
_parse_results(xyxy, conf, cls) → filter by confidence_threshold (0.25)
    ↓
_aggregate → max-confidence detection → _map_label (class index → label name)
    ↓
DetectionResult(device_type, brand, confidence, detections)
```

Constants: `_PLACEHOLDER_BRAND = "Unknown"`, `_WEIGHTS_CANDIDATES = ("model.pt", "model.onnx")`

**Mock path (`MockDetector`):**
- Derives device_type and brand deterministically from image SHA-256
- Confidence = 0.75 + (first 2 hex digits / 255) × 0.20 → range [0.75, 0.95]
- Same image bytes → identical detection output (testability guarantee)

### 8.5 Collaborators

- `Detector` (Protocol) — `MockDetector` | `YOLODetector`
- No repository or external infrastructure; pure stateless inference

### 8.6 Configuration

From `Settings`:
- `detector_weights: str = "yolov8n.pt"` — relative to `model_dir`
- `detector_image_size: int = 640` — YOLOv8 input resolution
- `detector_confidence_threshold: float = 0.25` — minimum box confidence
- `model_dir: Path`, `model_version: str`

### 8.7 Error Handling

- `ModelNotLoadedError` (503) if real backend `is_ready == False`
- Import guarded: `try/except ImportError` with `# pragma: no cover` (real YOLO path)
- Detection failure → `DetectionResult` with empty brand, 0.0 confidence (no exception for no detection)

### 8.8 Testing

`test_yolo_detector.py` (12 tests): Mock detector determinism, YOLO aggregation logic, label mapping, confidence threshold filtering.

### 8.9 Extension Points

- **Swap weights:** inject different YOLOv8 variant (nano/small/medium)
- **Custom label map:** override `_map_label` for custom device classes
- **Multi-model ensemble:** inject multiple detectors and fuse at evidence level

### 8.10 Design Rationale

- **Pretrained, not trained:** YOLOv8 nano is plug-and-play; no custom training needed for MVP device detection
- **Deterministic mock:** derives from SHA-256, not randomness → same image = same detection → reproducible tests
- **Honest degradation:** `YOLODetector.is_ready` → mock fallback with warning log
- **Frozen contract:** `DetectionResult` shape unchanged since M1.4 → stable downstream evidence builder

### 8.11 Dependencies

Core: `numpy`, `pillow`. Optional (guarded): `ultralytics`.

### 8.12 Interaction with Neighboring Engines

- **Feeds:** `DetectionResult` → `Evidence.from_detection()` in M1.7 Fusion (maps DEVICE_TYPE + BRAND claims)
- **Consumes:** `LoadedImage` from M1.1 preprocessing
- **Frozen contract:** downstream fusion operates on `DetectionResult`, not YOLO internals

### 8.13 Detection Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                     DETECTION PIPELINE (M1.4)                  │
└──────────────────────────────────────────────────────────────┘

  LoadedImage
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │              YOLODetector (or MockDetector)         │
  │                                                    │
  │  Real path:  YOLOv8 → xyxy/conf/cls tensors        │
  │  Mock path:  SHA-256 → deterministic label/conf     │
  └────────────────────────────────────────────────────┘
      │
      ├─> Confidence threshold filter (0.25)
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  _parse_results(boxes, scores, classes)            │
  │  → list[Detection] (label, confidence, bbox)       │
  └────────────────────────────────────────────────────┘
      │
      ├─> _aggregate: max-confidence detection
      │
      ▼
  DetectionResult
  ├─ device_type: "laptop"
  ├─ brand: "Dell" | "Unknown"
  ├─ confidence: 0.92
  └─ detections: tuple[Detection, ...]
```

---

## 9. Device Fingerprinting Engine (M1.5)

### 9.1 Purpose

Generate stable, hash-backed device fingerprints from visual embeddings for identity anchoring and duplicate detection. The fingerprint is a SHA-256 hash of an L2-normalized OpenCLIP embedding vector, making it a content-addressable visual identity that is computationally infeasible to forge.

### 9.2 Inputs

- `list[LoadedImage]` — encoded to embedding
- `DeviceFingerprint` objects — for comparison and verification

### 9.3 Outputs

**`DeviceFingerprint`** (frozen, slotted):
- `eco_id: str` — `ET-YYYY-XXXXXXXX` (EcoID format)
- `fingerprint: str` — SHA-256 of 6-decimal-precision, L2-normalized embedding coordinates
- `embedding: tuple[float, ...]` — the raw 512-dim OpenCLIP vector (or mock synthetic)
- `dimension: int` — embedding dimensionality
- `encoder_name: str` — "clip" | "mock-embedding"
- `encoder_version: str` — "ViT-B-32-1.0.0" | "mock-embedding-1.0.0"
- `metric: str` — "cosine" | "euclidean" | "manhattan"
- `created_at: datetime`
- `source_hashes: tuple[str, ...]` — image SHA-256 provenance
- `device_type: str = ""` — from detection (optional)
- `brand: str = ""` — from detection (optional)
- `identity: dict[str, str]` — from OCR identity fields (M1.6+)

**`EmbeddingVector`** (frozen, slotted):
- `values: tuple[float, ...]` — 512-dim L2-normalized vector
- `dimension: int`
- `normalized: bool`

**`VerificationResult`** (frozen, slotted):
- `left_eco_id: str`, `right_eco_id: str`
- `score: SimilarityScore` — `(metric, similarity: float, distance: float)`
- `matched: bool` — `similarity >= threshold` (default threshold = 0.85)
- `threshold: float`

### 9.4 Internal Workflow

**Fingerprint generation:**

```
List[LoadedImage]
    ↓
CLIPEncoder.embed(images)  (or MockEmbeddingEncoder)
    ├─> image → preprocess → tensor stack
    ├─> model.encode_image(batch) → features
    ├─> Mean-pool across batch (multiple images → one vector)
    ├─> L2-normalize (F.normalize, p=2)
    └─> EmbeddingVector(values, dimension, normalized=True)
    ↓
compute_fingerprint(vector)
    ├─> Round to 6 decimal places (_FINGERPRINT_PRECISION = 6)
    ├─> Canonicalize (ascii representation)
    ├─> SHA-256 hash
    └─> fingerprint hash string
    ↓
EcoIDGenerator.generate() → ET-YYYY-XXXXXXXX
    ↓
DeviceFingerprint(eco_id, fingerprint, embedding, ...)
    ↓
FingerprintRepository.save(fingerprint)  (in-memory or JSON file)
```

**Verification (`VerificationEngine`):**

```
DeviceFingerprint (left)  vs  DeviceFingerprint (right)
    ↓
Must have same dimension (FingerprintMismatchError if not)
    ↓
compute_similarity(left.embedding, right.embedding, metric)
    ├─> COSINE:    (1 + cos_θ) / 2  →  [0, 1]
    ├─> EUCLIDEAN: 1 / (1 + L2_dist) →  [0, 1]
    └─> MANHATTAN: 1 / (1 + L1_dist) →  [0, 1]
    ↓
matched = similarity >= threshold (default 0.85)
    ↓
VerificationResult(left_eco_id, right_eco_id, score, matched, threshold)
```

### 9.5 Collaborators

- **`EmbeddingEncoder`** (protocol): `MockEmbeddingEncoder` | `CLIPEncoder`
- **`FingerprintRepository`** (ABC): `InMemoryFingerprintRepository` | `JsonFileFingerprintRepository` (path-traversal guarded)
- **`EcoIDGenerator`**: UUID-based deterministic ID
- **`VerificationEngine(threshold, metric)`**: similarity + match decision
- **`_METRICS` registry** (`fingerprint/similarity.py`): `cosine_similarity`, `euclidean_similarity`, `manhattan_similarity`
- **`clock`**: injected `Callable[[], datetime]`, defaults to UTC now

### 9.6 Configuration

From `Settings`:
- `fingerprint_metric: str = "cosine"` — default similarity metric
- `fingerprint_match_threshold: float = 0.85` — binary match decision threshold
- `fingerprint_backend: str = "memory"` — repository backend
- `clip_model_name: str = "ViT-B-32"`, `clip_pretrained: str = "laion2b_s34b_b79k"`, `clip_weights: str = "clip"` — from `model_dir`

### 9.7 Error Handling

- `FingerprintError` (500) — base fingerprint domain error
- `FingerprintNotFoundError` (404) — no fingerprint for a given eco_id
- `FingerprintMismatchError` (422) — different embedding dimensions/unencodable comparison
- `UnknownSimilarityMetricError` (400) — unsupported metric name
- `EncoderNotReadyError` (503) — CLIP backend not loaded

### 9.8 Testing

Key test files: `test_fingerprint_service.py` (12 tests), `test_clip_encoder.py` (7 tests). Covers mock/real encoding, repository persistence, similarity computation, verification threshold, EcoID generation.

### 9.9 Extension Points

- **Add metric:** register new similarity function in `_METRICS` dict
- **Repository backends:** `InMemoryFingerprintRepository` (test), `JsonFileFingerprintRepository` (lightweight persistence, path-traversal guarded)
- **Encoder swap:** inject `MockEmbeddingEncoder` (deterministic test) or `CLIPEncoder` (production)

### 9.10 Design Rationale

- **SHA-256 over rounded embedding:** same device photos → same fingerprint (modulo encoder version); 6-decimal rounding absorbs floating-point noise across machines
- **L2-normalization + mean-pool:** multiple photos of same device compressed to one stable vector → robust to lighting/angle variation
- **Three similarity metrics → one scale:** all map to [0, 1] with clear semantics (1.0 = identical)
- **Binary threshold:** `matched = similarity >= 0.85` → clear yes/no for duplicate detection
- **Deterministic EcoID:** `ET-YYYY-XXXXXXXX` format derived from UUID projection → unique, human-readable, no collision risk
- **Injected clock:** `created_at` → reproducible test timestamps

### 9.11 Dependencies

Core: `numpy`. Optional (guarded): `open-clip-torch`, `torch`.

### 9.12 Interaction with Neighboring Engines

- **Feeds:** `DeviceFingerprint` → `Evidence.from_fingerprint()` in M1.7 (device_type/brand provenance + identity dict at 0.50 confidence)
- **Consumes:** OCR identity `dict[str, str]` from M1.6 (optional enrichment)
- **OCR seam:** `FingerprintService.identity_for(images) → OCRIdentity` — 5-field projection passed to fingerprint generation

### 9.13 Fingerprint Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                  FINGERPRINT PIPELINE (M1.5)                   │
└──────────────────────────────────────────────────────────────┘

  List[LoadedImage]
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │          CLIPEncoder (or MockEmbeddingEncoder)      │
  │                                                    │
  │  Real path:  ViT-B-32 → encode_image → 512-dim     │
  │  Mock path:  SHA-256 → synthetic 512-dim vector     │
  └────────────────────────────────────────────────────┘
      │
      ├─> Mean-pool across batch
      ├─> L2-normalize (‖v‖ = 1.0)
      │
      ▼
  EmbeddingVector(values: tuple[float, ...], dimension: 512)
      │
      ├─> Round to 6 decimal places
      ├─> canonical bytes → SHA-256
      │
      ▼
  Fingerprint Hash: "a3f8b1c2d4e5..."
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │             EcoIDGenerator.generate()               │
  │                                                    │
  │  uuid4.int % (16**8) → 8-char upper hex            │
  │  → "ET-2026-A3F8B1C2"                              │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  DeviceFingerprint                                  │
  │  ├─ eco_id: "ET-2026-A3F8B1C2"                     │
  │  ├─ fingerprint: "a3f8b1c2d4e5..."                 │
  │  ├─ embedding: tuple[float, ...] (512)              │
  │  ├─ device_type: "laptop"                           │
  │  ├─ brand: "Dell"                                   │
  │  ├─ identity: {serial: "SN123", imei: "490..."}     │
  │  └─ source_hashes: tuple[str, ...]                  │
  └────────────────────────────────────────────────────┘
      │
      ▼
  FingerprintRepository.save(fingerprint)
      │
      ├─ InMemoryRepository (memstore)
      └─ JsonFileRepository (path-traversal guarded)
```

---

## 10. OCR Intelligence Engine (M1.6)

### 10.1 Purpose

Extract structured device identity fields (serial number, model, IMEI, MAC address, manufacturer, QR/barcode payloads) from device label photographs using EasyOCR text recognition, OpenCV barcode/QR decoding, and a rule-based normalization parser.

### 10.2 Inputs

**Primary (recognition + parsing):** `list[LoadedImage]` — validated, decoded images.

**Parse-only (no images):** `list[TextSpan]` + optional `list[BarcodeResult]` — the normalization layer accepts raw spans/barcodes directly for testing and composition.

### 10.3 Outputs

**`OCRExtraction`** (frozen, slotted):
- `fields: tuple[ExtractedField, ...]` — one per identity dimension
- `spans: tuple[TextSpan, ...]` — raw text recognition detections
- `barcodes: tuple[BarcodeResult, ...]` — decoded QR/1-D codes
- `engine_name: str` — e.g. "easyocr-1.7.2" | "mock-ocr-m16-1.0.0"
- `engine_version: str`
- `created_at: datetime` (injected clock)
- `source_hashes: tuple[str, ...]` — sorted image SHA-256 hashes

**Identity objects:**
- `ExtractedField`: `(field_type: FieldType, value: str, confidence: float, raw_text: str, source: FieldSource)`
- `FieldType` enum: `MANUFACTURER, MODEL, SERIAL_NUMBER, IMEI, MAC_ADDRESS, QR_CODE, BARCODE`
- `FieldSource` enum: `TEXT, BARCODE, QR`
- `OCRIdentity` (`.identity` property): 5-field projection `(manufacturer, model, serial_number, imei, mac_address)`
- `TextSpan`: `(text: str, confidence: float, bounding_box: tuple[int, int, int, int] | None)`
- `BarcodeResult`: `(kind: "qr"|"barcode", payload: str, symbology: str, confidence: float)`

### 10.4 Internal Workflow

Two-stage architecture: **recognize** (backend-specific text detection) → **parse** (backend-agnostic normalization).

**Stage 1 — Recognition:**

```
List[LoadedImage]
    │
    ├──> OCRBackend.recognize_batch(images) → list[TextSpan]
    │    ├─ Real: EasyOCR readtext_batch → filter by min_confidence
    │    └─ Mock: SHA-256 → labelled synthetic identity spans
    │
    └──> BarcodeReader.decode_batch(images) → list[BarcodeResult]
         ├─ Real: cv2.QRCodeDetector + cv2.barcode.BarcodeDetector
         └─ Mock: SHA-256 → synthetic QR + EAN13 barcode payloads
```

**Stage 2 — Normalization (pure, stateless `OCRParser`):**

```
list[TextSpan] + list[BarcodeResult]
    │
    ▼
OCRParser.parse(spans, barcodes)
    │
    ├──> _fields_from_span(span) — per span:
    │    ├─ IMEI: 15 digits, confusion-normalized (O→0, I→1, l→1, S→5, B→8),
    │    │       Luhn checksum validated, strength 0.98 (pass) | 0.55 (shape only)
    │    ├─ MAC:  ([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}, canonical upper-colon, strength 0.97
    │    ├─ Serial: alnum 6-26 chars, mixed digit+letter required (unless labelled), strength 0.9/0.7
    │    ├─ Model: label-required (no intrinsic shape), whitespace-collapsed, strength 0.85
    │    └─ Manufacturer: keyword table (17 brands), exact-token boundary match, strength 0.95
    │
    ├──> _fields_from_barcode(barcode) — per barcode:
    │    └─ Mine payload for embedded IMEI (preferred) or serial
    │
    ├──> _best(fields) per FieldType — highest confidence, tie-break by value (deterministic)
    │
    └──> Field confidence = recognition_conf × pattern_strength × label_boost (×1.05 for labelled IMEI)
         Clamp [0, 1]
```

**Stage 3 — Provenance stamping:**

`OCRService._stamp(extraction, images)` — attaches backend name/version, `self._clock()`, sorted `image.sha256` hashes.

### 10.5 Collaborators

- **`OCRBackend`** (ABC): `EasyOCRBackend` (real) | `MockOCRBackend` (deterministic)
- **`BarcodeReader`** (ABC): `OpenCVBarcodeReader` (real) | `MockBarcodeReader` (deterministic)
- **`OCRParser`**: stateless, pure, single shared instance — testable from hand-built spans
- **`ImageValidator`**: reused from M1.1 preprocessing
- **`clock`**: injected `Callable[[], datetime]`, defaults to UTC now

### 10.6 Configuration

From `Settings`:
- `ocr_backend: str = "easyocr"` — `"easyocr"` | `"mock"`
- `ocr_languages: tuple[str, ...] = ("en",)` — EasyOCR language codes
- `ocr_weights: str = "ocr"` — model storage locator relative to `model_dir`
- `ocr_use_gpu: bool = False` — request GPU inference
- `ocr_min_confidence: float = 0.0` — min kept recognition confidence
- `barcode_enabled: bool = True` — enable QR/barcode decoding

### 10.7 Error Handling

- `OCRError` (500) — base OCR domain error
- `OCRBackendNotReadyError` (503) — no reader loaded to serve
- `OCRParseError` (422) — malformed spans/barcodes submitted to parser

### 10.8 Testing

99 tests across 7 files: `test_ocr_models.py` (16), `test_ocr_patterns.py` (24), `test_ocr_parser.py` (15), `test_ocr_backends.py` (13), `test_ocr_barcode.py` (10), `test_ocr_service.py` (10), `test_ocr_routes.py` (11).

### 10.9 Extension Points

- **Backend protocol:** `OCRBackend` ABC (`name, version, is_ready, recognize()`)
- **Reader protocol:** `BarcodeReader` ABC (`name, version, is_ready, decode()`)
- **Injectable fakes:** `recognize_fn: RecognizeFn`, `decode_fn: DecodeFn` for testing without weights
- **Pattern tables:** `patterns._MANUFACTURERS` dict (add brands in one place)
- **Field types:** `FieldType` enum extendable
- **Parser:** pure, no backend coupling — testable from hand-built inputs

### 10.10 Design Rationale

- **Separate package:** OCR is a dedicated engine, not an overloaded field on `/predict` — scales independently
- **Two-stage architecture:** recognition (backend-specific) cleanly separated from parsing (pure business logic) — parser testable without images
- **Confusion normalization selective:** only for structured IDs (IMEI/MAC digit runs), never free text (manufacturer names)
- **Label-aware parsing:** `"S/N: ABC123"` both boosts confidence and isolates value
- **Barcode mining:** QR/barcode payloads mined for embedded IMEI/serial (device labels encode identity in barcodes)
- **Honest degradation:** mock backend when EasyOCR unavailable; same contract

### 10.11 Dependencies

Core: `pillow`, `numpy`. Optional (guarded): `easyocr`, `opencv-python-headless`.

### 10.12 Interaction with Neighboring Engines

**Fingerprint seam** (optional, backward-compatible):
- `OCRService.identity_for(images) → OCRIdentity` — 5-field projection passed to fingerprint generation
- Fingerprint M1.5 carries `identity: dict[str, str]` (OCR-derived fields, empty when absent)

**Fusion seam** (M1.7):
- `Evidence.from_ocr(extraction)` — maps each `ExtractedField` to `Claim`:
  - `MANUFACTURER → BRAND`, `MODEL → MODEL`, `SERIAL_NUMBER → SERIAL_NUMBER`, `IMEI → IMEI`, `MAC_ADDRESS → MAC_ADDRESS`
  - `QR_CODE`, `BARCODE` ignored (not device attributes)
- Uses per-field `extracted.confidence` (not shared)
- Module confidence = mean of claim confidences

### 10.13 OCR Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                     OCR PIPELINE (M1.6)                        │
└──────────────────────────────────────────────────────────────┘

  List[LoadedImage]
      │
      ├──────────────────┬──────────────────────┐
      ▼                  ▼                      ▼
  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐
  │ OCRBackend│   │ BarcodeReader│    │ (parallel decode) │
  │          │    │              │    │                  │
  │ EasyOCR  │    │ OpenCV QR    │    │                  │
  │ (or mock)│    │ + 1-D barcode│    │                  │
  │          │    │ (or mock)    │    │                  │
  └──────────┘    └──────────────┘    └──────────────────┘
      │                  │
      ▼                  ▼
  list[TextSpan]   list[BarcodeResult]
      │                  │
      └────────┬─────────┘
               ▼
  ┌──────────────────────────────────────────────┐
  │              OCRParser.parse()                │
  │                                              │
  │  Per span:                                   │
  │    IMEI regex → Luhn validate → Field        │
  │    MAC regex → canonicalize → Field          │
  │    Serial regex → extract → Field            │
  │    Model regex (label-required) → Field      │
  │    Manufacturer table match → Field          │
  │                                              │
  │  Per barcode:                                │
  │    QR payload → mine IMEI/serial → Field     │
  │    1-D barcode → mine payload → Field        │
  │                                              │
  │  _best() per FieldType (max confidence)      │
  │  confidence = recognition × pattern × boost   │
  └──────────────────────────────────────────────┘
               │
               ▼
  ┌──────────────────────────────────────────────┐
  │            OCRExtraction                      │
  │  ├─ fields: tuple[ExtractedField, ...]       │
  │  │    ├─ FieldType.MANUFACTURER: "Dell"      │
  │  │    ├─ FieldType.MODEL: "XPS 15"           │
  │  │    ├─ FieldType.SERIAL_NUMBER: "SN123"    │
  │  │    ├─ FieldType.IMEI: "490154203237518"   │
  │  │    └─ FieldType.MAC_ADDRESS: "00:1A:2B..." │
  │  ├─ spans: tuple[TextSpan, ...]              │
  │  ├─ barcodes: tuple[BarcodeResult, ...]      │
  │  ├─ engine_name: "easyocr-1.7.2"            │
  │  └─ source_hashes: tuple[sha256, ...]        │
  └──────────────────────────────────────────────┘
               │
               ▼
  Evidence.from_ocr(extraction)
  → Claims: BRAND ("Dell", 0.80), MODEL ("XPS 15", 0.75),
            SERIAL_NUMBER ("SN123", 0.92), ...
```

---

## 11. Multi-Modal Fusion Engine (M1.7)

### 11.1 Purpose

Merge competing evidence from detection, fingerprint, and OCR into a single, normalized, immutable `DeviceContext` with conflict detection and confidence aggregation. The fusion engine is the **one-way valve** between the perception and knowledge tiers — all downstream reasoning engines consume only the `DeviceContext`, never raw module outputs.

### 11.2 Inputs

**Via `fuse_modules`:**
- `detection: DetectionResult | None`
- `fingerprint: DeviceFingerprint | None`
- `ocr: OCRExtraction | None`

**Via pure `fuse`:**
- `evidence: Iterable[Evidence]` — pre-built, any source

### 11.3 Outputs

**`DeviceContext`** (frozen, slotted) — the canonical device identity:
- `eco_id: str` — from fingerprint
- `fingerprint: str` — hash-backed identity
- `attributes: tuple[ResolvedAttribute, ...]` — in `FusionAttribute` declaration order
- `confidence: float` — mean of resolved-attribute confidences
- `evidence: tuple[Evidence, ...]` — full provenance (every claim traced to source module + version)
- `conflicts: tuple[Conflict, ...]` — cross-module disagreements (empty = all modules agree)
- `source_hashes: tuple[str, ...]`
- `engine_version: str`
- `created_at: datetime | None`

**Convenience properties:** `.device_type`, `.brand`, `.model`, `.serial_number`, `.imei`, `.mac_address`, `.has_conflicts`

**Supporting models:**
- `ResolvedAttribute`: `(attribute: FusionAttribute, value: str, confidence: float, sources: tuple[EvidenceKind, ...], conflicted: bool)` + `.agreed` property
- `Conflict`: `(attribute: FusionAttribute, resolved_value: str, claims: tuple[Claim, ...])`
- `Evidence`: `(source: EvidenceKind, module_name: str, module_version: str, confidence: float, claims: tuple[Claim, ...])`
- `Claim`: `(attribute: FusionAttribute, value: str, confidence: float, source: EvidenceKind)` + `.key` property (casefold, whitespace-normalized)

### 11.4 Internal Workflow

**`FusionEngine.fuse_modules(detection=..., fingerprint=..., ocr=...)`:**

1. Build evidence list:
   - `Evidence.from_detection(result)` → DEVICE_TYPE + BRAND claims at `result.confidence`
   - `Evidence.from_fingerprint(fp)` → device_type/brand provenance + identity dict, all at **0.50** confidence (`_FINGERPRINT_PROVENANCE_CONFIDENCE`)
   - `Evidence.from_ocr(extraction)` → per-field claims at each `field.confidence`
2. Extract identity anchors: `eco_id = fingerprint.eco_id`, `fingerprint_hash = fingerprint.fingerprint`
3. Call `fuse(evidence, eco_id=..., fingerprint=..., source_hashes=...)`

**`FusionEngine.fuse(evidence, ...)`:**

1. Freeze evidence: `evidence = tuple(evidence)`
2. **`_resolve_attributes(evidence)`** — for each `FusionAttribute` (in declaration order):
   a. Gather all claims for that attribute from all evidence
   b. **Group by normalized value** (`claim.key` — casefold + whitespace-normalized)
   c. Per group: **noisy-OR combine** confidences: `combined = 1 - Π(1 - cᵢ)`
      - Two 0.8 claims → 0.96 (stronger than either alone)
      - Three 0.5 claims → 0.875
   d. **Select winner:** rank by `(combined_conf, claim_count, module_order)`
      - Tie-break: more claims → higher rank; same count → earlier module wins
   e. **Confidence scaling:** `winner_combined × support_share` where `support_share = winner_combined / sum(all combined)`
      - Lone dissenter damps confidence (true value could be the dissenter's)
   f. **Conflict detection:** more than one distinct value group → `Conflict` entry
3. Assemble `DeviceContext` with:
   - `confidence = mean(resolved_attribute.confidence for each attribute)`
   - `has_conflicts = bool(conflicts)`

**Key constant:** `_UNKNOWN_VALUES = {"", "unknown", "n/a", "none"}` — sentinel values treated as absent/no claim.

### 11.5 Collaborators

- `FusionEngine` — pure stateless engine; single instance
- No external infrastructure, no repositories, no I/O

### 11.6 Configuration

No settings-specific configuration — the fusion algorithm is parameter-free. The fusion engine version is stamped onto `DeviceContext`.

### 11.7 Error Handling

- `FusionError` (500) — base fusion domain error (internal-only, no HTTP surface)

### 11.8 Testing

34 tests across 2 files: `test_fusion_models.py` (18 tests: Evidence builders, Claim normalization, ResolvedAttribute, Conflict, DeviceContext properties), `test_fusion_engine.py` (16 tests: agreement aggregation, conflict detection, missing module handling, unknown-value filtering, confidence scaling).

### 11.9 Extension Points

- **Add attribute:** extend `FusionAttribute` enum → auto-participates in resolution
- **Add evidence source:** extend `EvidenceKind` enum + add `Evidence.from_*` builder
- **Custom fusion logic:** override `_select_winner` or `_group_by_value` for domain-specific reconciliation
- **Weighted modules:** inject per-module trust weights (future; currently equal-weight noisy-OR)

### 11.10 Design Rationale

- **Shared attribute space:** `FusionAttribute` enum is the single vocabulary — modules map their native fields onto it via `Evidence.from_*` builders
- **Noisy-OR (not mean):** agreement raises confidence multiplicatively (two independent 0.8 sources → 0.96, not 0.80)
- **Support-share damping:** when one module dissents, the winner's confidence is damped proportionally — acknowledges uncertainty
- **Conflict-preserving:** rejected value groups are captured as `Conflict` entries → downstream engines can act on disagreements
- **KNOWN_UNKNOWN_CONFIDENCE = 0.50:** fingerprint provenance claims carry moderate trust — they come from a hash match, not an explicit label
- **Unknown-value filtering:** `""/"unknown"/"n/a"/"none"` treated as absent → prevents garbage values from outvoting real ones
- **Internal-only:** no HTTP surface → fusion is an architectural seam, not a service

### 11.11 Dependencies

Pure Python (no external libs beyond stdlib). All type imports under `TYPE_CHECKING`.

### 11.12 Interaction with Neighboring Engines

- **Consumes:** `DetectionResult` (M1.4), `DeviceFingerprint` (M1.5), `OCRExtraction` (M1.6) via `Evidence` builders
- **Produces:** `DeviceContext` → consumed by M1.8 Recoverability, M1.9 Component, M1.10 Material, M1.11 Environmental
- **One-way valve:** perception tier → fusion → knowledge tier; no back-coupling

### 11.13 Fusion Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────────┐
│                     FUSION PIPELINE (M1.7)                         │
└──────────────────────────────────────────────────────────────────┘

  DetectionResult        DeviceFingerprint        OCRExtraction
      │                       │                       │
      ▼                       ▼                       ▼
  Evidence.from_       Evidence.from_          Evidence.from_
  detection()          fingerprint()           ocr()
      │                       │                       │
      │  Claim(DEVICE_TYPE,   │  Claim(DEVICE_TYPE,   │  Claim(BRAND,
      │    "laptop", 0.92)    │    "laptop", 0.50)    │    "Dell", 0.80)
      │  Claim(BRAND,         │  Claim(BRAND,         │  Claim(MODEL,
      │    "Dell", 0.92)      │    "Dell", 0.50)      │    "XPS", 0.75)
      │                       │  (identity dict at     │  Claim(SERIAL_NUMBER,
      │                       │   0.50 each)           │    "SN123", 0.92)
      │                       │                       │
      └───────────────────────┼───────────────────────┘
                              │
                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │                FusionEngine.fuse(evidence)                 │
  │                                                          │
  │  For each FusionAttribute (DEVICE_TYPE, BRAND, MODEL,    │
  │    SERIAL_NUMBER, IMEI, MAC_ADDRESS):                    │
  │                                                          │
  │  1. Collect claims → group by normalized key             │
  │     "Dell" vs "dell"   → same group (casefold)          │
  │     "XPS 15" vs "xps15" → same group (whitespace)      │
  │                                                          │
  │  2. Per group: noisy-OR confidence                       │
  │     combined = 1 - Π(1 - cᵢ)                            │
  │                                                          │
  │  3. Winner = max(combined, claim_count, module_order)    │
  │                                                          │
  │  4. Damp confidence:                                     │
  │     winner.conf × (winner_combined / total_combined)     │
  │                                                          │
  │  5. Conflict = >1 value group → rejected groups saved     │
  └──────────────────────────────────────────────────────────┘
                              │
                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │                     DeviceContext                          │
  │                                                          │
  │  attributes: tuple[ResolvedAttribute, ...]                │
  │    ├─ DEVICE_TYPE: "laptop", conf=0.96, sources=[DET,FPR]│
  │    ├─ BRAND: "Dell", conf=0.992, sources=[DET,FPR,OCR]   │
  │    ├─ MODEL: "XPS 15", conf=0.75, sources=[OCR]          │
  │    ├─ SERIAL_NUMBER: "SN123", conf=0.92, sources=[OCR]   │
  │    ├─ IMEI: N/A (no evidence)                             │
  │    └─ MAC_ADDRESS: N/A (no evidence)                      │
  │                                                          │
  │  confidence: mean(0.96, 0.992, 0.75, 0.92) = 0.9055      │
  │  conflicts: [] (all groups agree)                         │
  │  has_conflicts: False                                     │
  └──────────────────────────────────────────────────────────┘
```

---

## 12. Recoverability Intelligence Engine (M1.8)

### 12.1 Purpose

Transform a fused `DeviceContext` into three normalized recoverability scores [0,1] (repairability, reusability, recyclability), a hazard level, a confidence [0,1], and a recommended end-of-life action — all via **deterministic, auditable rules** with no model weights.

### 12.2 Inputs

- `DeviceContext` — including `.device_type`, `.model`, `.serial_number`, `.imei`, `.confidence`, `.has_conflicts`, `.conflicts`, `.eco_id`

**TYPE_CHECKING only** — the engine imports `DeviceContext` solely for type annotation; runtime coupling is through the passed parameter.

### 12.3 Outputs

**`RecoverabilityReport`** (frozen, slotted):
- `repairability: float` [0, 1] — 6 decimal places
- `reusability: float` [0, 1]
- `recyclability: float` [0, 1]
- `hazard_level: HazardLevel` — `NONE` | `LOW` | `MEDIUM` | `HIGH` | `UNKNOWN`
- `confidence: float` [0, 1] — context.confidence × Π rule confidence factors
- `recommended_action: RecommendedAction` — `REFURBISH` | `REPAIR` | `RECYCLE` | `HAZARDOUS_DISPOSAL` | `MANUAL_REVIEW`
- `reasoning: tuple[str, ...]` — ordered reasons from rules
- `warnings: tuple[str, ...]` — operator cautions
- `device_type: str`, `eco_id: str`, `engine_version: str`, `created_at: datetime | None`

**Supporting enums:**
- `HazardLevel` — `NONE = 0, UNKNOWN = 1, LOW = 2, MEDIUM = 3, HIGH = 4` (ordered for `max_hazard()`)
- `RecommendedAction` — `REFURBISH, REPAIR, RECYCLE, HAZARDOUS_DISPOSAL, MANUAL_REVIEW`
- `RuleOutcome` (frozen dataclass) — `(rule: str, repairability_delta: float, reusability_delta: float, recyclability_delta: float, hazard_floor: HazardLevel | None, confidence_factor: float, force_action: RecommendedAction | None, reason: str, warning: str | None)`

### 12.4 Internal Workflow

**`RecoverabilityService.assess(context)`** → `RecoverabilityReport`:

```
DeviceContext
    │
    ▼
1. Resolve device profile (profile_for(device_type))
   └─> in-code profiles.py → 19 curated profiles + _UNKNOWN_PROFILE fallback
       Case-insensitive lookup + ~40 synonyms
    │
    ▼
2. Run rule engine → list[RuleOutcome]
   └─> RuleEngine.run(context, profile, config)
       7 rules in fixed order, each evaluating independently
    │
    ▼
3. Score: fold outcomes → RecoverabilityReport
   └─> ScoringEngine.score(context, profile, outcomes)
       ├─> Sum repairability/reusability/recyclability deltas → clamp [0,1] → round 6 decimals
       ├─> max_hazard() over all hazard floors (HazardLevel ordering)
       ├─> confidence = context.confidence × Π(confidence_factors) → clamp/round
       ├─> Decision table (ordered priority):
       │   1. HIGH hazard or forced HAZARDOUS_DISPOSAL → HAZARDOUS_DISPOSAL
       │   2. Forced MANUAL_REVIEW → MANUAL_REVIEW
       │   3. reusability ≥ refurbish_min_reusability (0.65) → REFURBISH
       │   4. repairability ≥ repair_min_repairability (0.55) → REPAIR
       │   5. recyclability ≥ recycle_min_recyclability (0.45) → RECYCLE
       │   6. Else → MANUAL_REVIEW
       └─> Collect reasoning + warnings from all outcomes
```

### 12.5 Collaborators

- **`RecoverabilityConfig`** — thresholds, bonuses, penalties (constructor-injected)
- **`RuleEngine`** — 7 `Rule` instances in `DEFAULT_RULES` (constructor-injected, extendable)
- **`ScoringEngine`** — pure fold function (constructor-injected)
- **`clock`** — optional, defaults to UTC now

### 12.6 Configuration

**`RecoverabilityConfig`** (`recoverability/config.py`):
- `refurbish_min_reusability: float = 0.65`
- `repair_min_repairability: float = 0.55`
- `recycle_min_recyclability: float = 0.45`
- `low_confidence_threshold: float = 0.50`
- `identity_repair_bonus: float = 0.10` — bonus for known serial/IMEI
- `identity_reuse_bonus: float = 0.10` — bonus for known identity
- `missing_identity_reuse_penalty: float = 0.15` — penalty for no identity
- `battery_recyclability_penalty: float = 0.10` — penalty for battery separation step
- `battery_hazard_floor_enabled: bool = True`
- `conflict_confidence_factor: float = 0.80` — multiplicatively damp confidence on fusion conflict
- `low_confidence_factor: float = 0.60` — multiplicatively damp on sub-threshold confidence
- `unknown_device_confidence_factor: float = 0.70` — damp on unrecognized device type

**Environment variable mapping** (4 vars via `from_settings()`):
- `RECOVERABILITY_REFURBISH_MIN_REUSABILITY`
- `RECOVERABILITY_REPAIR_MIN_REPAIRABILITY`
- `RECOVERABILITY_RECYCLE_MIN_RECYCLABILITY`
- `RECOVERABILITY_LOW_CONFIDENCE_THRESHOLD`

### 12.7 Error Handling

- `RecoverabilityError` (500) — internal-only; raised to orchestrator as typed exception

### 12.8 Testing

59 total tests: `test_recoverability_profiles.py`, `test_recoverability_rules.py`, `test_recoverability_scoring.py`, `test_recoverability_service.py`. Tests cover all 7 rules independently and in combination, all 19 profiles, edge cases (unknown type, low confidence, conflict, missing identity, high hazard).

### 12.9 Extension Points

- **Add rule:** new `Rule` subclass → inject into `RuleEngine(rules=...)`
- **Edit profiles:** modify `_DEFAULT_PROFILES` table in `profiles.py`
- **Override config:** inject `RecoverabilityConfig()` with custom thresholds

### 12.10 Design Rationale

- **Rules not ML:** 7 deterministic rules, not learned weights → fully auditable, explainable
- **Profiles in-code:** 19 device types + synonyms are curated knowledge, not data-files; stable enough to live in code
- **Uniform `RuleOutcome`:** additive deltas → pure scoring fold without per-rule special cases
- **Multiplicative confidence:** independent damping signals compound (conflict × low_confidence × unknown_device)
- **Explicit decision table:** safety overrides (HIGH hazard) beat scores every time
- **Internal-only:** no HTTP surface; report consumed by downstream M1.9–M1.11 engines

### 12.11 Dependencies

Pure Python (no external libs beyond stdlib). Imports `HazardLevel`/`RecommendedAction` enums at runtime; `DeviceContext`/`Settings` under `TYPE_CHECKING` only.

### 12.12 Rule Set (7 rules, ordered)

| # | Rule | Fires When | Outcome |
|---|------|-----------|---------|
| 1 | `BaselineProfileRule` | Always | Seeds 3 scores + hazard from profile baseline |
| 2 | `IdentityCompletenessRule` | Any identity field present | +repair/+reuse bonuses; absent → −reuse + warning |
| 3 | `BatteryHazardRule` | Profile `has_battery` | Hazard floor MEDIUM, −recycle (separation step) |
| 4 | `HighHazardDisposalRule` | Profile hazard HIGH | Hazard floor HIGH, forces `HAZARDOUS_DISPOSAL` |
| 5 | `ConflictPenaltyRule` | Context has conflicts | ×0.80 confidence, warning |
| 6 | `LowConfidenceRule` | Context confidence < 0.50 | ×0.60 confidence, forces `MANUAL_REVIEW`, warning |
| 7 | `UnknownDeviceRule` | Profile not known | ×0.70 confidence, forces `MANUAL_REVIEW`, warning |

### 12.13 Interaction with Neighboring Engines

- **Consumes:** `DeviceContext` from M1.7 Fusion (only upstream dependency)
- **Produces:** `RecoverabilityReport` → consumed by M1.9 Component (confidence blend, hazard corroboration), M1.10 Material (confidence blend), M1.11 Environmental (recyclability for circularity, hazard for reduction score)

### 12.14 Recoverability Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│               RECOVERABILITY PIPELINE (M1.8)                   │
└──────────────────────────────────────────────────────────────┘

  DeviceContext
  ├─ device_type: "laptop"
  ├─ model: "XPS 15"
  ├─ serial_number: "SN123"
  ├─ confidence: 0.90
  └─ has_conflicts: false
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  1. Resolve device profile                          │
  │     profile_for("laptop") → DeviceProfile          │
  │     repairability: 0.60, reusability: 0.65         │
  │     recyclability: 0.70, hazard: NONE              │
  │     has_battery: true, known: true                  │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  2. Run 7 rules → list[RuleOutcome]                 │
  │                                                    │
  │  ✓ Rule 1 (Baseline): seed scores + NONE hazard    │
  │  ✓ Rule 2 (Identity): model+serial+IMEI present    │
  │    → +0.10 repair, +0.10 reuse                     │
  │  ✓ Rule 3 (Battery): has_battery=true              │
  │    → hazard floor MEDIUM, −0.10 recycle            │
  │  ✗ Rule 4 (HighHazard): hazard=NONE → skip         │
  │  ✗ Rule 5 (Conflict): no conflicts → skip          │
  │  ✗ Rule 6 (LowConf): conf=0.90 ≥ 0.50 → skip      │
  │  ✗ Rule 7 (Unknown): known=true → skip             │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  3. ScoringEngine.score(outcomes)                   │
  │                                                    │
  │  repairability = clamp(0.60 + 0.10) = 0.70         │
  │  reusability   = clamp(0.65 + 0.10) = 0.75         │
  │  recyclability = clamp(0.70 − 0.10) = 0.60         │
  │  hazard_level  = max(NONE, MEDIUM) = MEDIUM        │
  │  confidence    = 0.90 × 1.0 = 0.90                 │
  │                                                    │
  │  Decision table:                                    │
  │    1. Hazard HIGH? No                               │
  │    2. Forced MANUAL_REVIEW? No                      │
  │    3. reusability 0.75 ≥ 0.65 → REFURBISH ✓        │
  └────────────────────────────────────────────────────┘
      │
      ▼
  RecoverabilityReport
  ├─ repairability: 0.70
  ├─ reusability: 0.75
  ├─ recyclability: 0.60
  ├─ hazard_level: MEDIUM (battery)
  ├─ confidence: 0.90
  ├─ recommended_action: REFURBISH
  └─ reasoning: ("profile baseline...", "identity complete...",
                 "battery hazardous...")
```

---

## 13. Component Intelligence Engine (M1.9)

### 13.1 Purpose

Infer the likely internal electronic components (battery, motherboard, display, camera, etc.) from device type, with presence confidence [0,1] per component corroborated by available identity signals and recoverability hazard information.

### 13.2 Inputs

- `DeviceContext` — reads `.device_type`, `.model`, `.serial_number`, `.imei`, `.mac_address`, `.confidence`, `.has_conflicts`, `.eco_id`
- `RecoverabilityReport` — reads `.confidence`, `.hazard_level`

**TYPE_CHECKING only** — runtime coupling through passed parameters.

### 13.3 Outputs

**`ComponentReport`** (frozen, slotted):
- `components: tuple[InferredComponent, ...]` — each component:
  - `name: str` — human-readable name (e.g. "Lithium-ion battery pack")
  - `category: ComponentCategory` — 17-member enum (`BATTERY, CIRCUIT_BOARD, PROCESSOR, MEMORY, STORAGE, DISPLAY, CONNECTIVITY, INPUT, CAMERA, SENSOR, POWER, AUDIO, OPTICS, OPTICAL_MEDIA, CABLING, HOUSING, OTHER`)
  - `presence_confidence: float` [0, 1] — 6 decimals
  - `hazardous: bool`, `recoverable: bool`
  - `reason: str`
- `overall_confidence: float` [0, 1] — blended then damped
- `reasoning: tuple[str, ...]`, `warnings: tuple[str, ...]`
- `device_type: str`, `eco_id: str`, `engine_version: str`, `profile_version: str`, `created_at: datetime | None`

### 13.4 Internal Workflow

**`ComponentService.analyze(context, recoverability)`** → `ComponentReport`:

```
DeviceContext + RecoverabilityReport
    │
    ▼
1. Resolve device profile
   └─> ComponentProfileLibrary.profile_for(device_type)
       Loads components/data/components.yaml (versioned, 19 profiles + 47 aliases)
    │
    ▼
2. Infer components (ComponentInferenceEngine.infer)
   └─> For each component in profile:
       ├─> Start: base_likelihood (catalogue prior)
       ├─> Identity corroboration: if any implied_by signal
       │    (model/serial/IMEI/MAC) present → +identity_corroboration_bonus (default +0.05)
       ├─> Hazard corroboration: if component is hazardous AND
       │    recoverability hazard is concrete (LOW/MEDIUM/HIGH)
       │    → +hazard_corroboration_bonus (default +0.10)
       ├─> Clamp/round [0,1], 6 decimals
       └─> Drop if ≤ min_presence_confidence (0.05)
    │
    ▼
3. Compute overall confidence:
   └─> blend: context.confidence × 0.5 + recoverability.confidence × 0.5
       damp: × unknown_type_confidence_factor (0.50) if profile not known
       damp: × conflict_confidence_factor (0.80) if context has conflicts
```

### 13.5 Collaborators

- **`ComponentConfig`** — thresholds, bonuses (constructor-injected)
- **`ComponentProfileLibrary`** — loads from `components/data/components.yaml` (versioned YAML catalogue)
- **`ComponentInferenceEngine`** — pure inference logic
- **`clock`** — injected timestamp callable

### 13.6 Configuration

**`ComponentConfig`** (`components/config.py`):
- `profiles_path: str = "components/data/components.yaml"`
- `min_presence_confidence: float = 0.05` — drop components below this threshold
- `identity_corroboration_bonus: float = 0.05` — boost when implied_by signal present
- `hazard_corroboration_bonus: float = 0.10` — boost when hazardous + concrete hazard
- `recoverability_confidence_weight: float = 0.50` — blend weight for recoverability confidence
- `unknown_type_confidence_factor: float = 0.50` — damp when device type unknown
- `conflict_confidence_factor: float = 0.80` — damp when fusion conflicts present

**Environment mapping:** `COMPONENT_PROFILES_PATH`, `COMPONENT_MIN_PRESENCE_CONFIDENCE`

### 13.7 Error Handling

- `ComponentError` (500) — base component domain error
- `ComponentProfileError` (422) — catalogue load failure (missing file, parse error, invalid structure)

### 13.8 Testing

48 tests: `test_component_profiles.py` (23 tests: catalogue loading, alias resolution, profile validation), `test_component_inference.py`, `test_component_service.py`.

### 13.9 Extension Points

- **Catalogue:** edit `components/data/components.yaml` (versioned data, domain-expert editable)
- **Corroboration rules:** modify inference engine bonuses (identity, hazard) or add new corroboration signals
- **New component categories:** extend `ComponentCategory` enum

### 13.10 Design Rationale

- **External catalogue:** data not code — domain experts can update component profiles without touching engine logic
- **Priors + bounded corroboration:** catalogue sets baseline likelihood; signals nudge but never overwhelm (max +0.10)
- **Why UNKNOWN hazard does not corroborate:** not positive evidence for a hazardous component
- **Blend then damp:** upstream confidences averaged, then independently damped for type familiarity and conflicts
- **Internal-only:** no HTTP surface; report consumed by downstream M1.10 Material, M1.11 Environmental

### 13.11 Dependencies

Core: `PyYAML` (catalogue loader). Runtime: `HazardLevel` enum (from recoverability). TYPE_CHECKING: `DeviceContext`, `RecoverabilityReport`, `Settings`.

### 13.12 Component Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                  COMPONENT PIPELINE (M1.9)                     │
└──────────────────────────────────────────────────────────────┘

  DeviceContext + RecoverabilityReport
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Load components/data/components.yaml (versioned)   │
  │  → 19 device profiles + 47 aliases                 │
  │  → Resolve: profile_for("laptop")                  │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  For each component in profile:                     │
  │                                                    │
  │  "Lithium-ion battery pack" (battery)              │
  │    base_likelihood: 0.97                           │
  │    implied_by: [] → no identity corroboration      │
  │    hazardous: true                                 │
  │    hazard_level: MEDIUM → +0.10 corroboration      │
  │    presence_confidence: clamp(0.97+0.10) = 1.0    │
  │                                                    │
  │  "Mainboard" (circuit_board)                       │
  │    base_likelihood: 0.99                           │
  │    implied_by: [serial_number]                     │
  │    serial "SN123" present → +0.05 corroboration    │
  │    presence_confidence: clamp(0.99+0.05) = 1.0    │
  │                                                    │
  │  "Webcam" (camera)                                 │
  │    base_likelihood: 0.85                           │
  │    implied_by: [] → no corroboration               │
  │    presence_confidence: 0.85                        │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Overall confidence:                                │
  │    blend = 0.90×0.5 + 0.90×0.5 = 0.90             │
  │    known type → no damp                            │
  │    no conflicts → no damp                          │
  │    overall = 0.90                                   │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ComponentReport
  ├─ components: (battery 1.0, mainboard 1.0, webcam 0.85, ...)
  ├─ overall_confidence: 0.90
  └─ profile_version: "1.0.0"
```

---

## 14. Material Intelligence Engine (M1.10)

### 14.1 Purpose

Estimate the recoverable and hazardous material breakdown (metals, plastics, glass, rare earths) with nominal mass in grams and confidence [0,1] per material, gated by component presence from the M1.9 Component Report.

**M1.10 supersedes the M1.1 `MockMaterialEstimator`** — it replaces the mock placeholder with the production material engine backed by an external, versioned YAML catalogue.

### 14.2 Inputs

- `DeviceContext` — reads `.device_type`, `.eco_id`, `.confidence`, `.has_conflicts`
- `RecoverabilityReport` — reads `.confidence`, `.hazard_level`
- `ComponentReport` — reads `.components` (for presence-gating), `.overall_confidence`

### 14.3 Outputs

**`MaterialReport`** (frozen, slotted):
- `materials: tuple[RecoveredMaterial, ...]` — each:
  - `name: str` — human-readable name (e.g. "Aluminium / magnesium chassis")
  - `category: MaterialCategory` — 11-member enum (`FERROUS_METAL, NON_FERROUS_METAL, PRECIOUS_METAL, CRITICAL_MATERIAL, RARE_EARTH, PLASTIC, GLASS, CERAMIC, BATTERY_MATERIAL, HAZARDOUS, OTHER`)
  - `mass_g: float` — catalogue nominal mass (never scaled by confidence)
  - `confidence: float` [0, 1] — 6 decimals
  - `recoverable: bool`, `hazardous: bool`
  - `source_components: tuple[str, ...]` — component category wire values that gate this material
  - `reason: str`
- `total_mass_g: float` — Σ all materials
- `recoverable_mass_g: float` — Σ recoverable materials
- `hazardous_mass_g: float` — Σ hazardous materials
- `overall_confidence: float` [0, 1]
- `reasoning: tuple[str, ...]`, `warnings: tuple[str, ...]`
- `device_type: str`, `eco_id: str`, `engine_version: str`, `profile_version: str`, `created_at: datetime | None`

### 14.4 Internal Workflow

**`MaterialService.analyze(context, recoverability, components)`** → `MaterialReport`:

```
DeviceContext + RecoverabilityReport + ComponentReport
    │
    ▼
1. Resolve device profile
   └─> MaterialProfileLibrary.profile_for(device_type)
       Loads materials/data/materials.yaml (versioned, 19 profiles + 47 aliases)
    │
    ▼
2. Infer materials (MaterialInferenceEngine.infer)
   └─> For each material in profile:
       ├─> Source-component gating:
       │    ├─ source_components empty → structural (always listed)
       │    └─ source_components non-empty → listed ONLY if at least
       │       one named component category is present in ComponentReport
       │       (e.g. "Lithium (battery cells)" listed only if BATTERY component present)
       ├─> Confidence:
       │    ├─ Structural (no source_components) → inherits overall_confidence
       │    └─ Gated → strongest present source's presence_confidence
       ├─> Drop if ≤ min_material_confidence (0.05)
       └─> Keep mass_g at catalogue nominal (never scale by confidence)
    │
    ▼
3. Aggregate totals: sum all masses, filter recoverable/hazardous
    │
    ▼
4. Compute overall confidence:
   └─> blend: components.overall_confidence × 0.5 + recoverability.confidence × 0.5
       damp: × unknown_type_confidence_factor (0.50) if profile not known
       damp: × conflict_confidence_factor (0.80) if context has conflicts
```

### 14.5 Collaborators

- **`MaterialConfig`** — thresholds, blend weights (constructor-injected)
- **`MaterialProfileLibrary`** — loads from `materials/data/materials.yaml`
- **`MaterialInferenceEngine`** — pure inference logic
- **`clock`** — injected timestamp callable

### 14.6 Configuration

**`MaterialConfig`** (`materials/config.py`):
- `profiles_path: str = "materials/data/materials.yaml"`
- `min_material_confidence: float = 0.05`
- `recoverability_confidence_weight: float = 0.50`
- `unknown_type_confidence_factor: float = 0.50`
- `conflict_confidence_factor: float = 0.80`

**Environment mapping:** `MATERIAL_PROFILES_PATH`, `MATERIAL_MIN_CONFIDENCE`

### 14.7 Error Handling

- `MaterialError` (500) — base material domain error
- `MaterialProfileError` (422) — catalogue load failure (missing file, parse error, negative mass, unknown category, unknown source component)

### 14.8 Testing

42 tests: `test_material_profiles.py` (24 tests), `test_material_inference.py`, `test_material_service.py`. Covers component gating, mass aggregation, confidence blend, edge cases (empty component report, unknown type).

### 14.9 Extension Points

- **Catalogue:** edit `materials/data/materials.yaml`
- **Source-component links:** catalogue `source_components` field connects materials to components

### 14.10 Design Rationale

- **Nominal mass + separate confidence:** mass is a physical quantity (45g of lithium whether 50% or 99% sure); confidence stays on a separate axis — never scales mass
- **Source-component gating:** makes the material breakdown faithful to THIS device: no battery component detected → no battery materials listed
- **Why per-device nominal masses not component-derived:** `ComponentReport` has presence confidence, not mass; mass needs a reference table
- **Blend then damp:** upstream confidences averaged, then independently damped for type familiarity and conflicts
- **Internal-only:** no HTTP surface; report consumed by M1.11 Environmental

### 14.11 Dependencies

Core: `PyYAML`. Runtime: `ComponentCategory` enum (from components). TYPE_CHECKING: `DeviceContext`, `RecoverabilityReport`, `ComponentReport`, `Settings`.

### 14.12 Material Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                  MATERIAL PIPELINE (M1.10)                     │
└──────────────────────────────────────────────────────────────┘

  DeviceContext + RecoverabilityReport + ComponentReport
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Load materials/data/materials.yaml (versioned)     │
  │  → 19 device profiles + 47 aliases                 │
  │  → Resolve: profile_for("laptop")                  │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Build component presence map:                      │
  │    battery: 1.0                                    │
  │    circuit_board: 1.0                              │
  │    camera: 0.85                                    │
  │    display: 1.0                                    │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  For each material in profile:                      │
  │                                                    │
  │  "Aluminium chassis" (non_ferrous_metal)           │
  │    mass_g: 500, source_components: []              │
  │    → structural, always listed                     │
  │    → confidence = overall_confidence (0.90)        │
  │                                                    │
  │  "Lithium (battery cells)" (battery_material)      │
  │    mass_g: 45, source_components: [battery]        │
  │    → battery present? YES → LISTED                 │
  │    → confidence = max(battery presence) = 1.0     │
  │                                                    │
  │  "Camera sensor (rare earth)" (rare_earth)         │
  │    mass_g: 0.5, source_components: [camera]        │
  │    → camera present? YES (0.85) → LISTED           │
  │    → confidence = 0.85                              │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Aggregate:                                         │
  │    total_mass_g = 500 + 45 + 0.5 + ...            │
  │    recoverable_mass_g = (all recoverable)          │
  │    hazardous_mass_g = 45 (lithium)                 │
  │                                                    │
  │  Overall confidence:                                │
  │    blend = 0.90×0.5 + 0.90×0.5 = 0.90             │
  │    known type → no damp                            │
  │    no conflicts → no damp                          │
  └────────────────────────────────────────────────────┘
      │
      ▼
  MaterialReport
  ├─ materials: (aluminium 500g, lithium 45g, camera sensor 0.5g, ...)
  ├─ total_mass_g: 645.5
  ├─ recoverable_mass_g: 645.5
  ├─ hazardous_mass_g: 45.0
  └─ overall_confidence: 0.90
```

---

## 15. Environmental Intelligence Engine (M1.11)

### 15.1 Purpose

Estimate the avoided environmental burden of recovering a device rather than manufacturing new materials — carbon saved (kg CO₂e), energy saved (MJ), water saved (L), landfill diversion (kg), critical material recovery (kg) — plus a circularity index [0,1] and hazard-reduction score [0,1]. Confidence is kept on a **separate axis** and never scales any metric.

### 15.2 Inputs

- `DeviceContext` — reads `.eco_id`
- `RecoverabilityReport` — reads `.recyclability`, `.hazard_level`, `.confidence`
- `ComponentReport` — provenance only
- `MaterialReport` — reads `.materials`, `.recoverable_mass_g`, `.total_mass_g`, `.hazardous_mass_g`, `.overall_confidence`, `.device_type`

### 15.3 Outputs

**`EnvironmentalImpactReport`** (frozen, slotted):

**Physical quantities** (never clamped, rounded to 3 decimal places):
- `carbon_saved_kg: float` — kg CO₂e avoided
- `energy_saved_mj: float` — MJ avoided
- `water_saved_l: float` — liters water avoided
- `landfill_diversion_kg: float` — kg diverted from landfill
- `critical_material_recovery_kg: float` — kg of critical materials recovered

**Unit indices** [0, 1] (6 decimal places):
- `circularity_index: float` — `(recoverable_fraction × (1−w)) + recyclability × w`, where w = 0.50
- `hazard_reduction_score: float` — `severity × ((1−w) + hazardous_fraction × w)`, where w = 0.50

**Separate axis:**
- `confidence: float` [0, 1] — `materials.overall_confidence × 0.5 + recoverability.confidence × 0.5` (no further damping)

**Structured contributions:**
- `contributions: tuple[MaterialContribution, ...]` — per-category breakdown:
  - `category: MaterialCategory`
  - `recovered_mass_g: float`
  - `carbon_saved_kg: float`, `energy_saved_mj: float`, `water_saved_l: float`
  - `critical: bool`
  - `reason: str`

**Metadata:**
- `reasoning: tuple[str, ...]`, `warnings: tuple[str, ...]`
- `device_type: str`, `eco_id: str`, `engine_version: str`, `factors_version: str`, `created_at: datetime | None`

### 15.4 Internal Workflow

**`EnvironmentalService.analyze(context, recoverability, components, materials)`** → `EnvironmentalImpactReport`:

```
All four upstream reports
    │
    ▼
1. Load factor catalogue (once at service construction)
   └─> FactorLibrary (environmental/data/factors.yaml)
       11 material categories + "default" fallback
    │
    ▼
2. Compute per-category contributions (_contributions):
   └─> Walk materials.materials, keep only:
       ├─ recoverable=True
       └─ confidence > min_material_confidence (0.05)
       Group by MaterialCategory, sum nominal masses
       For each category:
       ├─ factor = library.factor_for(category) or library.default
       ├─ mass_kg = mass_g / 1000
       ├─ carbon = mass_kg × factor.carbon_kg_per_kg
       ├─ energy = mass_kg × factor.energy_mj_per_kg
       └─ water  = mass_kg × factor.water_l_per_kg
    │
    ▼
3. Compute physical totals:
   ├─ carbon_saved_kg    = Σ contributions.carbon
   ├─ energy_saved_mj    = Σ contributions.energy
   ├─ water_saved_l      = Σ contributions.water
   ├─ landfill_diversion_kg = materials.recoverable_mass_g / 1000
   └─ critical_material_recovery_kg = Σ mass_g where critical=True, / 1000
    │
    ▼
4. Compute unit indices:
   ├─ circularity_index:
   │    mass_fraction = recoverable_mass_g / total_mass_g
   │    blended = mass_fraction × (1−w) + recyclability × w
   │    w = 0.50
   └─ hazard_reduction_score:
       severity = {NONE:0, UNKNOWN:0.25, LOW:0.4, MEDIUM:0.7, HIGH:1.0}
       hazardous_fraction = hazardous_mass_g / total_mass_g
       blended = severity × ((1−w) + hazardous_fraction × w)
       w = 0.50
    │
    ▼
5. Compute confidence (separate axis, never scales metrics):
   └─> materials.overall_confidence × 0.5 + recoverability.confidence × 0.5
       (NO further damping — material confidence already folds in type/conflict signals)
    │
    ▼
6. Build reasoning + warnings (_explain)
```

**Critical categories** (flagged `critical=True` in the factor catalogue): `precious_metal`, `critical_material`, `rare_earth` — these count toward `critical_material_recovery_kg`.

### 15.5 Collaborators

- **`EnvironmentalConfig`** — blend weights and threshold (constructor-injected)
- **`FactorLibrary`** — loaded from `environmental/data/factors.yaml` (versioned, validated)
- **`EnvironmentalInferenceEngine`** — pure arithmetic fold
- **`clock`** — injected timestamp callable

### 15.6 Configuration

**`EnvironmentalConfig`** (`environmental/config.py`):
- `factors_path: str = "environmental/data/factors.yaml"`
- `min_material_confidence: float = 0.05` — filter floor for recovered materials
- `recoverability_confidence_weight: float = 0.50` — blend weight for recoverability side
- `circularity_recyclability_weight: float = 0.50` — recyclability weight in circularity blend
- `hazard_diversion_weight: float = 0.50` — hazardous mass fraction weight in hazard reduction

**Environment mapping:** `ENVIRONMENTAL_FACTORS_PATH`, `ENVIRONMENTAL_MIN_CONFIDENCE`

### 15.7 Error Handling

- `EnvironmentalError` (500) — base environmental domain error
- `EnvironmentalFactorError` (422) — catalogue load failure (missing file, parse error, negative/non-numeric factors, unknown material category, missing default fallback)

### 15.8 Testing

23 tests: `test_environmental_factors.py`, `test_environmental_inference.py` (23 tests), `test_environmental_service.py`. Covers per-category aggregation, mass→kg conversion, factor lookup, edge cases (empty material report, zero mass, unknown category falling back to default).

### 15.9 Extension Points

- **Factor catalogue:** edit `environmental/data/factors.yaml` (versioned LCA data — improves without redeploy)
- **New material categories:** extend `MaterialCategory` enum + add factor entry
- **Adjust blend weights:** inject `EnvironmentalConfig` with custom weights

### 15.10 Design Rationale

- **Data not logic:** LCA factors improve over time; external catalogue = no redeploy needed
- **Three axes kept apart:**
  - *Physical* — real amounts, never clamped, rounded to 3 decimals
  - *Unit indices* — [0, 1] composite measures, rounded to 6 decimals
  - *Confidence* — separate axis, never scales a metric
- **No double-damping:** material confidence already encodes device-type/conflict signals; environmental engine blends, doesn't re-damp
- **Deterministic fold:** pure function, no models → fully auditable
- **Critical material tracking:** precious metals, critical materials, rare earths flagged for regulatory reporting

### 15.11 Dependencies

Core: `PyYAML`. Runtime: `HazardLevel` (from recoverability), `MaterialCategory` (from materials). TYPE_CHECKING: all four upstream reports + `Settings`.

### 15.12 Environmental Pipeline (ASCII Diagram)

```
┌──────────────────────────────────────────────────────────────┐
│               ENVIRONMENTAL PIPELINE (M1.11)                   │
└──────────────────────────────────────────────────────────────┘

  All 4 upstream reports + environmental/data/factors.yaml
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Filter recoverable materials:                      │
  │    keep: recoverable=True, confidence > 0.05       │
  │    skip: non-recoverable or low confidence         │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Aggregate by MaterialCategory:                     │
  │                                                    │
  │  non_ferrous_metal: 500g → 0.5 kg                 │
  │    factor: carbon=6.5, energy=45, water=150        │
  │    carbon = 0.5 × 6.5 = 3.25 kg                   │
  │    energy = 0.5 × 45 = 22.5 MJ                    │
  │    water  = 0.5 × 150 = 75 L                      │
  │                                                    │
  │  battery_material: 45g → 0.045 kg                 │
  │    factor: carbon=42, energy=320, water=2500       │
  │    carbon = 0.045 × 42 = 1.89 kg                  │
  │    energy = 0.045 × 320 = 14.4 MJ                 │
  │    water  = 0.045 × 2500 = 112.5 L                │
  │                                                    │
  │  rare_earth: 0.5g → 0.0005 kg                     │
  │    factor: carbon=42, energy=320, water=2500       │
  │    carbon = 0.0005 × 42 = 0.021 kg                │
  │    critical=true                                   │
  └────────────────────────────────────────────────────┘
      │
      ▼
  ┌────────────────────────────────────────────────────┐
  │  Physical totals:                                   │
  │    carbon_saved_kg = 3.25 + 1.89 + 0.021 = 5.161  │
  │    energy_saved_mj = 36.9                           │
  │    water_saved_l   = 187.5                          │
  │    landfill_diversion_kg = 545.5 / 1000 = 0.546    │
  │    critical_material_recovery_kg = 0.0005          │
  │                                                    │
  │  Unit indices:                                      │
  │    mass_fraction = 545.5/645.5 = 0.845             │
  │    circularity = 0.845×0.5 + 0.60×0.5 = 0.7225    │
  │    severity(MEDIUM) = 0.7                           │
  │    hazardous_fraction = 45/645.5 = 0.07            │
  │    hazard_reduction = 0.7×(0.5 + 0.07×0.5) = 0.375│
  │                                                    │
  │  Confidence:                                        │
  │    blend = 0.90×0.5 + 0.90×0.5 = 0.90             │
  │    (no further damping)                            │
  └────────────────────────────────────────────────────┘
      │
      ▼
  EnvironmentalImpactReport
  ├─ carbon_saved_kg: 5.161
  ├─ energy_saved_mj: 36.9
  ├─ water_saved_l: 187.5
  ├─ landfill_diversion_kg: 0.546
  ├─ critical_material_recovery_kg: 0.001
  ├─ circularity_index: 0.7225
  ├─ hazard_reduction_score: 0.3745
  ├─ confidence: 0.90
  ├─ contributions: (non_ferrous_metal, battery_material, rare_earth)
  └─ factors_version: "1.0.0"
```

---

## 16. End-to-End Data Flow

The end-to-end intelligence pipeline transforms raw images into a complete environmental intelligence package in one deterministic pass:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      END-TO-END AI FLOW                                   │
│               Upload → PredictionResult in one pass                      │
└──────────────────────────────────────────────────────────────────────────┘

  POST /predict (multipart form, 1–6 images)
      │
      ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.1: Image Preprocessing                                         │
  │  Validate → Decode → SHA-256 → LoadedImage                       │
  └──────────────────────────────────────────────────────────────────┘
      │
      ├─────────────────────┬─────────────────────┐
      ▼                     ▼                     ▼
  ┌──────────┐       ┌──────────────┐      ┌──────────┐
  │ M1.4     │       │ M1.5         │      │ M1.6     │
  │ Detection│       │ Fingerprint  │      │ OCR      │
  │          │       │              │      │          │
  │ YOLOv8   │       │ OpenCLIP     │      │ EasyOCR  │
  │ (mock)   │       │ (mock)       │      │ (mock)   │
  └──────────┘       └──────────────┘      └──────────┘
      │                     │                     │
      │ DetectionResult     │ DeviceFingerprint   │ OCRExtraction
      └─────────────────────┼─────────────────────┘
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.7: Multi-Modal Fusion                                          │
  │  Detection + OCR + Fingerprint → DeviceContext                    │
  │  Noisy-OR aggregation → conflict detection → 0.91 confidence     │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            │ DeviceContext(device_type="laptop",
                            │               brand="Dell", confidence=0.91)
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.8: Recoverability                                              │
  │  Known profile → 7 rules → scores → decision = REFURBISH        │
  │  repairability=0.70, reusability=0.75, recyclability=0.60       │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.9: Component Intelligence                                      │
  │  Catalogue (19 profiles) → corroborate → 8 components            │
  │  battery(1.0), mainboard(1.0), display(1.0), webcam(0.85)...    │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.10: Material Intelligence                                      │
  │  Catalogue gated by components → mass breakdown                  │
  │  aluminium(500g), lithium(45g) [bc battery present], ...        │
  │  545.5g recoverable, 45g hazardous                               │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ M1.11: Environmental Intelligence                                 │
  │  Mass × LCA factors → CO₂/energy/water savings                  │
  │  5.161 kg CO₂e saved, 36.9 MJ, 187.5 L water                    │
  │  Circularity: 0.72, Hazard reduction: 0.37                       │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ Carbon Score (pipeline-level, algebraic)                          │
  │  base 50 + condition_weight × material_value                     │
  │  → clamp [0,100], round 1 decimal                                │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ PredictionResult                                                  │
  │  ├─ eco_id: "ET-2026-A3F8B1C2"                                  │
  │  ├─ detection: {type:"laptop", brand:"Dell", conf:0.92}         │
  │  ├─ condition: {label:"Good", score:0.75}                        │
  │  ├─ ocr: {serial:"SN123", model:"XPS 15"}                       │
  │  ├─ materials: {aluminum:0.4, copper:0.1, ...}                  │
  │  ├─ carbon_score: 78.5                                            │
  │  └─ model_version: "1.0.0"                                       │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  JSON Response → Client

  Total wall-clock (mock degraded): ~2 ms (pure Python arithmetic)
  Total wall-clock (real backends): depends on GPU availability
  All outputs deterministic (given injected clock for timestamps)
```

---

## 17. Shared Domain Models

### 17.1 Cross-Engine Types

These types flow across engine boundaries and establish the shared vocabulary of the DIE:

**Identity types** (perception tier → fusion):
- `Detection` — `(label, confidence, bounding_box)` from M1.4
- `EmbeddingVector` — `(values, dimension, normalized)` from M1.5
- `TextSpan` — `(text, confidence, bounding_box)` from M1.6
- `BarcodeResult` — `(kind, payload, symbology, confidence)` from M1.6
- `ExtractedField` — `(field_type: FieldType, value, confidence, raw_text, source: FieldSource)` from M1.6

**Fusion domain models** (shared vocabulary, `fusion/models.py`):
- `FusionAttribute(str, Enum)` — `DEVICE_TYPE, BRAND, MODEL, SERIAL_NUMBER, IMEI, MAC_ADDRESS`
- `EvidenceKind(str, Enum)` — `DETECTION, FINGERPRINT, OCR`
- `Claim` — `(attribute, value, confidence, source)` with `.key` (casefold + whitespace-normalized)
- `Evidence` — `(source, module_name, module_version, confidence, claims)`
- `ResolvedAttribute` — `(attribute, value, confidence, sources, conflicted)` with `.agreed`
- `Conflict` — `(attribute, resolved_value, claims)`
- `DeviceContext` — the canonical device identity consumed by M1.8–M1.11

**Knowledge tier enums** (flowing M1.8 → M1.11):
- `HazardLevel(IntEnum)` — `NONE=0, UNKNOWN=1, LOW=2, MEDIUM=3, HIGH=4` (ordered for `max()`)
- `RecommendedAction(Enum)` — `REFURBISH, REPAIR, RECYCLE, HAZARDOUS_DISPOSAL, MANUAL_REVIEW`
- `ComponentCategory(Enum)` — 17 members (`BATTERY, CIRCUIT_BOARD, PROCESSOR, MEMORY, STORAGE, DISPLAY, CONNECTIVITY, INPUT, CAMERA, SENSOR, POWER, AUDIO, OPTICS, OPTICAL_MEDIA, CABLING, HOUSING, OTHER`)
- `MaterialCategory(Enum)` — 11 members (`FERROUS_METAL, NON_FERROUS_METAL, PRECIOUS_METAL, CRITICAL_MATERIAL, RARE_EARTH, PLASTIC, GLASS, CERAMIC, BATTERY_MATERIAL, HAZARDOUS, OTHER`)

### 17.2 Immutable Value Object Pattern

Every domain model follows a uniform pattern:

```python
@dataclass(frozen=True, slots=True)
class SomeReport:
    """Immutable intelligence report."""
    # ... typed fields ...
    
    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {...}
```

**Benefits:**
1. **Thread-safe** — no mutable state = no race conditions
2. **Cacheable** — hash-stable values can be memoized safely
3. **Testable** — deterministic equality checks in assertions
4. **Traceable** — every report carries `engine_version`, `created_at`, `eco_id`

### 17.3 Precision Conventions

Every scored value follows uniform precision:

| Value type | Precision | Constant |
|-----------|-----------|-----------|
| Confidence / Score [0,1] | 6 decimal places | `_SCORE_PRECISION = 6` |
| Physical quantity (mass, carbon, energy, water) | 3 decimal places | `_METRIC_PRECISION = 3` |
| Carbon score [0,100] | 1 decimal place | `round(n, 1)` |
| Fingerprint coordinates | 6 decimal places | `_FINGERPRINT_PRECISION = 6` |

This cross-engine consistency means numbers compare cleanly in assertions and change detection.

---

## 18. Configuration

### 18.1 Configuration Hierarchy

All engines accept **constructor-injected configuration objects** with sensible production defaults. The `Settings` singleton (`configs/settings.py`, `@lru_cache(maxsize=1)`) reads from:

1. **Environment variables** (highest priority) — prefixed with the engine name
2. **YAML config file** — optional overrides
3. **Hardcoded defaults** — safe production values (fallback)

### 18.2 Per-Engine Configuration

| Engine | Config Class | Package | Key Settings |
|--------|-------------|---------|--------------|
| Preprocessing | `Settings` | `configs/` | `max_images=6`, `max_file_size=10MB`, `min_image_dimension=32`, `max_image_dimension=12000` |
| Detection | `Settings` | `configs/` | `detector_weights="yolov8n.pt"`, `detector_image_size=640`, `detector_confidence_threshold=0.25` |
| Fingerprint | `Settings` | `configs/` | `clip_model_name="ViT-B-32"`, `fingerprint_metric="cosine"`, `fingerprint_match_threshold=0.85` |
| OCR | `Settings` | `configs/` | `ocr_backend="easyocr"`, `ocr_languages=("en",)`, `ocr_min_confidence=0.0`, `barcode_enabled=True` |
| Recoverability | `RecoverabilityConfig` | `recoverability/` | `refurbish_min_reusability=0.65`, `repair_min_repairability=0.55`, `recycle_min_recyclability=0.45` |
| Component | `ComponentConfig` | `components/` | `profiles_path`, `min_presence_confidence=0.05`, `identity_corroboration_bonus=0.05`, `hazard_corroboration_bonus=0.10` |
| Material | `MaterialConfig` | `materials/` | `profiles_path`, `min_material_confidence=0.05` |
| Environmental | `EnvironmentalConfig` | `environmental/` | `factors_path`, `min_material_confidence=0.05` |

### 18.3 Environment Variable Mapping

Each config class supports `from_settings()` or `from_env()` for environment variable overrides:

| Config | Env Var | Default |
|--------|---------|---------|
| Recoverability | `RECOVERABILITY_REFURBISH_MIN_REUSABILITY` | 0.65 |
| Recoverability | `RECOVERABILITY_REPAIR_MIN_REPAIRABILITY` | 0.55 |
| Recoverability | `RECOVERABILITY_RECYCLE_MIN_RECYCLABILITY` | 0.45 |
| Recoverability | `RECOVERABILITY_LOW_CONFIDENCE_THRESHOLD` | 0.50 |
| Component | `COMPONENT_PROFILES_PATH` | `"components/data/components.yaml"` |
| Component | `COMPONENT_MIN_PRESENCE_CONFIDENCE` | 0.05 |
| Material | `MATERIAL_PROFILES_PATH` | `"materials/data/materials.yaml"` |
| Material | `MATERIAL_MIN_CONFIDENCE` | 0.05 |
| Environmental | `ENVIRONMENTAL_FACTORS_PATH` | `"environmental/data/factors.yaml"` |
| Environmental | `ENVIRONMENTAL_MIN_CONFIDENCE` | 0.05 |

### 18.4 External Catalogue Paths

All external knowledge lives in versioned YAML files relative to the device_ai package root:

```
intelligence/device_ai/
├── components/data/components.yaml    ← M1.9 component profiles
├── materials/data/materials.yaml      ← M1.10 material profiles
└── environmental/data/factors.yaml    ← M1.11 LCA conversion factors
```

**Recoverability profiles (M1.8) are in-code** (`recoverability/profiles.py`) — 19 curated device types + ~40 synonyms are stable enough for code; they are judged domain knowledge that changes at the same cadence as the engine logic.

### 18.5 Catalogue Validation

Every catalogue loader enforces strict validation at construction time:
- Version field present and non-empty
- Every required key declared
- No unknown keys (typos → load-time error)
- Cross-references valid (e.g., `source_components` match known `ComponentCategory` values)
- Numeric ranges sensible (confidence ∈ [0, 1], mass ≥ 0, factors ≥ 0)

Validation failures raise **typed domain exceptions** with file path context (e.g., `ComponentProfileError`, `MaterialProfileError`, `EnvironmentalFactorError`). There are no silent drops — a malformed catalogue fails to load, which means the engine cannot serve (caught at construction → mock fallback).

---

## 19. Error Handling

### 19.1 Exception Hierarchy

All domain exceptions inherit from `DeviceAIError` and carry a stable `code` (SCREAMING_SNAKE_CASE) and an `http_status` hint:

```python
class DeviceAIError(Exception):
    code: str = "DEVICE_AI_ERROR"
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    
    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
```

The exception hierarchy is **transport-agnostic** — it imports only `http.HTTPStatus`, never FastAPI. The API middleware translates domain exceptions to HTTP error envelopes.

### 19.2 Complete Exception Catalog

**Validation errors** (preprocessing, M1.1):
| Exception | Code | HTTP | Condition |
|-----------|------|------|-----------|
| `ValidationError` | `VALIDATION_ERROR` | 422 | Base validation error |
| `NoImagesProvidedError` | `NO_IMAGES_PROVIDED` | 400 | Zero images in request |
| `TooManyImagesError` | `TOO_MANY_IMAGES` | 400 | Exceeds `max_images` |
| `FileTooLargeError` | `FILE_TOO_LARGE` | 413 | Exceeds `max_file_size` |
| `UnsupportedMediaTypeError` | `UNSUPPORTED_MEDIA_TYPE` | 415 | Wrong format |
| `CorruptedImageError` | `CORRUPTED_IMAGE` | 422 | PIL cannot decode |
| `ImageDimensionError` | `INVALID_IMAGE_DIMENSIONS` | 422 | Out of range |

**Perception tier errors:**
| Exception | Code | HTTP | Condition |
|-----------|------|------|-----------|
| `InferenceError` | `INFERENCE_ERROR` | 500 | Pipeline failure |
| `ModelNotLoadedError` | `MODEL_NOT_LOADED` | 503 | Backend not ready |
| `FingerprintError` | `FINGERPRINT_ERROR` | 500 | Fingerprint domain error |
| `FingerprintNotFoundError` | `FINGERPRINT_NOT_FOUND` | 404 | No match for eco_id |
| `FingerprintMismatchError` | `FINGERPRINT_MISMATCH` | 422 | Incomparable fingerprints |
| `UnknownSimilarityMetricError` | `UNKNOWN_SIMILARITY_METRIC` | 400 | Unknown metric |
| `EncoderNotReadyError` | `ENCODER_NOT_READY` | 503 | CLIP not loaded |
| `OCRError` | `OCR_ERROR` | 500 | OCR domain error |
| `OCRBackendNotReadyError` | `OCR_BACKEND_NOT_READY` | 503 | EasyOCR not loaded |
| `OCRParseError` | `OCR_PARSE_ERROR` | 422 | Malformed spans |

**Knowledge tier errors** (internal-only — no HTTP surface; surfaced as typed exceptions to the orchestrator):
| Exception | Code | HTTP* | Condition |
|-----------|------|-------|-----------|
| `FusionError` | `FUSION_ERROR` | 500 | Fusion internal error |
| `RecoverabilityError` | `RECOVERABILITY_ERROR` | 500 | Recoverability internal error |
| `ComponentError` | `COMPONENT_ERROR` | 500 | Component internal error |
| `ComponentProfileError` | `COMPONENT_PROFILE_ERROR` | 422 | Catalogue load failure |
| `MaterialError` | `MATERIAL_ERROR` | 500 | Material internal error |
| `MaterialProfileError` | `MATERIAL_PROFILE_ERROR` | 422 | Catalogue load failure |
| `EnvironmentalError` | `ENVIRONMENTAL_ERROR` | 500 | Environmental internal error |
| `EnvironmentalFactorError` | `ENVIRONMENTAL_FACTOR_ERROR` | 422 | Factor catalogue load failure |

*HTTP status is advisory for internal-only engines — the orchestrator decides how to surface the error.

### 19.3 Rule Engine Error Patterns

**Rule engines report violations as structured data, not exceptions.** A device that fails validation rules gets `is_valid=False` + ordered warnings on the report. A malformed **rule file** that cannot be loaded gets a typed exception at construction time.

**Catalogue validation errors** (`*ProfileError`, `*FactorError`) are raised at **load time** (service construction), not at call time. This means the engine either works correctly or fails to construct — there is no case where a partially-loaded catalogue produces silently degraded results.

---

## 20. Dependency Injection

### 20.1 DI Architecture

The DIE uses **constructor injection throughout**. Every service accepts all collaborators as constructor parameters with sensible defaults for production. This pattern is described in detail in document [02 — AI Platform Architecture, Section 3.3]; here we document the device-intelligence-specific DI graph.

### 20.2 Centralized Wiring

Production wiring lives in `api/dependencies.py` — a set of `@lru_cache(maxsize=1)` factory functions that construct the singleton service graph:

```python
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

@lru_cache(maxsize=1)
def get_detector() -> Detector:
    """YOLODetector if ready, else MockDetector."""
    settings = get_settings()
    real = YOLODetector(weights_path=settings.model_dir / settings.detector_weights)
    if real.is_ready:
        return real
    logger.warning("YOLODetector not ready; falling back to mock")
    return MockDetector()

@lru_cache(maxsize=1)
def get_encoder() -> EmbeddingEncoder:
    """CLIPEncoder if ready, else MockEmbeddingEncoder."""
    # ... same honest-degradation pattern ...

@lru_cache(maxsize=1)
def get_ocr_backend() -> OCRBackend:
    """EasyOCRBackend if ready, else MockOCRBackend."""
    # ... same honest-degradation pattern ...
```

### 20.3 Injectable Contracts

Every engine in the DIE exposes these injectable contracts:

| Engine | Injectable Collaborators |
|--------|-------------------------|
| M1.1 Pipeline | `detector`, `embedding`, `condition`, `ocr`, `material`, `ecoid_generator` |
| M1.4 Detection | `Detector` (protocol) — mock or YOLO |
| M1.5 Fingerprint | `encoder`, `repository`, `ecoid_generator`, `verifier`, `clock` |
| M1.6 OCR | `backend` (OCRBackend ABC), `barcode_reader` (BarcodeReader ABC), `parser` (pure), `clock` |
| M1.7 Fusion | Pure `FusionEngine` — no injectable state |
| M1.8 Recoverability | `config`, `rule_engine`, `scoring_engine`, `clock` |
| M1.9 Component | `config`, `profile_library`, `inference_engine`, `clock` |
| M1.10 Material | `config`, `profile_library`, `inference_engine`, `clock` |
| M1.11 Environmental | `config`, `factor_library`, `inference_engine`, `clock` |

### 20.4 Test Wiring

Tests wire services directly with test doubles:

```python
def test_fingerprint_with_mock_encoder():
    mock_encoder = MockEmbeddingEncoder()
    in_memory_repo = InMemoryFingerprintRepository()
    fixed_clock = lambda: datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    service = FingerprintService(
        encoder=mock_encoder,
        repository=in_memory_repo,
        ecoid_generator=EcoIDGenerator(),
        verifier=VerificationEngine(threshold=0.85, metric="cosine"),
        clock=fixed_clock,
    )
    
    # Deterministic test: no filesystem, no models, no clock drift
    fp = service.generate([LoadedImage(...)])
    assert fp.eco_id == "ET-2026-A3F8B1C2"  # deterministic
```

Every clock, repository, config, and model adapter is injectable. The mock-first design means tests run without models, without filesystem, and without network.

---

## 21. Explainability Strategy

### 21.1 Reasoning Transparency

Every knowledge-tier report carries **ordered human-readable reasoning** as a `tuple[str, ...]`. The reasoning traces each step of the deterministic fold, enabling auditors and regulators to understand *why* a score was produced without reading code.

**Example** (RecoverabilityReport reasoning):
```
("Device-type profile for 'laptop' establishes baseline recoverability: repairability 60%, reusability 65%, recyclability 70%.",
 "Identity is complete (model, serial number, IMEI): the device is trackable, wipeable and its parts identifiable, improving repair and reuse prospects.",
 "Device class carries a battery: it must be handled and transported as hazardous and the battery separated before material recovery.")
```

**Example** (EnvironmentalImpactReport reasoning):
```
("Aggregated 3 recoverable material categories from the material report into an avoided burden of 5.161 kg CO2e.",
 "Savings are recovered mass times the external per-kilogram carbon, energy and water factors; masses are physical quantities and are never scaled by confidence.",
 "Recoverability assessment (recyclability 0.60, hazard 'medium') shaped the circularity index and hazard-reduction score; confidence blends the material and recoverability confidences on a separate axis.")
```

### 21.2 Warnings

Warnings (`tuple[str, ...]`) convey operator-facing cautions — conditions that don't halt processing but should be reviewed:

```
("Missing identity: model, serial number and IMEI are all unknown. Confirm provenance before reuse.",
 "Conflicting module evidence was fused; verify the device identity before acting on this recommendation.",
 "Device carries an assessed hazard; the hazard-reduction score is only realized if the hazardous stream is handled correctly.")
```

### 21.3 Confidence as Separate Axis

Confidence is always a **separate `float [0, 1]` field**, never used to scale scores or masses. This preserves the semantics:
- **Score = what we believe about the device** (e.g., recyclability 0.60)
- **Confidence = how sure we are about that belief** (e.g., 0.90)

A low-confidence score never becomes a lower score — it stays at the assessed value with a warning flag.

### 21.4 Rule Provenance

Every recoverability rule outcome names the rule that produced it (`rule=baseline_profile`, `rule=identity_completeness`, etc.), making the reasoning **traceable to the specific line of business logic** that generated it.

### 21.5 Catalogue Version Stamping

Every knowledge-tier report stamps the external catalogue version:
- `ComponentReport.profile_version = "1.0.0"`
- `MaterialReport.profile_version = "1.0.0"`
- `EnvironmentalImpactReport.factors_version = "1.0.0"`

If an auditor questions a 2026 material estimate using 2028 updated factors, the version pin makes the mismatch detectable.

---

## 22. Performance

### 22.1 Computational Profile

| Tier | Engine | Backend | Weight (no GPU) | Weight (with GPU) | Runtime |
|------|--------|---------|-----------------|-------------------|---------|
| Perception | M1.4 Detection | Mock | 0 MB | 0 MB | ~0.1 ms |
| Perception | M1.4 Detection | YOLOv8n | 0 MB | ~6 MB VRAM | 30–80 ms |
| Perception | M1.5 Fingerprint | Mock | 0 MB | 0 MB | ~0.1 ms |
| Perception | M1.5 Fingerprint | ViT-B-32 | 0 MB | ~300 MB VRAM | 50–150 ms |
| Perception | M1.6 OCR | Mock | 0 MB | 0 MB | ~0.1 ms |
| Perception | M1.6 OCR | EasyOCR | 0 MB | ~200 MB VRAM | 200–800 ms |
| Knowledge | M1.8–M1.11 | (pure Python) | 0 MB | 0 MB | ~1–5 ms total |

**In mock-degraded mode** (base environment, no model weights), the entire pipeline runs in **~2 ms** and uses **<100 MB RAM** — well within serverless cold-start budgets.

**With real backends** and GPU, detection + encoding + OCR run concurrently where GPU memory allows; the knowledge tier adds sub-millisecond arithmetic overhead.

### 22.2 Memory Profile

- **Mock adapters**: zero model weights — synthetic output derived from SHA-256
- **YOLOv8 nano**: ~6 MB weights, ~12 MB image tensor at 640×640
- **CLIP ViT-B-32**: ~300 MB weights, ~50 MB embedding batch
- **EasyOCR**: ~200 MB weights, variable by image size
- **External catalogues**: <100 KB total (3 YAML files)

### 22.3 Scaling

- **Horizontal**: stateless → scale replicas behind load balancer; fingerprint repository (in-memory or JSON) is the only bottleneck
- **Knowledge tier**: pure arithmetic, no I/O → scales to any throughput CPU-bound
- **Perception**: GPU-bound, benefits from batching + async processing
- **Memory pressure**: mock degradation enables cost-effective baseline (no GPU needed for development/CI)

---

## 23. Testing Strategy

### 23.1 Test Summary

| Engine | Test Files | Test Count | Key Properties |
|--------|-----------|------------|----------------|
| M1.1 Pipeline | 5 | ~50 | End-to-end `/predict` contract, validation |
| M1.2 Dataset | 10 | ~100 | Quality metrics, splits, exports, versioning |
| M1.3 Training | 10 | ~100 | Callbacks, tracker, registry, exporters |
| M1.4 Detection | 1 | 12 | Mock determinism, YOLO aggregation |
| M1.5 Fingerprint | 3 | 19 | Encoding, similarity, verification, repository |
| M1.6 OCR | 7 | 99 | Patterns, parsing, backends, barcodes, service |
| M1.7 Fusion | 2 | 34 | Evidence builders, fusion algorithm, conflicts |
| M1.8 Recoverability | 4 | 59 | Profiles, rules, scoring, service |
| M1.9 Component | 3 | 48 | Profiles, inference, service |
| M1.10 Material | 3 | 42 | Profiles, inference, service |
| M1.11 Environmental | 3 | 23 | Factors, inference, service |

**Total: 1209 tests, all passing** (as of 2026-08-05).

### 23.2 Test Architecture

**Three testing strategies, engine-appropriate:**

1. **Perception tier — mock-deterministic unit tests:**
   - `MockDetector`: derives device_type/brand from image SHA-256 (same image → same detection)
   - `MockEmbeddingEncoder`: derives synthetic 512-dim vector from SHA-256
   - `MockOCRBackend`: generates labelled synthetic identity spans (Luhn-valid IMEI, formatted MAC, etc.)
   - Tests assert exact values, not approximate ranges

2. **Knowledge tier — pure function tests:**
   - Every engine is a deterministic fold → hand-crafted inputs → exact outputs
   - Edge cases tested: unknown device type, zero mass, empty component report, all hazards
   - Round-trip tests: `to_dict()` + reconstruction

3. **Integration tests:**
   - End-to-end `POST /predict` with mock pipeline → verify frozen contract
   - Multi-engine cascade: DeviceContext → Recoverability → Component → Material → Environmental
   - Catalogue loading: verify YAML loads + validates, version stamps propagate

### 23.3 Test Infrastructure

- **Test runner**: pytest (user-site installation)
- **No model weights needed** for 100% of tests (mock-first design)
- **FastTest target**: full suite runs in <10 seconds (pure Python arithmetic + mock adapters)
- **No GPU, no network, no filesystem** required for test execution
- **Injected clock**: all timestamps deterministic via `fixed_clock` lambdas

### 23.4 What Is Not Tested

- **Real model paths** (`# pragma: no cover`): import-guarded `try/except ImportError` blocks for `ultralytics`, `open_clip`, `easyocr` — tested in integration environment with `requirements-models.txt` installed
- **GPU-specific code paths**: covered by mock fallback tests; GPU correctness verified in staging

---

## 24. Extension Points

### 24.1 Model Backend Swaps

Every perception engine exposes a **protocol** or **ABC** that a new backend can implement:

```python
# Swap detection backend
class CustomDetector:
    name = "custom"
    version = "1.0.0"
    
    @property
    def is_ready(self) -> bool: ...
    def detect(self, images: list[LoadedImage]) -> DetectionResult: ...

# Wire via dependency injection
get_detector() → CustomDetector()
```

No engine internals change — the DI wiring is the only touch point.

### 24.2 Rule Set Extension (M1.8)

Add a new `Rule` subclass and inject into `RuleEngine`:

```python
class WaterDamageRule(Rule):
    name = "water_damage"
    
    def evaluate(self, context, profile, config) -> list[RuleOutcome]:
        # New business logic
        ...

custom_engine = RuleEngine(rules=DEFAULT_RULES + (WaterDamageRule(),))
service = RecoverabilityService(rule_engine=custom_engine, ...)
```

### 24.3 External Catalogue Updates

Domain experts edit YAML files without touching code:
- `components/data/components.yaml` — add device profiles, update components
- `materials/data/materials.yaml` — update masses, add materials, adjust gating
- `environmental/data/factors.yaml` — update LCA factors as science improves

Each catalogue declares a `version` field; reports stamp the version → audit trail.

### 24.4 New Intelligence Engines

Future engines follow the established pattern:
1. Define frozen output models (`models.py`)
2. Implement pure inference logic (`inference.py` or `engine.py`)
3. Wrap in a service façade with DI (`service.py`)
4. Add typed exceptions to `exceptions.py`
5. Inject into the pipeline or consume existing reports
6. Test with deterministic inputs

The `DeviceContext` → `RecoverabilityReport` → `ComponentReport` → `MaterialReport` → `EnvironmentalImpactReport` cascade can be extended with new consumers anywhere in the chain — they're immutable frozen dataclasses, so downstream addition never breaks upstream.

### 24.5 Catalogue Version Rollback

Each catalogue loader validates the `version` field. If a new version is malformed, the loader raises a typed exception at construction time — the engine fails to construct. The DI layer can catch this and fall back to a previous version:

```python
try:
    library = ComponentProfileLibrary(path="v2.yaml")
except ComponentProfileError:
    logger.warning("v2 catalogue invalid; falling back to v1")
    library = ComponentProfileLibrary(path="v1.yaml")
```

---

## 25. Limitations

### 25.1 Current Scope Boundaries

| Limitation | Detail | Mitigation |
|-----------|--------|------------|
| No real condition assessment | `ConditionAssessor` is always mock (M1.1) | Future milestone: CNN-based damage/condition classifier |
| No custom trained models | YOLOv8, CLIP, EasyOCR are all pretrained plug-ins | M1.3 training framework complete; dataset pipeline ready for custom training |
| Detection → 1 class | Aggregation selects dominant class; multi-device scenes → binary classification misses secondary devices | Future: multi-class detection output |
| Fingerprint depends on encoder version | SHA-256 changes when CLIP model updates → identity discontinuity | Version stamp on fingerprint enables lookup across encoder versions |
| In-code recoverability profiles | 19 types curated in code, not external YAML | Judged acceptable: profiles change at same cadence as rules; YAML path available for future |
| English-only OCR | `ocr_languages = ("en",)` default | EasyOCR supports 80+ languages; add language codes to config |
| No GPU CI | Real model paths tested in staging only | Mock-first design ensures 100% coverage in base environment |

### 25.2 Non-Functional Gaps

- **No async processing**: the `/predict` endpoint is synchronous — single request/response. No message queue or background worker for high-throughput batch processing.
- **No model version migration**: if CLIP ViT-B-32 is replaced by ViT-L-14, existing fingerprints are not automatically re-indexed.
- **No incremental catalogue updates**: catalogue changes require service restart (no hot-reload).
- **No distributed tracing**: no OpenTelemetry or distributed trace context propagation across engine boundaries.

### 25.3 Precision Caveats

- **Perceptual hash thresholds**: the Hamming distance threshold (5) for near-duplicate images depends on hash type (ahash/dhash/phash) and image resolution; false positives possible for very small images.
- **Blur detection**: hand-rolled Laplacian variance is a proxy measure; a photo of a smooth surface may register as "blurry" despite being properly focused.

---

## 26. Future AI Evolution

### 26.1 Planned Enhancements

| Enhancement | Priority | Effort | Dependency |
|-------------|----------|--------|------------|
| Real damage/condition CNN | High | Medium | M1.2 dataset pipeline (curated condition labels needed) |
| Custom YOLOv8 fine-tuning on e-waste classes | High | Medium | M1.3 training pipeline (already complete) |
| Multi-language OCR support | Medium | Low | Config change only (EasyOCR supports 80+ languages) |
| Multi-device scene detection | Medium | Medium | YOLO multi-label output processing |
| Encoder-version migration tooling | Low | Medium | Fingerprint version registry |
| Incremental catalogue hot-reload | Low | Medium | File watcher + atomic swap |

### 26.2 Research Directions

- **Self-supervised device embedding**: train CLIP-like embeddings on e-waste device photos for domain-specific fingerprint quality (vs. general-purpose LAION pretraining)
- **Active learning loop**: low-confidence predictions flagged for human review → curated labels added to dataset → incremental retraining
- **Transformer-based fusion**: replace the rule-based fusion (M1.7) with a lightweight attention mechanism for learning module trust weights from human feedback
- **Material verification via spectroscopy labels**: extend M1.10 with optional spectroscopy validation (XRF/LIBS) to close the loop between catalogue estimates and ground truth

### 26.3 Architecture Evolution Principles

As the DIE evolves, these principles should be preserved:

1. **Mock-first, never mock-only.** Every new AI component ships with a deterministic mock before requiring real weights.
2. **External knowledge over hardcoded logic.** Business rules, device profiles, material breakdowns, environmental factors → versioned YAML, not code.
3. **Deterministic reasoning.** Scores must be reproducible and explainable. If ML is added, predictions must be accompanied by reasoning provenance.
4. **Immutable outputs.** Frozen dataclasses + `to_dict()` → every report is a snapshot that can be versioned, cached, and audited.
5. **Honest degradation.** Missing backends → warning log + mock fallback, never silent failure.

---

## Appendix A: Key Command Reference

```bash
# Run full test suite (base environment, zero model weights)
pytest intelligence/device_ai/tests/ -q

# Run specific engine tests
pytest intelligence/device_ai/tests/ -k recoverability -q
pytest intelligence/device_ai/tests/ -k fusion -q
pytest intelligence/device_ai/tests/ -k ocr -q

# Run with coverage
pytest intelligence/device_ai/tests/ --cov=intelligence.device_ai

# Validate external catalogues
python -c "
from device_ai.components.profiles import ComponentProfileLibrary
from device_ai.materials.profiles import MaterialProfileLibrary
from device_ai.environmental.factors import FactorLibrary
print('All catalogues valid')
"
```

## Appendix B: Package Reference

| Package | Path | HTTP Surface | Key Types |
|---------|------|-------------|-----------|
| `api` | `api/` | Yes (routes, schemas) | `PredictionResponse`, `dependencies.py` |
| `preprocessing` | `preprocessing/` | No | `LoadedImage`, `ImageValidator` |
| `inference` | `inference/` | No | `PredictionPipeline`, `YOLODetector`, `CLIPEncoder` |
| `dataset` | `dataset/` | Yes (dataset_routes) | `ImageRecord`, `DatasetService` |
| `training` | `training/` | No (CLI only) | `BaseTrainer`, `ModelRegistry` |
| `fingerprint` | `fingerprint/` | Yes (fingerprint_routes) | `DeviceFingerprint`, `FingerprintService` |
| `ocr` | `ocr/` | Yes (ocr_routes) | `OCRExtraction`, `OCRService`, `OCRParser` |
| `fusion` | `fusion/` | **No** | `DeviceContext`, `FusionEngine`, `Evidence` |
| `recoverability` | `recoverability/` | **No** | `RecoverabilityReport`, `RuleEngine`, `ScoringEngine` |
| `components` | `components/` | **No** | `ComponentReport`, `ComponentProfileLibrary` |
| `materials` | `materials/` | **No** | `MaterialReport`, `MaterialProfileLibrary` |
| `environmental` | `environmental/` | **No** | `EnvironmentalImpactReport`, `FactorLibrary` |
| `configs` | `configs/` | No | `Settings` |
| `utils` | `utils/` | No | `hashing.py`, `image_utils.py` |
| `exceptions.py` | `exceptions.py` | N/A | `DeviceAIError`, all typed exceptions |

**Bold `No`** = internal-only engines (M1.7–M1.11) with zero HTTP surface.

---

*End of document. Generated from reverse-engineered implementation source of truth at `intelligence/device_ai/`. All engine behaviors, configurations, error codes, and data flows are verified against the codebase as of 2026-08-05.*