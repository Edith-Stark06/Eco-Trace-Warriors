# Device Detection Training Foundation

**Sprint:** P4.1.1 — Device Detection Dataset & Training Foundation  
**Component:** Device Intelligence Engine (DIE) — YOLO Detector Training  
**Status:** Active  
**Scope:** Training preparation only. This document defines the training
foundation, evaluation metrics, and configuration variants for production YOLO
training. It does **not** train any model, download any weights, or fetch any
datasets.

---

## 1. Purpose

This document describes how the Device Intelligence Engine's **YOLO detector**
is trained using the existing training platform (`intelligence/device_ai/training/`,
milestone M1.3) and the dataset pipeline (`intelligence/device_ai/dataset/`,
milestone M1.2).

The training foundation **reuses the platform end to end** rather than
duplicating any functionality. Every concept below maps to an already-implemented
module or configuration file — this specification introduces **no new training
code** and simply composes the existing infrastructure.

| Concept | Implementation | Configuration |
| --- | --- | --- |
| Base training lifecycle | `training/core/trainer.py::BaseTrainer` | Abstract epoch loop, callbacks, provenance |
| YOLO integration | `training/detector/yolo_trainer.py::YOLOTrainer` | Delegates to Ultralytics, reuses platform |
| Run configuration | `training/config.py::RunConfig` | Pydantic value objects + YAML loader |
| Variant configs | `training/configs/detector_yolo11*.yaml` | YOLO11n / YOLO11s / YOLO11m |
| Artifacts & checkpoints | `training/registry/artifact_manager.py` | Reproducible directory layout |
| Model registry | `training/registry/model_registry.py` | JSON-backed provenance records |
| Experiment tracking | `training/experiments/tracker.py` | JSON / MLflow backends |
| Evaluation metrics | `training/detector/evaluation.py::extract_metrics` | mAP, precision, recall, F1 |
| ONNX export | `training/core/exporter.py` | Honest skipped-export when backend absent |

> **Critical constraint:** The detector interface
> (`inference/yolo_detector.py::YOLODetector`) is **frozen**. This training
> foundation produces artifacts consumed by that interface; it does not change
> how inference works.

---

## 2. Design Principles

- **Reuse, don't duplicate.** YOLOTrainer **delegates** the epoch loop to
  Ultralytics (which already provides resume, early-stopping, checkpointing, and
  native MLflow logging) while **reusing** the platform's provenance and
  reporting surface (ArtifactManager, ModelRegistry, ExperimentTracker,
  ExportRecord). Reimplementing the training loop through `BaseTrainer`'s
  `train_step` / `validation_step` hooks would duplicate functionality
  Ultralytics provides.
  
- **Reproducible.** Every run is described by a validated `RunConfig` (immutable
  Pydantic value object) that records: model name, trainer key, hyper-parameters,
  optimizer settings, dataset version, Git commit, and free-form tags. The
  platform embeds this config verbatim in experiment records and model-registry
  entries, so a run is fully reproducible from its serialised form.

- **Modular backends.** Ultralytics (and torch/onnx/mlflow/hydra) are **optional**
  heavy dependencies (`requirements-models.txt`). YOLOTrainer uses import guards
  and raises an honest `TrainingError` when the backend is unavailable, so the
  base environment (and the full test suite) runs without them.

- **Dependency injection.** Every collaborator (artifacts, tracker, registry,
  callbacks, clock, Git commit) is injected, so the training lifecycle is
  unit-testable without touching the wall clock, filesystem, or globals.

- **Honest failure.** When a required input (data config, base weights, backend)
  is missing, the platform says so with a `TrainingError` rather than faking a
  run or silently degrading to a mock.

---

## 3. Training Platform Overview

The M1.3 training platform (`intelligence/device_ai/training/`) provides the
reusable ecosystem that every future model plugs into. It contains **no** model
implementations; instead it offers:

### 3.1 Core Abstractions

- **`BaseTrainer(ABC)`** — abstract training lifecycle with fully injected
  collaborators. Defines the contract:
  - `build_model()` — construct the model from configured weights.
  - `train_loader()` / `val_loader()` — data loaders (may be empty iterables
    when the backend owns data loading).
  - `train_step(model, batch)` / `validation_step(model, batch)` — per-batch
    hooks (may raise `NotImplementedError` when the backend owns the loop).
  - `fit()` — orchestrate the run: seed → tracked run → epoch loop → checkpoint
    → register `ModelRecord` → return `TrainingHistory`.

- **`TrainerRegistry`** — maps string keys (`"yolo"`, `"mock"`) to `BaseTrainer`
  subclasses. Trainers self-register via the `@default_registry.register(...)`
  decorator at import time.

- **`Evaluator` + `build_evaluation_document(...)`** — framework-agnostic
  evaluation-report builder (JSON + HTML) that adapts any model's validation
  result onto a standard schema (metrics table, benchmark comparison,
  recommendations).

- **`ExportRecord` + `export_model(...)`** — framework-agnostic export
  orchestration. Returns a `SkippedExport` when the backend (torch/onnx) is
  absent rather than failing.

### 3.2 Collaborators (Injected)

- **`ArtifactManager`** — reproducible directory layout under `artifact_dir`:
  - `checkpoints/` — model weights (`.pt`, `.pth`, `.onnx`).
  - `exports/` — exported artifacts with metadata JSON.
  - `reports/` — evaluation reports (JSON + HTML).
  
- **`ModelRegistry`** — JSON-backed registry (`models/registry.json`) recording
  `ModelRecord` per trained artifact: name, version, dataset version, created
  timestamp, Git commit, metrics, checkpoint path, export formats, config.

- **`ExperimentTracker`** — pluggable experiment backend (`json` / `mlflow` /
  `none`). The platform uses it to:
  - Open a tracked run (with run ID, experiment name, config dict).
  - Log metrics (step-indexed).
  - Set a summary (training time, commit, device, export formats).

- **Callbacks** — `ModelCheckpoint` (save best model by monitored metric),
  `LoggingCallback` (loguru progress), `EarlyStopping` (optional, when
  patience > 0). Built by `BaseTrainer._default_callbacks()` and triggered at
  epoch boundaries.

### 3.3 Configuration

Run configuration is composed from YAML via `load_config(path, overrides=...)`:

```python
@dataclass(frozen=True)
class RunConfig:
    model_name: str              # Registry key (e.g. "device-detector-yolo11n")
    trainer: str                 # Trainer registry key (e.g. "yolo")
    experiment_name: str         # Grouping label for tracker
    training: TrainingConfig     # Batch size, epochs, device, seed, image size, ...
    optimizer: OptimizerConfig   # Optimizer, LR, weight decay, scheduler, ...
    tags: dict[str, str]         # Free-form provenance metadata
```

The loader supports Hydra-compatible `defaults` composition via lightweight
PyYAML (`_compose`, `_deep_merge`), so configs work today without `hydra-core`
installed. When `hydra-core` is added later (it's in `requirements-models.txt`),
the same YAML files are directly compatible with a full Hydra pipeline.

---

## 4. YOLOTrainer Integration

`training/detector/yolo_trainer.py::YOLOTrainer` is the first **real** trainer
to plug into the M1.3 platform. It is registered under the key `"yolo"` via
`@default_registry.register("yolo")`.

### 4.1 How YOLOTrainer Reuses the Platform

Rather than implement the epoch loop through `BaseTrainer`'s `train_step` /
`validation_step` hooks (which would **duplicate** Ultralytics functionality),
YOLOTrainer **overrides `fit()`** to delegate the training loop to
`model.train(...)` while still **reusing** the platform for provenance:

| Platform component | How YOLOTrainer reuses it |
| --- | --- |
| **ArtifactManager** | Passes `artifacts.checkpoints` as Ultralytics' `project` dir; copies `best.pt` into the artifact tree post-train. |
| **ModelRegistry** | Auto-registers a `ModelRecord` capturing: model name/version, dataset version, created timestamp, Git commit, metrics, checkpoint path, export formats, full run config. |
| **ExperimentTracker** | Opens a tracked run (`run_id`, `experiment_name`, `config`) before training; logs extracted metrics (`extract_metrics(results)`); sets summary (training time, commit, device, exports). |
| **Callbacks** | YOLOTrainer does **not** drive the platform's callbacks during the loop (Ultralytics owns early-stopping/checkpointing), but the `fit()` override still respects the platform's callback contract for pre/post-run hooks if needed. |
| **ExportRecord** | After training, optionally exports to ONNX via `export_model(...)`; records a `SkippedExport` when the backend is absent. |
| **TrainingHistory** | Returns a `TrainingHistory` of the same shape `BaseTrainer.fit()` produces, so downstream code (reports, registry queries) sees a uniform contract. |

**The five abstract hooks** (`build_model`, `train_loader`, `val_loader`,
`train_step`, `validation_step`) are still implemented (the ABC requires them)
but are **not driven** because `fit()` is overridden:

- `train_loader()` / `val_loader()` return empty iterables `()` — Ultralytics
  owns data loading.
- `train_step()` / `validation_step()` raise `NotImplementedError` with a
  message documenting that the loop is delegated.

### 4.2 Constructor Signature

```python
YOLOTrainer(
    config: RunConfig,
    settings: Settings,
    *,
    data_config: Path | None = None,        # Path to YOLO data.yaml (required for real training)
    yolo_factory: Callable[[str], Any] | None = None,  # Injected for testing
    export_onnx: bool = True,               # Attempt ONNX export post-train
    artifacts: ArtifactManager | None = None,
    tracker: ExperimentTracker | None = None,
    registry: ModelRegistry | None = None,
    clock: Callable[[], datetime] | None = None,
    commit: str | None = None,
)
```

**Key parameters:**

- `data_config` — path to a YOLO `data.yaml` describing the dataset (produced by
  the dataset pipeline's YOLO export, see `docs/ai/device_detection_dataset.md`).
  Required for a real `fit()`; may be omitted in tests that inject a fake
  `yolo_factory` ignoring it.
  
- `yolo_factory` — callable mapping base-weights string → model object. Injected
  by tests; defaults to constructing a real `ultralytics.YOLO` when the backend
  exists. Raises `TrainingError` if neither a factory nor Ultralytics is
  available.

- All other collaborators default to building from `settings` when omitted, per
  the platform's dependency-injection contract.

### 4.3 Lifecycle: fit()

1. **Seed everything** — `seed_everything(config.training.seed)` for reproducibility.
2. **Build model** — `build_model()` uses `settings.detector_weights` or the
   injected `yolo_factory`.
3. **Open tracked run** — `tracker.run(run_id, experiment_name, config.to_dict())`.
4. **Delegate training** — call `model.train(data=str(data_config), epochs, imgsz,
   batch, patience, device, seed, project, name, resume, verbose=False)`.
   Ultralytics handles:
   - Data loading from `data.yaml`.
   - Epoch loop with progress.
   - Early stopping (native `patience`).
   - Checkpointing (`best.pt`, `last.pt`).
   - Native MLflow logging (when `MLFLOW_TRACKING_URI` is set).
5. **Extract metrics** — `extract_metrics(results)` → {precision, recall, mAP50,
   mAP50_95, f1}.
6. **Log metrics** — `tracker.log_metrics(metrics, step=0)`.
7. **Copy checkpoint** — `best.pt` → `artifacts.checkpoint_path(model_name, version)`.
8. **Export ONNX** — if `export_onnx=True`, call `export_model(...)`; record
   result (exported or skipped).
9. **Set summary** — `tracker.set_summary({training_time, git_commit, device,
   export_formats})`.
10. **Register model** — auto-register a `ModelRecord` with full provenance.
11. **Return history** — `TrainingHistory(model_name, model_version, run_id,
    epochs_completed, training_time, best_epoch, best_metric, final_metrics,
    checkpoint_path, git_commit, device, epochs=[...])`.

**Resume:** Ultralytics supports native resume via `resume=True` when a prior
run exists at the same `project/name` path. YOLOTrainer opts into resume when
the run config has a tag `resume: "true"`.

---

## 5. Variant Configurations

Sprint P4.1.1 provides **three reusable YOLO11 variant configs** under
`intelligence/device_ai/training/configs/`:

| Config | Model name | Variant | Target use case |
| --- | --- | --- | --- |
| `detector_yolo11n.yaml` | `device-detector-yolo11n` | YOLO11n (nano) | Default production target; smallest/fastest; meets edge/mobile latency budget. |
| `detector_yolo11s.yaml` | `device-detector-yolo11s` | YOLO11s (small) | Mid-point; balances latency and accuracy for finer-grained discrimination. |
| `detector_yolo11m.yaml` | `device-detector-yolo11m` | YOLO11m (medium) | Accuracy-first reference; server-side; upper bound on achievable mAP. |

Each config:

- Composes the shared `training` and `optimizer` groups via Hydra-style
  `defaults: [training, optimizer]`.
- Selects `trainer: yolo` (resolves to `YOLOTrainer`).
- Uses distinct `model_name` per variant (so the three sizes register as separate
  model lineages in the JSON-backed registry).
- Records the variant and intended base weights in provenance `tags` (e.g.
  `variant: yolo11n`, `base_weights: yolo11n.pt`).

### 5.1 Base-Weights Selection (No Interface Change)

The base checkpoint (pre-trained YOLO backbone) is **not** a config field.
`TrainingConfig` has no `base_weights` field by design — base weights are read
from `settings.detector_weights` (env `DETECTOR_WEIGHTS`, default `"yolov8n.pt"`,
resolved relative to `MODEL_DIR`).

**Why?** The platform's settings already provide a single, environment-controlled
source for the detector weights used at inference time. Training reuses that same
setting so there's one canonical place to point at a checkpoint, not two.

**Per-variant selection:** Point each variant at its intended backbone at **run
time** via the `DETECTOR_WEIGHTS` environment variable:

```bash
# Train the nano variant
DETECTOR_WEIGHTS=yolo11n.pt \
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config datasets/exports/yolo/data.yaml \
    --run

# Train the small variant
DETECTOR_WEIGHTS=yolo11s.pt \
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11s.yaml \
    --data-config datasets/exports/yolo/data.yaml \
    --run

# Train the medium variant
DETECTOR_WEIGHTS=yolo11m.pt \
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11m.yaml \
    --data-config datasets/exports/yolo/data.yaml \
    --run
```

The `base_weights` tag in each config is **provenance only** — it documents the
intended checkpoint for that variant but does not control what `build_model()`
actually loads. The effective checkpoint is whatever `DETECTOR_WEIGHTS` resolves
to at run time, which is then recorded in the model registry's `ModelRecord` via
the platform's Git commit and config dict.

**Assumption:** The user (or CI pipeline) has already downloaded or placed the
YOLO11n/s/m pre-trained checkpoints at the paths referenced by `DETECTOR_WEIGHTS`.
This sprint does **not** download weights.

---

## 6. Evaluation Metrics

The detector is validated using standard COCO detection metrics, extracted by
`training/detector/evaluation.py::extract_metrics(results)` from an Ultralytics
validation result.

### 6.1 Metrics Produced by extract_metrics()

The platform currently extracts these metrics (all in `[0, 1]` unless noted):

| Metric | Key | Description | Source |
| --- | --- | --- | --- |
| **Precision** | `precision` | True positives / (true positives + false positives) | `results_dict["metrics/precision(B)"]` |
| **Recall** | `recall` | True positives / (true positives + false negatives) | `results_dict["metrics/recall(B)"]` |
| **mAP@50** | `mAP50` | Mean average precision at IoU threshold 0.50 | `results_dict["metrics/mAP50(B)"]` |
| **mAP@50-95** | `mAP50_95` | Mean average precision averaged over IoU thresholds 0.50–0.95, step 0.05 (the COCO primary metric) | `results_dict["metrics/mAP50-95(B)"]` |
| **F1 Score** | `f1` | Harmonic mean of precision and recall: `2 * (P * R) / (P + R)` | Derived on-the-fly from precision and recall |

**Monitored metric:** YOLOTrainer sets `monitor_metric = "mAP50_95"` and
`monitor_mode = "max"`, so the best checkpoint (saved by ModelCheckpoint and
copied into the artifact tree) is the one with the highest mAP@50-95.

### 6.2 Metrics Defined But Not Yet Produced

The sprint defines three additional metrics that are **not yet extracted** by
`extract_metrics()` (Ultralytics does not emit them in its validation `results_dict`):

| Metric | Unit | Definition | How to measure (future) |
| --- | --- | --- | --- |
| **Latency** | ms | End-to-end inference time for a single image (model forward pass only, excluding I/O) | Benchmark the trained model on a reference device (CPU / GPU) with a fixed-size input; report mean over 100+ runs after warm-up. |
| **FPS** | frames/sec | Throughput: images processed per second | `1000 / Latency` for single-image mode; or batch throughput when batch size > 1. |
| **Model Size** | MiB | On-disk size of the checkpoint (`.pt`) or exported artifact (`.onnx`) | `Path(checkpoint_path).stat().st_size / (1024 * 1024)` |

**Why not produced yet?** Latency and FPS require running inference on a
reference device (which this sprint does not do — no training or inference is
performed). Model size can be trivially added post-checkpoint by reading
`best.pt.stat().st_size`, but it was left as a future enhancement to keep the
sprint focused on the training foundation.

**When to add them:** After the first real training run (future sprint), augment
`extract_metrics()` or add a separate `benchmark_model(...)` utility that runs
inference on a small held-out set and appends `{latency_ms, fps, model_size_mib}`
to the metrics dict before logging.

### 6.3 Evaluation Reports

The platform's `Evaluator` + `build_evaluation_document(...)` produce
JSON + HTML evaluation reports from a `ModelRecord`. The report includes:

- **Metrics table** — all recorded metrics (precision, recall, mAP50, mAP50_95, f1).
- **Benchmark comparison** — placeholder section comparing this model to a
  reference baseline (to be populated when a reference model exists).
- **Recommendations** — placeholder section suggesting next steps (e.g. "Precision
  is low; consider adding hard negatives" or "mAP is sufficient; proceed to
  deployment").

The evaluation CLI is:

```bash
python -m device_ai.evaluate --model-name device-detector-yolo11n --model-version 1.0.0
```

This reads the registered `ModelRecord` and writes `reports/{name}_{version}_evaluation.{json,html}`.

---

## 7. Training Instructions

These instructions document the **preparation workflow** for a production training
run. **This sprint does not execute them** — it only creates the configs, docs,
and metric definitions.

### 7.1 Prerequisites

1. **Dataset prepared** — follow `docs/ai/device_detection_dataset.md` end to end:
   - Ingest images into `datasets/raw/`.
   - De-duplicate, quality-gate, annotate, split, augment, export to
     `datasets/exports/yolo/`.
   - Cut a dataset version (e.g. `v1`).
   - Obtain the path to `datasets/exports/yolo/data.yaml` (the YOLO manifest).

2. **Base weights available** — download or place the YOLO11n/s/m pre-trained
   checkpoints:
   ```bash
   # Example (not executed in this sprint)
   # wget https://github.com/ultralytics/assets/releases/download/.../yolo11n.pt -P models/
   # wget https://github.com/ultralytics/assets/releases/download/.../yolo11s.pt -P models/
   # wget https://github.com/ultralytics/assets/releases/download/.../yolo11m.pt -P models/
   ```
   Set `MODEL_DIR` (or leave it at the default `models/`) so
   `DETECTOR_WEIGHTS=yolo11n.pt` resolves correctly.

3. **Optional dependencies installed** — if training on a real GPU:
   ```bash
   pip install -r intelligence/device_ai/requirements-models.txt
   ```
   This installs `torch`, `ultralytics`, `onnx`, `mlflow`, `hydra-core`.

   If the dependencies are absent, `YOLOTrainer.build_model()` raises an honest
   `TrainingError`.

### 7.2 Dry Run (Validate Config)

The CLI's default mode is a **dry run** — it composes and validates the config,
resolves artifact paths, records the Git commit, and prints the run plan **without
training**:

```bash
cd intelligence

python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config ../datasets/exports/yolo/data.yaml
```

Expected output (JSON run plan):

```json
{
  "batch_size": 16,
  "checkpoints_dir": "artifacts/checkpoints",
  "dataset_version": "latest",
  "device": "auto",
  "epochs": 100,
  "experiment_name": "die-detection",
  "git_commit": "<current-commit-sha>",
  "hydra_available": false,
  "learning_rate": 0.001,
  "model_name": "device-detector-yolo11n",
  "model_version": "1.0.0",
  "optimizer": "adamw",
  "reports_dir": "artifacts/reports",
  "trainer": "yolo"
}
```

This validates that the config loads, composes correctly, and all paths resolve.

### 7.3 Real Training Run

To actually train (requires `requirements-models.txt` installed and base weights
available), add `--run`:

```bash
cd intelligence

DETECTOR_WEIGHTS=yolo11n.pt \
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config ../datasets/exports/yolo/data.yaml \
    --run
```

**What happens:**

1. The platform seeds everything with `config.training.seed` (42).
2. `YOLOTrainer.build_model()` constructs `YOLO(settings.detector_weights)`.
3. A tracked run opens (`run_id`, `experiment_name`, full config dict).
4. `model.train(data=..., epochs=100, imgsz=640, batch=16, patience=20, device=auto,
   seed=42, project=artifacts/checkpoints, name=<run_id>, resume=False, verbose=False)`
   delegates the training loop to Ultralytics.
5. Ultralytics handles data loading, the epoch loop, early stopping, checkpointing
   (`best.pt` / `last.pt`), and native MLflow logging.
6. `extract_metrics(results)` pulls precision, recall, mAP50, mAP50_95, f1.
7. Metrics are logged to the tracker (`step=0`).
8. `best.pt` is copied to `artifacts/checkpoints/device-detector-yolo11n_1.0.0.pt`.
9. If `export_onnx=True` (default), the platform attempts ONNX export; records
   `SkippedExport` when the backend is absent.
10. The tracker summary is set: `{training_time, git_commit, device, export_formats}`.
11. A `ModelRecord` is auto-registered in `artifacts/models/registry.json`.
12. `TrainingHistory` is returned.

### 7.4 CLI Overrides

Runtime overrides (without editing the config file):

```bash
# Override batch size and epochs
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config ../datasets/exports/yolo/data.yaml \
    --batch-size 8 \
    --epochs 50 \
    --run

# Override device
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config ../datasets/exports/yolo/data.yaml \
    --device cuda \
    --run

# Override model version (artifact stamp)
python -m device_ai.train \
    --config device_ai/training/configs/detector_yolo11n.yaml \
    --data-config ../datasets/exports/yolo/data.yaml \
    --model-version 1.1.0 \
    --run
```

---

## 8. Post-Training Workflows

### 8.1 Query the Model Registry

List all registered models:

```bash
cd intelligence
python -c "
from device_ai.training.registry.model_registry import ModelRegistry
from device_ai.configs.settings import get_settings

registry = ModelRegistry.from_settings(get_settings())
for record in registry.list_models():
    print(f'{record.name} v{record.version} — dataset {record.dataset_version} — {record.created_at}')
"
```

Get a specific model:

```bash
python -c "
from device_ai.training.registry.model_registry import ModelRegistry, record_to_dict
from device_ai.configs.settings import get_settings
import json

registry = ModelRegistry.from_settings(get_settings())
record = registry.get('device-detector-yolo11n', '1.0.0')
print(json.dumps(record_to_dict(record), indent=2))
"
```

### 8.2 Generate Evaluation Report

```bash
cd intelligence
python -m device_ai.evaluate \
    --model-name device-detector-yolo11n \
    --model-version 1.0.0
```

Produces:
- `artifacts/reports/device-detector-yolo11n_1.0.0_evaluation.json`
- `artifacts/reports/device-detector-yolo11n_1.0.0_evaluation.html`

The report includes: metrics table, benchmark comparison (placeholder), and
recommendations (placeholder).

### 8.3 Export to ONNX (Post-Train)

If ONNX export was skipped during training (backend absent), re-run it:

```bash
cd intelligence
python -m device_ai.export \
    --model-name device-detector-yolo11n \
    --model-version 1.0.0 \
    --formats onnx
```

Honestly reports `SkippedExport` when torch/onnx is unavailable.

---

## 9. Architecture Integration

The training foundation integrates into the Device Intelligence Engine's
broader architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│  Dataset Pipeline (M1.2)                                         │
│  ─────────────────────────────────────────────────────────────  │
│  raw/ → duplicates → quality → annotations → split → augment    │
│  → export (YOLO data.yaml)                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ data.yaml
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Training Platform (M1.3) + YOLOTrainer (M1.4)                  │
│  ─────────────────────────────────────────────────────────────  │
│  RunConfig → YOLOTrainer.fit() → Ultralytics model.train(...)   │
│  → extract_metrics → checkpoint → ONNX export → ModelRecord     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ best.pt / .onnx
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Inference (M1.4)                                                │
│  ─────────────────────────────────────────────────────────────  │
│  YOLODetector(settings.detector_weights) → detect(image) →      │
│  DetectionResult(device_type, confidence, bbox, timestamp)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ DetectionResult
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Downstream Intelligence Engines                                 │
│  ─────────────────────────────────────────────────────────────  │
│  • Component Intelligence (M1.9) — infer likely components       │
│  • Material Intelligence (M1.10) — estimate material composition │
│  • Carbon Intelligence (M2.4) — lifecycle carbon footprint       │
│  • Digital Passport (M2.5) — fused multi-modal report            │
└─────────────────────────────────────────────────────────────────┘
```

**Key contracts:**

- The training foundation **produces** checkpoints that the inference-time
  `YOLODetector` **consumes** via `settings.detector_weights`.
- `YOLODetector` emits `DetectionResult` with a canonical `device_type` (one of
  the 19 types in §3 of the dataset spec).
- Downstream engines (component, material, carbon, passport) consume
  `DetectionResult.device_type` to select the correct profile, so the detector's
  taxonomy alignment is critical.
- The training platform's `ModelRegistry` records full provenance: which dataset
  version, which Git commit, which hyper-parameters, which metrics. This closes
  the loop from prediction → model → dataset.

---

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| **Class imbalance** | Rare classes (e.g. `crt_monitor`, `server`) are under-represented; the model may under-detect them. | Per-class metrics reported in evaluation; targeted collection for under-represented classes; future: class-weighted loss or focal loss. |
| **Global splitting** | The `DatasetSplitter` shuffles globally, not per-class; a small class may have all instances in one split. | Future: stratified splitting. For now: manual inspection of per-class split coverage in the dataset version report. |
| **Base-weights availability** | YOLO11n/s/m pre-trained checkpoints must be manually placed at `DETECTOR_WEIGHTS` paths; this sprint does not download them. | Document the download step in the Prerequisites; add a verification script that checks whether the weights exist before training. |
| **Latency/FPS metrics missing** | `extract_metrics()` does not yet produce latency, FPS, or model size. | Future sprint: add a `benchmark_model(...)` utility that runs inference on a held-out set and appends `{latency_ms, fps, model_size_mib}` to the metrics dict. |
| **Dataset taxonomy drift** | If the component/material knowledge base adds a new device type, the detector's 19-class taxonomy becomes stale. | The taxonomy is explicitly versioned and frozen in the dataset spec (§3); adding a class requires a new dataset version, re-annotation, re-training, and a model version bump. |
| **Ultralytics version drift** | Ultralytics' `results_dict` schema may change across versions, breaking `extract_metrics()`. | Pin `ultralytics==8.3.58` in `requirements-models.txt`; add a version-compatibility test that validates the expected keys exist. |

---

## 11. Assumptions

1. **Base weights are pre-trained on COCO or a similar general object-detection
   dataset.** The YOLO11n/s/m backbones are assumed to carry reasonable feature
   extractors for natural images; fine-tuning adapts them to the 19-device
   taxonomy.

2. **The 19-class taxonomy is sufficient.** No device types outside the canonical
   list (§3 of the dataset spec) are expected in production. If a new type appears
   (e.g. `drone`, `vr_headset`), it requires re-annotation, a new dataset version,
   and re-training.

3. **DETECTOR_WEIGHTS points to a valid YOLO checkpoint.** The platform does not
   validate the checkpoint's architecture or class count before training; a
   mismatched checkpoint will fail during Ultralytics' `model.train(...)`.

4. **The dataset pipeline has already run.** This document assumes
   `datasets/exports/yolo/data.yaml` exists and is correctly formatted (see
   `docs/ai/device_detection_dataset.md`).

5. **Training happens on a machine with sufficient resources.** The medium variant
   (YOLO11m) requires ~8 GiB GPU memory at batch size 16; the nano variant can
   train on CPU (slowly). The platform does not enforce resource requirements.

6. **No training or downloads are performed in Sprint P4.1.1.** This sprint delivers
   configs, docs, and metric definitions only. Actual training is a future sprint.

---

## 12. Future Enhancements

- **Add latency / FPS / model-size metrics** — augment `extract_metrics()` or add
  a `benchmark_model(...)` utility (see §6.2).
- **Stratified splitting** — update `DatasetSplitter` to stratify by class so small
  classes are represented in all splits.
- **Class-weighted loss** — when imbalance is severe, pass class weights to
  Ultralytics' `model.train(cls_weight=...)`.
- **Hyperparameter search** — wrap the training CLI in a search loop (grid / random
  / Bayesian) to find optimal LR / batch size / augmentation strength.
- **Multi-GPU training** — Ultralytics supports DDP; the platform's config can add
  a `world_size` field and pass it through.
- **Continuous evaluation** — after each epoch, run validation on a held-out test
  set and log per-epoch metrics (current implementation logs only final metrics).
- **Base-weights download script** — automate fetching YOLO11n/s/m checkpoints from
  Ultralytics' releases into `models/`.

---

## 13. Related Documents

- `docs/ai/device_detection_dataset.md` — dataset specification (taxonomy, layout,
  annotation format, quality gates, splitting, augmentation, export).
- `intelligence/device_ai/docs/engineering/detector.md` — M1.4 detector
  engineering reference (dataset preparation guide, training instructions).
- `intelligence/device_ai/training/` — M1.3 training platform source
  (`BaseTrainer`, callbacks, model registry, experiment tracking) with
  module-level docstrings documenting each collaborator.
- `docs/engineering/08_AI.md` — AI architecture overview.
- `docs/engineering/03_ARCHITECTURE.md` — system-wide architecture.
- `PROJECT.md` — project vision, scope, and roadmap.