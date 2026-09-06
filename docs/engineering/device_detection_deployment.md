# Device Detection Training & Deployment

**Sprint:** P4.1.3 — Production YOLO Training & Detector Integration
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** Training execution, model registration, deployment process, export formats,
and rollback strategy for the device-detection model. This document connects the
annotated dataset (P4.1.2) to a production-ready trained detector serving predictions
through the existing inference API.

> **Production taxonomy note (added at finalization):** the tooling described in
> this document defaults to the full, code-owned 19-class `DeviceTaxonomy`
> (`dataset/taxonomy.py::load_taxonomy()`), and that remains correct for the
> general-purpose training/manifest pipeline. However, the **currently deployed
> production checkpoint** (`docker_data/device_ai/models/best.pt`, SHA256
> `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92`, served via
> `inference/class_map.py::CANONICAL_CLASSES`) was trained on an **8-class
> subset**: laptop, smartphone, tablet, monitor, printer, mouse, camera,
> headphones. The other 11 taxonomy classes were temporarily dropped for this
> production run due to insufficient training data, not removed from the
> authoritative taxonomy. A future retraining run that builds a `data.yaml` via
> `build_training_manifest()`'s 19-class default will **not** match the frozen
> production checkpoint unless it is explicitly scoped back down to this same
> 8-class subset — do not assume the two are interchangeable.

---

## 1. Purpose

This document is the operational runbook for **training, registering, deploying, and
rolling back** the device-detection YOLO model. It sits downstream of the dataset
pipeline and upstream of the inference API, closing the loop from annotated images to
served predictions:

- **Input:** A versioned, split-aware dataset release (P4.1.2
  `DatasetRelease` + YOLO export).
- **Training:** `YOLOTrainer` delegates the epoch loop to Ultralytics while reusing
  the M1.3 platform for provenance (artifact management, model registry, experiment
  tracking, export records).
- **Output:** A registered `ModelRecord` with mAP metrics, a best-weights checkpoint,
  and ONNX export; a guarded production deployment swapping the served artifact.

Every step below maps to **already-implemented modules** under
`intelligence/device_ai/`. Sprint P4.1.3 introduced **no new architecture and no
interface changes** — it added focused collaborators on top of the M1.3 training
platform and the M1.2 dataset pipeline:

| Concern | Module (P4.1.3 addition) | Reuses |
| --- | --- | --- |
| Split-aware YOLO manifest | `training/detector/data_manifest.py` (`build_training_manifest`) | `DatasetRelease`, `SplitAssignment`, `DeviceTaxonomy` |
| Inference benchmark measurement | `training/detector/benchmark.py` (`benchmark_inference`) | `Timer`, `measure_model_size` |

The pre-existing M1.3 training platform and M1.4 detector are reused unchanged:

| Concern | Module | Configuration source |
| --- | --- | --- |
| YOLO training delegation | `training/detector/yolo_trainer.py` (`YOLOTrainer`) | `@default_registry.register("yolo")` |
| Detection evaluation | `training/detector/evaluation.py` (`DetectionEvaluator`) | Ultralytics validation results |
| Artifact layout | `training/registry/artifact_manager.py` (`ArtifactManager`) | `artifact_dir` (default `artifacts/`) |
| Model registry | `training/registry/model_registry.py` (`ModelRegistry`) | JSON-backed, immutable `ModelRecord` |
| Experiment tracking | `training/experiments/tracker.py` (`ExperimentTracker`) | `experiment_tracker` (`json`/`mlflow`/`none`) |
| Run configuration | `training/config.py` (`RunConfig`) | Hydra-style YAML composition |
| YOLO detector inference | `inference/yolo_detector.py` (`YOLODetector`) | `detector_weights`, `detector_image_size`, `detector_confidence_threshold` |
| Prediction pipeline | `inference/pipeline.py` (`build_detection_pipeline`) | Frozen `Detector` contract |
| Dependency injection | `api/dependencies.py` (`get_pipeline`) | Guarded real/mock swap |

> **Frozen interfaces.** The `Detector` interface
> (`inference/detector.py`), the `Prediction` API (`api/routes/predict.py`), and
> the dataset value objects (`dataset/records.py`) are **frozen**. This runbook
> trains a model those interfaces consume; it does not change them.

---

## 2. Training Execution (the entry point)

### 2.1 CLI command

Training is invoked via `python -m device_ai.train`. The CLI composes a
`RunConfig` from a YAML file, resolves artifact paths, records the Git commit,
and — when `--run` is supplied — delegates to the registered trainer.

**Dry run (default, no training):**

```bash
python -m device_ai.train \
    --config device_ai/training/configs/detector.yaml
```

This validates the configuration and prints the run plan without training.

**Real training run:**

```bash
python -m device_ai.train \
    --config device_ai/training/configs/detector.yaml \
    --data-config <exported-dataset>/data.yaml \
    --run
```

### 2.2 CLI flags

| Flag | Meaning | Default |
| --- | --- | --- |
| `--config` | Path to the run-config YAML. | Packaged `configs/default.yaml` |
| `--trainer` | Trainer registry key (`yolo` for the detector). | From config (`trainer: yolo`) |
| `--data-config` | Path to the YOLO `data.yaml` describing the dataset. | None (**required** for `--run`) |
| `--model-name` | Override the logical model / registry key. | `device-detector` |
| `--model-version` | Override the artifact version stamped onto the record. | `1.0.0` |
| `--epochs` | Override training epochs. | From config |
| `--batch-size` | Override batch size. | From config |
| `--device` | Override the compute-device selector (`cpu`, `0`, `cuda:0`, …). | Auto-resolved |
| `--run` | Attempt a real `fit()`; without it the CLI prints the plan only. | Off (dry run) |

Only flags actually supplied become overrides — unset flags never clobber the
values from the config file or its `defaults` composition.

### 2.3 What happens on `--run`

`train_main` lazily imports the built-in trainer package so `YOLOTrainer`
self-registers under the key `yolo`, resolves the class from the registry, and
instantiates it — passing `data_config` only because the constructor accepts it.
`YOLOTrainer.fit()` then runs the delegated lifecycle:

```
seed → build model → open tracked run → model.train(...) (Ultralytics owns the
epoch loop: resume / early-stop / checkpoint) → copy best.pt into the artifact
tree → export ONNX → register a ModelRecord → return a TrainingHistory
```

The training loop itself (resume, early stopping, checkpointing, callbacks) is
**Ultralytics-native** — the platform does not re-implement it. `YOLOTrainer`
overrides `fit()` precisely so it reuses provenance/registry/tracker/export
without duplicating an epoch loop.

### 2.4 Resume, early stopping, checkpointing

| Capability | How it is driven | Backing detail |
| --- | --- | --- |
| **Resume** | Opt-in via a run tag `resume: "true"` (there is no field on the frozen `TrainingConfig`). | `YOLOTrainer._resume_requested()` → `model.train(resume=True)` |
| **Early stopping** | `training.early_stopping_patience` (detector default `20`). | Forwarded as Ultralytics `patience` |
| **Checkpointing** | Best weights (`best.pt`) copied into the managed artifact tree. | `_store_checkpoint` → `ArtifactManager.checkpoint_path` |
| **Seeding** | `training.seed` (default `42`) for reproducibility. | `seed_everything` + `model.train(seed=…)` |

> **Honest failure.** Ultralytics is a heavy **optional** backend. When it is
> absent and no `yolo_factory` is injected, `fit()` raises `TrainingError`
> rather than faking a run. Likewise, `--run` without `--data-config` raises
> `TrainingError` — you cannot train a detector without a dataset manifest.

---

## 3. Dataset Integration — release → `data.yaml`

### 3.1 The connection (PART 2)

`YOLOTrainer.fit()` requires a `--data-config` pointing at a YOLO `data.yaml`.
The dataset pipeline (P4.1.2) produces a `DatasetRelease` carrying a
`SplitAssignment` (train/val/test tuples of relative paths). The new
`data_manifest.py` module is the **pure composition** that turns one into the
other, honoring the split so validation does not leak into training:

```python
from device_ai.training.detector.data_manifest import build_training_manifest

data_yaml = build_training_manifest(
    release,                       # the P4.1.2 DatasetRelease
    export_root=Path("datasets/exports/yolo"),
    # taxonomy defaults to load_taxonomy() — the canonical 19-class list
)
# → datasets/exports/yolo/data.yaml, referencing train.txt / val.txt / test.txt
```

### 3.2 Split-aware behaviour

| `release.split` | Produced `data.yaml` | Rationale |
| --- | --- | --- |
| **Present** | `train: train.txt`, `val: val.txt`, `test: test.txt` (image-list files written next to the yaml). | Honors the deterministic `SplitAssignment` — train and val are **disjoint**, avoiding the validation leakage a flat `train: images` / `val: images` layout would cause. |
| **`None`** | `train: images`, `val: images`, `test: images` (flat fallback). | Degrades to the `DatasetExporter` flat layout when no split was recorded, so the pipeline still runs end-to-end. |

Every `data.yaml` carries `nc: <taxonomy.num_classes>` (19), the ordered
`names:` list from `DeviceTaxonomy`, and a `# Taxonomy version:` comment for
provenance. `build_training_manifest` raises `ValueError` when
`export_root/images` does not exist — a missing image directory is a hard error,
not a silent empty run.

> **No custom dataset loader.** The manifest is consumed by Ultralytics'
> standard `data=` argument. The platform contributes only the split-aware
> `data.yaml`; the actual data loading is Ultralytics', exactly like the flat
> export produced by `DatasetExporter`.

---

## 4. Evaluation

### 4.1 Detection metrics (PART 4)

`DetectionEvaluator` (`training/detector/evaluation.py`) extracts the standard
object-detection metrics from Ultralytics validation results and records them on
the `ModelRecord`:

| Metric | Field | Meaning |
| --- | --- | --- |
| mAP@50 | `mAP50` | Mean average precision at IoU 0.50. |
| mAP@50-95 | `mAP50_95` | COCO-style mAP averaged over IoU 0.50–0.95 (the **monitored** metric). |
| Precision | `precision` | Box-level precision. |
| Recall | `recall` | Box-level recall. |
| F1 | `f1` | Harmonic mean of precision and recall. |

`mAP50_95` is the trainer's `monitor_metric` (`monitor_mode = "max"`), so it
drives best-checkpoint selection and is reported as `TrainingHistory.best_metric`.

### 4.2 Inference benchmark (PART 4)

When a model is trained, runtime characteristics are measured by
`benchmark_inference` (`training/detector/benchmark.py`), which fills the same
section shape the core evaluator emits as a placeholder:

```python
from device_ai.training.detector.benchmark import benchmark_inference

section = benchmark_inference(
    model, sample,
    device="cpu", batch_size=1, image_size=640,
    warmup=2, runs=20, weights_path=checkpoint,
)
# → {"status": "measured", "latency_ms": …, "throughput_fps": …,
#    "device": …, "batch_size": …, "model_size_bytes": …,
#    "model_size_mb": …, "runs": …}
```

| Measure | Field | How it is derived |
| --- | --- | --- |
| Latency | `latency_ms` | Mean wall-clock per timed batch (`Timer`, `perf_counter`). |
| Throughput | `throughput_fps` | Per-image: `batch_size / mean_batch_seconds`. |
| Model size | `model_size_bytes` / `model_size_mb` | `measure_model_size(weights_path)`; `(0, 0.0)` when absent. |
| Device / batch | `device` / `batch_size` | Echoed from the call for provenance. |

Warmup runs are untimed; `runs < 1` or `batch_size < 1` raise `ValueError`. The
`status: "measured"` section slots into `build_evaluation_document(benchmark=…)`,
replacing the default `status: "placeholder"` section when a real model exists.

### 4.3 Rendering a report

```bash
python -m device_ai.evaluate --model-name device-detector --model-version latest
```

This resolves the registered record and writes JSON + HTML reports under
`artifacts/reports/`, embedding the recorded metrics (and the benchmark section
when supplied).

---

## 5. Model Registration

Every successful `fit()` **auto-registers** an immutable `ModelRecord` via the
reused `ModelRegistry` (JSON-backed, under `artifact_dir`). No manual step is
required. The record captures full provenance:

| Element | `ModelRecord` field | Source |
| --- | --- | --- |
| Model version | `name` + `version` | `config.model_name` / `training.model_version` |
| Metrics | `metrics` | `extract_metrics(results)` (mAP50, mAP50_95, precision, recall, f1) |
| Dataset version | `dataset_version` | `training.dataset_version` (pins the P4.1.2 release) |
| Training config | `tags` + `git_commit` + `framework` | Run tags, resolved commit, `"ultralytics"` |
| Export formats | `export_formats` | Formats that actually exported (e.g. `("onnx",)`) |
| Artifact location | `artifact_location` | POSIX path of the stored best checkpoint |
| Creation timestamp | `created_at` | ISO-8601 UTC from the injected clock |

Records are **immutable and append-only** — re-registering never mutates a prior
record, so the registry retains the full lineage of every trained version. This
immutability is the foundation of the rollback strategy in §8.

---

## 6. Model Export

### 6.1 Formats

| Format | When produced | Mechanism |
| --- | --- | --- |
| **PyTorch** (`.pt`) | Always (the stored best checkpoint). | `_store_checkpoint` copies `best.pt` into the artifact tree. |
| **ONNX** (`.onnx`) | During `fit()` when `export_onnx=True` (default). | `model.export(format="onnx")` → relocated into `artifacts/exports/`. |
| **TorchScript** | On demand via the export CLI. | `python -m device_ai.export` |

### 6.2 Export CLI

```bash
python -m device_ai.export \
    --model-name device-detector \
    --model-version latest \
    --formats pytorch,torchscript,onnx
```

The exporter honestly reports `skipped` for any format whose backend
(torch/onnx) is unavailable rather than silently producing nothing — the same
"optional backend, honest degradation" contract used throughout the platform.

---

## 7. Detector Integration & Deployment

### 7.1 Frozen interface, swapped implementation (PART 7)

Serving a trained model requires **no code change** to the inference path. The
`Detector` interface, `Prediction` API, and pipeline contracts are frozen;
`api/dependencies.py::get_pipeline()` already chooses the real detector when its
artifact resolves and Ultralytics is available, degrading to the mock pipeline
otherwise — the API response schema is identical either way, so swapping models
is transparent to clients.

```
get_pipeline()
  → _build_detector(settings)          # resolves detector_weights under model_dir
      → YOLODetector(weights, image_size, confidence_threshold)
  → detector.is_ready ?
      yes → build_detection_pipeline(detector, model_version, year)   # REAL
      no  → build_mock_pipeline(model_version, year)                  # MOCK
```

### 7.2 Deployment process

1. **Train & register** a model (§2, §5); note the best checkpoint under
   `artifacts/checkpoints/` and the ONNX export under `artifacts/exports/`.
2. **Place the artifact** where the API resolves it: copy the chosen weights
   (`.pt` or `.onnx`) to the location named by `DETECTOR_WEIGHTS`, resolved
   relative to `MODEL_DIR` (default `models/`) when not absolute.
3. **Configure** via environment variables (never hardcode):

   | Setting | Env var | Default | Purpose |
   | --- | --- | --- | --- |
   | Detector weights locator | `DETECTOR_WEIGHTS` | `yolov8n.pt` | File or directory under `MODEL_DIR`. |
   | Model directory | `MODEL_DIR` | `models` | Root for versioned artifacts. |
   | Inference image size | `DETECTOR_IMAGE_SIZE` | `640` | Forwarded to `YOLODetector`. |
   | Confidence threshold | `DETECTOR_CONFIDENCE_THRESHOLD` | `0.25` | Minimum kept-detection confidence. |
   | Reported model version | `MODEL_VERSION` | `1.0.0` | Stamped on every prediction. |

4. **Restart / reload** the API process so `get_pipeline` rebuilds its cached
   singleton. (In tests, `reset_dependency_caches()` clears the `lru_cache`
   singletons — production uses a process restart.)
5. **Verify readiness**: on startup the log line
   `Serving predictions with the real YOLO detector.` confirms the real detector
   is live; `Detector artifact unavailable; serving the mock pipeline.` confirms
   the fallback. A smoke prediction against a known image confirms end-to-end.

### 7.3 Safety of the swap

Because construction **never raises** (`_build_detector` catches every failure
and logs a warning), a missing or corrupt artifact degrades to the mock pipeline
instead of taking the API down. This makes the production swap fail-safe: a bad
deploy serves mock predictions rather than 500s.

---

## 8. Rollback Strategy

The deployment is a **pointer swap**, so rollback is the inverse pointer swap —
no artifact is ever destroyed:

1. **Revert the pointer.** Set `DETECTOR_WEIGHTS` back to the previous artifact
   (the prior version's checkpoint is still on disk under `artifacts/` /
   `MODEL_DIR`) and restart the API. The registry's immutable, append-only
   `ModelRecord` history means the previous version's metrics and
   `artifact_location` are always retrievable
   (`ModelRegistry.resolve(name, "<previous-version>")`).
2. **Fail-safe fallback.** If the previous artifact is unavailable, unset or
   point `DETECTOR_WEIGHTS` at a missing path — the service degrades to the mock
   pipeline (a known-good, deterministic baseline) rather than failing requests.
3. **No history rewrite.** Rollback never edits or deletes a `ModelRecord`;
   it only changes which registered version the API serves. This preserves the
   full audit trail (CLAUDE.md: immutable records, audit trails) and keeps every
   version reproducible from its pinned `dataset_version` + `git_commit`.

| Step | Action | Command / setting |
| --- | --- | --- |
| Identify prior version | Resolve a registered version. | `ModelRegistry.resolve("device-detector", "<version>")` |
| Repoint | Set the weights locator to the prior artifact. | `DETECTOR_WEIGHTS=<prior>.pt` |
| Reload | Restart the API process. | (process restart) |
| Confirm | Check the startup log line and a smoke prediction. | logs + `POST /predict` |

---

## 9. Training Execution Status

> **Training execution is intentionally deferred.** No real annotated device
> dataset — and no Ultralytics/torch backend — is present in this repository's
> base environment, so no weights were trained or committed. This is the honest,
> expected state for Sprint P4.1.3: the sprint delivers a **production-ready
> pipeline**, not model weights.

What **is** confirmed ready and verified in the base environment:

- The `python -m device_ai.train … --run` entry point resolves and instantiates
  `YOLOTrainer` from the registry (verified via injected `yolo_factory` fakes).
- The dataset-release → `data.yaml` connection honors the split and degrades
  correctly (`test_detector_data_manifest.py`).
- The benchmark filler produces the measured evaluation section
  (`test_detector_benchmark.py`).
- `ModelRecord` registration, ONNX export, evaluation metric extraction, and the
  guarded `get_pipeline` real/mock swap are all covered by the existing detector
  test suite.

To run a real training pass once a dataset and backend are available:

```bash
# 1. Build the split-aware manifest from a P4.1.2 release (Python, §3.1).
# 2. Install the optional model backend.
pip install -r requirements-models.txt      # ultralytics + torch + onnx
# 3. Train, register, export.
python -m device_ai.train \
    --config device_ai/training/configs/detector.yaml \
    --data-config datasets/exports/yolo/data.yaml \
    --epochs 100 --batch-size 16 --run
# 4. Deploy (§7): copy artifacts/checkpoints/device-detector/1.0.0.pt to
#    $MODEL_DIR/$DETECTOR_WEIGHTS and restart the API.
```

---

## 10. Reference Artifacts

| Artifact | Path |
| --- | --- |
| Split-aware manifest builder | `intelligence/device_ai/training/detector/data_manifest.py` |
| Inference benchmark | `intelligence/device_ai/training/detector/benchmark.py` |
| YOLO trainer | `intelligence/device_ai/training/detector/yolo_trainer.py` |
| Detection evaluator | `intelligence/device_ai/training/detector/evaluation.py` |
| Detector run config | `intelligence/device_ai/training/configs/detector.yaml` |
| Inference detector | `intelligence/device_ai/inference/yolo_detector.py` |
| Pipeline DI (real/mock swap) | `intelligence/device_ai/api/dependencies.py` |
| Dataset annotation runbook (upstream) | `docs/engineering/device_detection_annotation.md` |

> **Out of scope for P4.1.3:** no OpenCLIP, OCR, Condition-AI, or Material-AI
> work; no redesign of any architecture; no change to the `Detector` interface,
> the `Prediction` API, or pipeline contracts. This runbook trains and deploys
> the detector; it only replaces the served implementation.
