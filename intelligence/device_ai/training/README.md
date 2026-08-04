# AI Training & MLOps Platform (M1.3)

> The reusable training **ecosystem** for the Device Intelligence Engine.
> Every future model — YOLO detector, CLIP encoder, OCR, condition classifier,
> material estimator, carbon intelligence — plugs into this platform.

**Scope note.** This milestone builds the *platform only*. It contains **no**
model implementations, trains no real models, downloads no datasets and
implements neither YOLO, CLIP nor OCR. TensorRT export is explicitly out of
scope. A `MockTrainer` in the test-suite exercises the full lifecycle end to
end so the ecosystem is proven without any trained weights.

---

## Design principles

- **Light default, optional adapters.** The whole platform runs in the base
  environment (FastAPI + Pydantic + NumPy + PyYAML). Heavy libraries —
  **PyTorch, ONNX, Hydra, MLflow** — are optional (`requirements-models.txt`)
  and accessed behind import guards. When absent, the platform degrades
  *honestly*: config still composes via PyYAML, experiment tracking falls back
  to a JSON tracker, and exporters return a `skipped` record instead of
  pretending an export happened.
- **Dependency injection everywhere.** Every collaborator (artifact layout,
  experiment tracker, model registry) and every source of non-determinism (the
  clock, the Git commit, the RNG seed) is injected, so a run is fully
  reproducible and unit-testable without touching the wall clock, the
  filesystem root or global state.
- **No duplication with M1.2.** Training reads datasets through the existing
  dataset pipeline's versioning; it does not re-implement dataset handling.

## Folder structure

```
training/
├── config.py            # typed RunConfig / TrainingConfig / OptimizerConfig + YAML loader
├── configs/             # default.yaml + training.yaml + optimizer.yaml (Hydra-compatible)
├── core/
│   ├── trainer.py       # BaseTrainer — the abstract, reusable training lifecycle
│   ├── callbacks.py     # EarlyStopping, ModelCheckpoint, LoggingCallback
│   ├── metrics.py       # pure-NumPy accuracy / precision / recall / F1 / confusion / mAP
│   ├── evaluator.py     # JSON + self-contained HTML evaluation report
│   ├── exporter.py      # PyTorch / TorchScript / ONNX export adapters (import-guarded)
│   └── registry.py      # TrainerRegistry (name → trainer class)
├── experiments/
│   ├── tracker.py       # ExperimentTracker protocol + JSON tracker + NullTracker
│   └── mlflow.py        # optional MLflow adapter (import-guarded)
├── registry/
│   ├── model_registry.py  # JSON-backed ModelRegistry + ModelRecord provenance
│   └── artifact_manager.py# resolves/creates the checkpoints/exports/reports tree
└── utils/               # seeding, timing, git metadata, environment capture
```

## The training lifecycle

`BaseTrainer` captures everything common to training any model, deferring the
model-specific pieces to five abstract hooks. A future `YOLOTrainer` /
`CLIPTrainer` implements **only** those hooks:

```python
class YOLOTrainer(BaseTrainer):
    framework = "pytorch"

    def build_model(self): ...
    def train_loader(self): ...
    def val_loader(self): ...
    def train_step(self, model, batch) -> dict[str, float]: ...
    def validation_step(self, model, batch) -> dict[str, float]: ...
```

`fit()` then orchestrates a reproducible run:

```
seed RNGs → resolve device → open tracked run
   → for each epoch: aggregate train + val_ metrics → dispatch callbacks
     (honour early stopping) → log metrics to the tracker
   → write checkpoint → set run summary
   → auto-register a ModelRecord (name, version, dataset version, timestamp,
     git commit, framework, metrics, export formats, artifact location)
→ return an immutable TrainingHistory
```

Register a trainer so the CLI can resolve it by name:

```python
from device_ai.training.core.registry import default_registry

@default_registry.register("yolo")
class YOLOTrainer(BaseTrainer):
    ...
```

## Configuration

Runs are described by a single validated `RunConfig` (a `TrainingConfig` +
`OptimizerConfig` + metadata). YAML is loaded with a **Hydra-compatible
`defaults` list**, so `configs/default.yaml` composes `training.yaml` and
`optimizer.yaml` with only PyYAML installed. When `hydra-core` is added the
same files work unchanged with a full Hydra pipeline (`hydra_available()`
reports which backend is active).

## Experiment tracking & model registry

- **Experiment tracking** is pluggable via the `ExperimentTracker` protocol.
  The default `JsonExperimentTracker` writes `params.json` / `metrics.json` /
  `meta.json` per run under `MLRUNS_DIR`. Setting `EXPERIMENT_TRACKER=mlflow`
  activates the MLflow adapter *if installed*, otherwise it falls back to JSON
  with a warning. `EXPERIMENT_TRACKER=none` disables tracking.
- **Model registry** is a JSON catalogue under `ARTIFACT_DIR`. Every `fit()`
  auto-registers a `ModelRecord`; query it with `list_models`, `versions`,
  `latest`, `get` and `resolve(name, "latest")`.

## Export

`export_model` writes one `ExportRecord` per requested format
(`pytorch` / `torchscript` / `onnx`). Each adapter checks for its backend and,
when torch/onnx are not installed, returns `status="skipped"` — the platform is
fully exercisable in the base environment without silently faking an export.
TensorRT is out of scope for this milestone.

## Command-line interface

Three thin CLIs drive the platform (each delegating to a unit-testable
`*_main` function). Run from `intelligence/` with `PYTHONPATH=.`:

```bash
# Compose + validate config, resolve paths, print the run plan (dry run —
# no concrete trainer ships in M1.3, so a dry run is the honest default):
python -m device_ai.train --config device_ai/training/configs/default.yaml

# Attempt a real fit() once a trainer is registered under --trainer:
python -m device_ai.train --trainer yolo --epochs 50 --run

# Render a registered model's recorded metrics into JSON + HTML:
python -m device_ai.evaluate --model device-detector --version 1.0.0

# Attempt export (honestly reports "skipped" when torch/onnx are absent):
python -m device_ai.export --model device-detector --version 1.0.0
```

## Testing

The platform ships a `MockTrainer` (in the test-suite) that implements the five
hooks, so `fit()` is exercised end to end — seeding, the epoch loop, callback
dispatch, tracking, checkpointing and auto-registration — with zero trained
weights. From `intelligence/device_ai`:

```bash
pytest tests -q
pytest tests --cov=device_ai.training --cov-report=term-missing
```

Coverage on `device_ai/training` is **99%** (the only uncovered line is the
MLflow-return branch, reachable solely when MLflow is installed).

## Example artifacts

Illustrative, byte-stable outputs of a mock run — a model-registry entry, a
training-history summary and a JSON/HTML evaluation report — are checked in
under [`../docs/examples/training/`](../docs/examples/training/). Regenerate
them with `python -m device_ai.scripts.gen_training_examples`.

## First real plug-in — YOLO detector (M1.4)

Milestone M1.4 adds the first concrete trainer, `training/detector/`, proving the
platform with a real model:

- **`YOLOTrainer(BaseTrainer)`** (registered as `"yolo"`) **overrides `fit()`**
  to delegate the epoch loop to Ultralytics — because Ultralytics already
  implements resume, early stopping, checkpointing and native MLflow logging,
  driving it through the per-step hooks would *duplicate framework
  functionality*. It still **reuses** every platform collaborator
  (`ArtifactManager`, `ModelRegistry`, `ExperimentTracker`, `ExportRecord`) for
  provenance and ONNX export, and auto-registers the same `ModelRecord`. The five
  abstract hooks remain implemented but inert (loaders return `()`, step hooks
  raise) — documenting that the loop is Ultralytics', not ours.
- **`DetectionEvaluator`** adapts an Ultralytics `model.val()` result
  (mAP/precision/recall, derived F1, confusion matrix) onto the **shared**
  `build_evaluation_document` + `Evaluator` report surface — only the
  detection-specific *extraction* is new.

See [`../docs/engineering/detector.md`](../docs/engineering/detector.md) for the
full detector design, dataset-preparation and training instructions.

## Serving plug-in — OpenCLIP encoder (M1.5)

Milestone M1.5 adds the **fingerprinting engine**'s real encoder,
`inference/clip_encoder.py` → `CLIPEncoder(EmbeddingEncoder)`. It is a **serving**
plug-in (no trainer ships yet), but it follows the same platform conventions as
the detector so a future `CLIPTrainer` drops onto this platform unchanged:

- **Registry-aligned artifact convention.** The encoder's weights are resolved
  from the configured `CLIP_WEIGHTS` locator **relative to `MODEL_DIR`** (never a
  hardcoded path) — the same "artifacts live under `MODEL_DIR`, addressed by a
  settings locator" convention the `ModelRegistry` and detector use. A directory
  locator is searched for a known artifact file (`open_clip_pytorch_model.bin`,
  then `model.pt`); when nothing resolves — or `open-clip-torch`/`torch` are
  absent — the encoder degrades **honestly** to not-ready and the service serves
  the deterministic mock encoder.
- **Same reuse story.** When a `CLIPTrainer(BaseTrainer)` is eventually added it
  reuses `ArtifactManager`/`ModelRegistry`/`ExperimentTracker`/`ExportRecord` for
  provenance and export exactly as `YOLOTrainer` does, and auto-registers a
  `ModelRecord` the serving path can then `resolve(name, "latest")`.

See [`../docs/engineering/fingerprint.md`](../docs/engineering/fingerprint.md)
for the full fingerprinting-engine design, similarity metrics and integration
instructions.

## Serving plug-in — EasyOCR backend (M1.6)

Milestone M1.6 adds the **OCR Intelligence Engine**'s real text backend,
`ocr/backends.py` → `EasyOCRBackend(OCRBackend)` (plus the OpenCV QR/barcode
reader). Like the OpenCLIP encoder it is a **serving-only** plug-in — **no
trainer ships**, because EasyOCR is *pretrained* — yet it follows the same
platform conventions so it stays consistent with the rest of the ecosystem:

- **`MODEL_DIR` locator convention.** The reader's model-storage directory is
  resolved from the configured `OCR_WEIGHTS` locator **relative to `MODEL_DIR`**
  (never a hardcoded path) — the same "artifacts live under `MODEL_DIR`,
  addressed by a settings locator" convention the `ModelRegistry`, detector and
  CLIP encoder use. When the directory is absent — or `easyocr` /
  `opencv-python-headless` are not installed — the backend degrades **honestly**
  to not-ready and the service serves the deterministic `MockOCRBackend` /
  `MockBarcodeReader`.
- **No trainer by design.** EasyOCR (like OpenCLIP) is consumed pretrained, so
  M1.6 ships a serving adapter only — there is no `OCRTrainer`. Should a future
  fine-tuning need arise, an `OCRTrainer(BaseTrainer)` would reuse
  `ArtifactManager`/`ModelRegistry`/`ExperimentTracker`/`ExportRecord` exactly as
  `YOLOTrainer` does; nothing about this serving plug-in precludes it.

See [`../docs/engineering/ocr.md`](../docs/engineering/ocr.md) for the full OCR
engine design, the pattern/validator table, the parser/normalization layer,
barcode/QR decoding and the optional fingerprint-identity seam.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../README.md) and `docs/engineering/` for platform-wide
standards._
