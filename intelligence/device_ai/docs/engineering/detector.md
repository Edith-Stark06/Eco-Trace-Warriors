# Device Detection Engine — YOLO Detector (M1.4)

> The first **real** model in the Device Intelligence Engine: an Ultralytics
> YOLO detector that replaces `MockDetector` behind the existing `Detector`
> interface **without changing the `/predict` API contract**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.4 — Device Detection Engine
**Status:** implemented; real training/weights are operator-run (documented below)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Inference — `YOLODetector`](#inference--yolodetector)
4. [Class → `device_type` mapping](#class--device_type-mapping)
5. [Guarded production swap](#guarded-production-swap)
6. [Training — `YOLOTrainer`](#training--yolotrainer)
7. [Evaluation — `DetectionEvaluator`](#evaluation--detectionevaluator)
8. [Artifact layout](#artifact-layout)
9. [Configuration](#configuration)
10. [Dataset preparation guide](#dataset-preparation-guide)
11. [Training instructions](#training-instructions)
12. [Evaluation results](#evaluation-results)
13. [Testing](#testing)
14. [Design rationale](#design-rationale)

---

## Scope

M1.4 makes **only** the detector real. Of the `/predict` response, only
`device_type`, `confidence` and the detection `bounding_box` come from the
model; **every other field remains a deterministic mock** until its own sprint:

| Field | Source in M1.4 |
|---|---|
| `device_type` | **real** — highest-confidence YOLO detection, mapped + title-cased |
| `confidence` | **real** — that detection's confidence |
| `bounding_box` (per detection) | **real** — YOLO `xyxy`, rounded to int |
| `brand` | placeholder `"Unknown"` (YOLO does not classify manufacturers) |
| `condition`, `ocr`, `materials`, `carbon_score`, `embedding_id` | mock (unchanged) |
| `eco_id`, `model_version` | unchanged |

**Explicitly out of scope** (stay mock): OCR, CLIP embeddings, device
fingerprinting, condition AI, material intelligence, carbon intelligence.
TensorRT export and downloading/training real weights in-repo are also out of
scope — the platform ships the *capability*; operators run real training per the
[instructions below](#training-instructions).

## Architecture

The detector reuses the M1.3 training platform and the M1.1 inference contract;
nothing is duplicated.

```
                 ┌────────────────── inference (serving) ──────────────────┐
POST /predict ──▶│ get_pipeline() ─ guarded selector ─┐                     │
                 │   ultralytics present + artifact ──▶│ build_detection_    │
                 │   resolves + loads?                 │  pipeline(detector) │
                 │   else ────────────────────────────▶│ build_mock_pipeline│
                 │                                     └─▶ PredictionPipeline│
                 │                       detector slot = YOLODetector (real) │
                 │              condition/ocr/material/embedding = mock      │
                 └──────────────────────────────────────────────────────────┘

                 ┌────────────────── training (offline) ───────────────────┐
python -m        │ YOLOTrainer(BaseTrainer).fit()  ── delegates loop ──▶     │
device_ai.train  │   Ultralytics model.train(resume=, patience=, project=…) │
--trainer yolo   │   reuses: ArtifactManager · ModelRegistry · Tracker ·    │
                 │           ExportRecord · Evaluator (report surface)      │
                 └──────────────────────────────────────────────────────────┘
```

Layering is unchanged (`api → inference → preprocessing → utils/configs`). The
detector is an `inference/` adapter; the trainer is a `training/detector/`
plug-in registered on the shared `TrainerRegistry`.

## Inference — `YOLODetector`

`inference/yolo_detector.py` implements the existing
`inference/predictor.py::Detector` contract, so wiring it into the pipeline (and
therefore `/predict`) is a dependency-injection concern only.

```python
class YOLODetector(Detector):
    version = "yolo-detector-1.0.0"

    def __init__(self, *, weights_path: Path | None = None,
                 image_size: int = 640, confidence_threshold: float = 0.25,
                 label_map: Mapping[str, str] | None = None,
                 model: Any | None = None) -> None: ...

    @property
    def is_ready(self) -> bool: ...          # True only when a model is loaded

    def detect(self, images: list[LoadedImage]) -> DetectionResult: ...
```

Flow of `detect()`:

1. Guard: if no model is loaded, raise `ModelNotLoadedError` (honest — never
   fakes a prediction).
2. Run inference over `[img.image for img in images]` — prefers the model's
   `predict(...)` (Ultralytics' public API) with `imgsz`, `conf`, `verbose=False`;
   falls back to calling the model directly (`__call__`).
3. Parse every result's `boxes` (`xyxy`, `conf`, `cls`) defensively — tolerant of
   both torch tensors (`.tolist()`) and plain lists — mapping class indices to
   names via each result's `names`. Detections below `confidence_threshold` are
   dropped; boxes are rounded to an int 4-tuple.
4. Aggregate: the **highest-confidence** detection across the batch drives
   `device_type`/`confidence`; `brand` is the placeholder. An empty batch yields
   `device_type="Unknown"`, `confidence=0.0`.

**Loading** (`weights_path` given, `model` not injected): `_resolve_weights`
accepts a direct `.pt`/`.onnx` file or a directory containing `model.pt` /
`model.onnx`. Loading is import-guarded and **degrades to not-ready** (returns
`None`, never raises) when the artifact is absent, Ultralytics is missing, or the
load fails — so the caller can fall back to the mock.

**Everything is injectable.** Passing `model=<fake>` bypasses disk/torch
entirely, which is how the whole parse/map/aggregate path is unit-tested in the
base environment (`tests/test_yolo_detector.py`).

## Class → `device_type` mapping

Raw model class names are normalised in `_map_label`:

1. apply the optional `label_map` (raw name → canonical name; identity fallback),
2. replace `_` with spaces and **title-case**.

So `cell_phone` with `label_map={"cell_phone": "smart_phone"}` → `Smart Phone`;
`laptop` (no mapping) → `Laptop`. The `label_map` lets a generic COCO-pretrained
model's vocabulary be projected onto EcoTrace's canonical device categories
without retraining, and is supplied at construction (no hardcoded label tables).

## Guarded production swap

`api/dependencies.py::get_pipeline()` chooses the pipeline at process start
(cached singleton). `_build_detector(settings)` resolves `detector_weights`
(relative to `model_dir` unless absolute) and constructs a `YOLODetector`.
Construction never raises; the selection rule is:

```
if detector is not None and detector.is_ready:   # ultralytics + artifact + load ok
    build_detection_pipeline(detector=…, model_version=…, year=…)
else:
    build_mock_pipeline(…)                        # honest fallback
```

Both branches produce an **identical** response schema, so the swap is invisible
to clients — and CI / the base environment (no ultralytics, no weights) stay
green on the mock path. This mirrors the M1.3 honesty pattern for
torch/onnx/mlflow.

## Training — `YOLOTrainer`

`training/detector/yolo_trainer.py`, registered as `@default_registry.register("yolo")`.

```python
class YOLOTrainer(BaseTrainer):
    framework = "ultralytics"
    monitor_metric = "mAP50_95"; monitor_mode = "max"

    def __init__(self, config, settings, *, data_config: Path | None = None,
                 yolo_factory: Callable[[str], Any] | None = None,
                 export_onnx: bool = True, ...): ...

    def fit(self) -> TrainingHistory: ...
```

`fit()` **overrides** the base epoch loop (see [rationale](#design-rationale))
and delegates to Ultralytics while reusing the platform for provenance:

```
seed → build_model(YOLO(base_weights))
  → open tracker.run(run_id, experiment_name, config)
      → model.train(data=data.yaml, epochs, imgsz, batch,
                    patience=early_stopping_patience,          # native early stopping
                    resume=<from `resume: "true"` tag>,        # native resume
                    project=artifacts.checkpoints, name=run_id,# native checkpointing
                    device, seed, verbose=False)
      → extract_metrics(results); run.log_metrics(...)
      → copy best.pt  → artifacts.checkpoint_path(model, version)
      → model.export(format="onnx") → artifacts.exports (ExportRecord)
      → run.set_summary({training_time, git_commit, device, export_formats})
  → registry.register(ModelRecord(framework, metrics, export_formats, location, …))
  → return TrainingHistory(…)
```

- **Resume** is opt-in via a `resume: "true"` run tag (there is no field on the
  frozen `TrainingConfig`); it flows straight into `model.train(resume=…)`.
- **Early stopping** maps `training.early_stopping_patience` → YOLO `patience`.
- **Checkpointing / MLflow** are Ultralytics-native (set `EXPERIMENT_TRACKER=mlflow`
  to also record via the platform's tracker wrapper).
- **ONNX export** is on by default (`export_onnx=False` to disable); the produced
  file is relocated under `artifacts/exports/` and recorded as an `ExportRecord`.
- **No backend, no fake run:** if neither a `yolo_factory` nor Ultralytics is
  available, `build_model()` raises `TrainingError`; `fit()` without a
  `data_config` also raises `TrainingError`.

The whole `fit()` delegation is unit-tested with an injected `yolo_factory`
producing a fake model (`tests/test_yolo_trainer.py`) — no torch/GPU.

## Evaluation — `DetectionEvaluator`

`training/detector/evaluation.py` adapts an Ultralytics `model.val()` result onto
the **shared** report surface (`build_evaluation_document` + `Evaluator`) — no new
report engine:

- `extract_metrics(results)` → `precision`, `recall`, `mAP50`, `mAP50_95` (read
  defensively from `results_dict` with `box`-attribute fallbacks, tolerant of
  Ultralytics key-name drift), plus a derived `f1 = 2·P·R/(P+R)` (0.0 when
  `P+R == 0`).
- `extract_confusion(results)` → the confusion matrix as an `int64` array.
- `names_to_list(names)` → class names ordered by index; `_align_labels` appends
  a `background` label when the matrix is one wider than the class list
  (Ultralytics adds a background row/col).
- `DetectionEvaluator.build_document(...)` / `.to_html(...)` produce the JSON +
  self-contained HTML report.

## Artifact layout

Resolved by `training/registry/artifact_manager.py` under `ARTIFACT_DIR` (paths
are never hardcoded). A completed detector run writes:

```
artifacts/
├── checkpoints/
│   ├── <run_id>/…                       # Ultralytics run dir (project/name)
│   └── device-detector-1.0.0.pt         # best.pt copied here (served artifact)
├── exports/
│   └── device-detector-1.0.0.onnx       # relocated ONNX export
├── reports/
│   ├── device-detector-1.0.0.json       # evaluation report (JSON)
│   └── device-detector-1.0.0.html       # evaluation report (HTML)
└── model_registry.json                  # ModelRecord provenance catalogue
mlruns/<run_id>/…                         # experiment-tracking run (json/mlflow)
```

To **serve** a trained detector, point `DETECTOR_WEIGHTS` at the produced
artifact (a file, or a directory containing `model.pt`/`model.onnx`) under
`MODEL_DIR`; `get_pipeline()` loads it on next start.

## Configuration

Additive, backwards-compatible env vars (defaults keep the mock path):

| Variable | Default | Description |
|---|---|---|
| `DETECTOR_WEIGHTS` | `yolov8n.pt` | Artifact locator (file/dir under `MODEL_DIR`, or absolute). Absent/unloadable → mock fallback. |
| `DETECTOR_IMAGE_SIZE` | `640` | Inference image size (px) forwarded to YOLO. |
| `DETECTOR_CONFIDENCE_THRESHOLD` | `0.25` | Minimum kept-detection confidence. |

Training hyper-parameters compose from `training/configs/detector.yaml` (a
Hydra-compatible `defaults` list over `training.yaml` + `optimizer.yaml`),
overriding `model_name: device-detector`, `trainer: yolo`,
`training.image_size: 640`, `training.early_stopping_patience: 20`.

## Dataset preparation guide

Reuse the **existing** M1.2 dataset pipeline — do not hand-assemble YOLO folders.
From a running service (`http://localhost:8100`):

```bash
# 1. Import & de-duplicate source photos into the managed raw/ tree
curl -X POST http://localhost:8100/dataset/import \
  -H 'Content-Type: application/json' \
  -d '{"source": "/data/incoming_device_photos", "deduplicate": true}'

# 2. Validate YOLO annotations against the images (bound the class range)
curl -X POST http://localhost:8100/dataset/validate \
  -H 'Content-Type: application/json' -d '{"num_classes": 4}'

# 3. (optional) Augment, then export in YOLO format
curl -X POST http://localhost:8100/dataset/export \
  -H 'Content-Type: application/json' \
  -d '{"format": "yolo", "class_names": ["laptop","smartphone","tablet","monitor"]}'
```

The export writes `datasets/exports/yolo/{images,labels,data.yaml}`. That
`data.yaml` is exactly the `--data-config` the trainer consumes — one source of
truth, no duplication.

## Training instructions

Real training needs the optional model dependencies (a machine with a GPU is
strongly recommended):

```bash
cd intelligence/device_ai
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-models.txt    # ultralytics, torch, onnx, mlflow, hydra
```

Then, from `intelligence/` with `PYTHONPATH=.`:

```bash
# Train the detector (resume/early-stopping/checkpointing are Ultralytics-native)
python -m device_ai.train \
  --trainer yolo \
  --config device_ai/training/configs/detector.yaml \
  --data-config device_ai/datasets/exports/yolo/data.yaml \
  --epochs 100 --batch-size 16 --run

# Resume an interrupted run (opt-in via the run tag; see detector.yaml)
#   add `tags: {resume: "true"}` to the config, then re-run the same command.

# Track with MLflow instead of the JSON tracker
EXPERIMENT_TRACKER=mlflow python -m device_ai.train --trainer yolo \
  --config device_ai/training/configs/detector.yaml \
  --data-config .../data.yaml --run

# Render the recorded metrics into a JSON + HTML report
python -m device_ai.evaluate --model-name device-detector --model-version 1.0.0

# Export to deployment formats (ONNX is produced during fit; this re-attempts)
python -m device_ai.export --model-name device-detector --model-version 1.0.0
```

Without `--run` the CLI prints the composed **run plan** (dry run). Without the
model dependencies installed, `--run` fails fast with a `TrainingError` (honest —
it cannot train without a backend).

## Evaluation results

Because no dataset or weights ship in-repo, a **byte-stable, illustrative**
evaluation report is generated from a fake `val()` result and checked in under
[`../examples/detector/`](../examples/detector/):

```bash
# from intelligence/ with PYTHONPATH=.
python -m device_ai.scripts.gen_detector_examples
```

It shows the real report shape a run produces — `precision`, `recall`, `mAP50`,
`mAP50_95`, derived `f1`, a four-class confusion matrix (plus the `background`
row/col) and the benchmark placeholder. A real `model.val()` populates the same
document with measured numbers.

## Testing

All M1.4 tests run in the **base environment** (no torch/ultralytics/GPU) via
injected fakes. From `intelligence/device_ai`:

```bash
pytest tests/test_yolo_detector.py \
       tests/test_yolo_trainer.py \
       tests/test_detection_evaluation.py \
       tests/test_predict_detection.py -q
```

- `test_yolo_detector.py` — parse/map/aggregate, DI model, threshold filtering,
  callable-only fallback, not-loaded guard, weight resolution.
- `test_yolo_trainer.py` — `fit()` delegation, checkpoint copy, ONNX
  `ExportRecord`, `ModelRecord` registration, `TrainingHistory`, resume tag,
  no-backend `TrainingError`, registry registration.
- `test_detection_evaluation.py` — metric extraction (+`f1`), confusion rounding,
  `names` normalisation, background alignment, HTML rendering.
- `test_predict_detection.py` — **integration**: `build_detection_pipeline` with
  an injected `YOLODetector(model=fake)` → `/predict` returns the **unchanged
  schema** with a real `device_type`/`confidence` and placeholder everything
  else; the existing mock `test_predict.py` stays green.

## Design rationale

**Why override `fit()` instead of implementing `train_step`/`validation_step`?**
Ultralytics already implements resume, early stopping, checkpointing and native
MLflow logging inside its own training loop. Forcing that through
`BaseTrainer`'s per-step epoch loop would *re-implement framework functionality*
— exactly the duplication the sprint (and `CLAUDE.md`) forbids. So `YOLOTrainer`
delegates the loop but **reuses** the platform's provenance/reporting
collaborators (`ArtifactManager`, `ModelRegistry`, `ExperimentTracker`,
`ExportRecord`, `Evaluator`). The five abstract hooks remain implemented (the ABC
requires them) but are inert: `train_loader`/`val_loader` return `()` and the
step hooks raise `NotImplementedError`, documenting that the loop is
Ultralytics', not ours.

**Why dependency-inject the model/factory?** The heavy backend
(ultralytics/torch/GPU) is absent in CI and the base environment. Injecting a
loaded `model` (inference) or a `yolo_factory` (training) lets every unit of
parsing/mapping/aggregation/delegation logic be tested deterministically with
tiny fakes, while the real backend paths are marked `# pragma: no cover`.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md), [`training/README.md`](../../training/README.md)
and the platform-wide `docs/engineering/` standards._
